"""Tests for ait.runner_subprocess (P0 fixes for runner OOM + timeout)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ait.runner_subprocess import run_command_with_budget_and_timeout


# ---------------------------------------------------------------------------
# Byte-budget enforcement
# ---------------------------------------------------------------------------


def test_captured_output_truncates_when_over_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child that emits more than the budget gets its captured buffer
    truncated. The marker appears in the captured stdout. The process
    is allowed to run to completion (we never block the child)."""
    monkeypatch.setenv("AIT_RUN_OUTPUT_BUDGET_BYTES", "4096")
    payload = "X" * 100  # 100 bytes per line × 100 lines = 10 KB > 4 KB budget
    script = (
        "import sys\n"
        f"for _ in range(100):\n"
        f"    sys.stdout.write('{payload}' + '\\n')\n"
        "    sys.stdout.flush()\n"
    )
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert "[ait: captured output truncated" in completed.stdout
    # Captured buffer should be close to budget (within a few KB of slack
    # for the truncation marker and one final partial line).
    assert len(completed.stdout) < 6 * 1024


def test_captured_output_under_budget_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Output below the budget is preserved verbatim with no marker."""
    monkeypatch.setenv("AIT_RUN_OUTPUT_BUDGET_BYTES", str(10 * 1024 * 1024))
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "print('hello-ait')"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert "hello-ait" in completed.stdout
    assert "truncated" not in completed.stdout


def test_invalid_budget_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garbage budget env var doesn't crash; default is used."""
    monkeypatch.setenv("AIT_RUN_OUTPUT_BUDGET_BYTES", "not-a-number")
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "print('ok')"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert "ok" in completed.stdout


# ---------------------------------------------------------------------------
# Timeout + process-group cancellation
# ---------------------------------------------------------------------------


def test_timeout_kills_hanging_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child that ignores SIGTERM still dies via SIGKILL after grace."""
    monkeypatch.setenv("AIT_RUN_TIMEOUT_SECONDS", "1")
    # Child sleeps 30s; we expect cancellation after ~1s + 5s grace.
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_command_with_budget_and_timeout(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            env=os.environ.copy(),
            capture_output=True,
            command_stdin=None,
            stdin_mode="inherit",
        )
    elapsed = time.monotonic() - started
    # Must terminate well before the child's 30s sleep.
    assert elapsed < 15.0, f"timeout took too long: {elapsed}s"


def test_no_timeout_runs_to_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no timeout is set, normal child runs to completion."""
    monkeypatch.delenv("AIT_RUN_TIMEOUT_SECONDS", raising=False)
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "print('done')"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert "done" in completed.stdout


# ---------------------------------------------------------------------------
# Process-group isolation (start_new_session=True)
# ---------------------------------------------------------------------------


def test_child_runs_in_new_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child must be in its own process group so we can killpg
    without taking AIT down. Child prints its own pgid; we verify it
    differs from AIT's pgid."""
    monkeypatch.delenv("AIT_RUN_TIMEOUT_SECONDS", raising=False)
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "import os; print(os.getpgrp())"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    child_pgid = int(completed.stdout.strip())
    parent_pgid = os.getpgrp()
    assert child_pgid != parent_pgid, (
        f"child pgid {child_pgid} == parent pgid {parent_pgid}; "
        "start_new_session=True is not taking effect"
    )


# ---------------------------------------------------------------------------
# stdin handling
# ---------------------------------------------------------------------------


def test_command_stdin_is_piped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """command_stdin is written to the child's stdin."""
    monkeypatch.delenv("AIT_RUN_TIMEOUT_SECONDS", raising=False)
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin="hello from ait stdin",
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert "hello from ait stdin" in completed.stdout


def test_stdin_mode_none_uses_devnull(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stdin_mode='none' connects child stdin to /dev/null."""
    monkeypatch.delenv("AIT_RUN_TIMEOUT_SECONDS", raising=False)
    # If stdin is /dev/null, .read() returns immediately as empty.
    completed = run_command_with_budget_and_timeout(
        [
            sys.executable,
            "-c",
            "import sys; data = sys.stdin.read(); print(f'len={len(data)}')",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        command_stdin=None,
        stdin_mode="none",
    )
    assert completed.returncode == 0
    assert "len=0" in completed.stdout


# ---------------------------------------------------------------------------
# Non-capture mode
# ---------------------------------------------------------------------------


def test_capture_output_false_returns_empty_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When capture_output=False the child's stdout flows to AIT's stdout
    and the returned CompletedProcess.stdout is empty."""
    monkeypatch.delenv("AIT_RUN_TIMEOUT_SECONDS", raising=False)
    completed = run_command_with_budget_and_timeout(
        [sys.executable, "-c", "print('inherited')"],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=False,
        command_stdin=None,
        stdin_mode="inherit",
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
