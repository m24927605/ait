"""Subprocess runner with byte budget, timeout, and process-group cancellation.

Replaces the bare `subprocess.run(..., capture_output=True)` call used by
`ait.runner` for non-PTY command execution. The bare call has two
production-grade failure modes that this module addresses:

1. **Unbounded RAM growth.** `capture_output=True` buffers the entire
   stdout + stderr in memory before the caller can truncate. A 10-minute
   verbose agent run can emit hundreds of MB and OOM the host before any
   downstream truncation runs.

2. **No timeout, no process-group cancellation.** Bare `subprocess.run`
   does not set `start_new_session=True`, so on `Ctrl-C` the child can
   swallow SIGINT and AIT has no way to escalate. There is also no
   timeout, so a hung agent CLI blocks `ait run` forever.

This helper:

- Starts the child in a new session (`start_new_session=True`) so the
  caller owns the process group.
- Streams stdout/stderr through reader threads with a configurable byte
  budget. After the budget is reached, output is silently dropped from
  the captured buffer but still flowed to the terminal (when replay is
  requested) so the user sees the live trace.
- Honors an optional `timeout_seconds`. On timeout the process group is
  killed with SIGTERM, then SIGKILL after a 5-second grace.
- Installs a SIGINT handler scoped to the call: first Ctrl-C sends
  SIGINT to the process group; a second Ctrl-C within 3 seconds
  escalates to SIGKILL. The handler is restored on return.

Returns a `subprocess.CompletedProcess[str]` so callers do not need to
change their interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO

# Default capture budget. Configurable via AIT_RUN_OUTPUT_BUDGET_BYTES.
# 32 MiB is large enough for verbose Claude Code / Codex sessions but
# small enough to survive on a 1 GB CI runner with several concurrent
# attempts. Truncation is silent for the captured buffer; the terminal
# still sees the live stream when replay is enabled.
_DEFAULT_OUTPUT_BUDGET_BYTES = 32 * 1024 * 1024


def _resolve_budget_bytes() -> int:
    raw = os.environ.get("AIT_RUN_OUTPUT_BUDGET_BYTES", "").strip()
    if not raw:
        return _DEFAULT_OUTPUT_BUDGET_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_OUTPUT_BUDGET_BYTES
    if value < 1024:  # nonsense values fall back to default
        return _DEFAULT_OUTPUT_BUDGET_BYTES
    return value


def _resolve_timeout_seconds(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is not None:
        return timeout_seconds
    raw = os.environ.get("AIT_RUN_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


@dataclass(frozen=True, slots=True)
class _StreamResult:
    text: str
    truncated: bool


def _drain_stream_with_budget(
    stream: IO[str],
    budget_bytes: int,
    *,
    mirror_to: IO[str] | None,
) -> _StreamResult:
    """Read `stream` to EOF, accumulating into a bounded buffer.

    Once the byte budget is exceeded, further data is still drained
    from the OS pipe (so the child does not block on a full pipe
    buffer) and still mirrored to `mirror_to` (so the user sees the
    live trace), but is dropped from the captured buffer. A single
    truncation marker is appended to the buffer at the point of
    overflow.
    """
    buffer: list[str] = []
    used = 0
    truncated = False
    truncation_marker = (
        "\n... [ait: captured output truncated after "
        f"{budget_bytes} bytes; raise AIT_RUN_OUTPUT_BUDGET_BYTES to "
        "see more in transcripts] ...\n"
    )
    while True:
        chunk = stream.readline()
        if not chunk:
            break
        if mirror_to is not None:
            try:
                mirror_to.write(chunk)
                mirror_to.flush()
            except (OSError, ValueError):
                # mirror failure must not kill the drain
                pass
        if truncated:
            continue
        chunk_bytes = len(chunk.encode("utf-8", errors="replace"))
        if used + chunk_bytes > budget_bytes:
            buffer.append(truncation_marker)
            truncated = True
            continue
        buffer.append(chunk)
        used += chunk_bytes
    return _StreamResult(text="".join(buffer), truncated=truncated)


def _kill_process_group(pid: int, sig: int) -> None:
    """Best-effort process-group signal. Tolerates the group being gone."""
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        # ProcessLookupError: group already exited
        # PermissionError: rare; fall back to direct kill
        # OSError: e.g. ESRCH between getpgid and killpg
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def run_command_with_budget_and_timeout(
    command: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str],
    capture_output: bool,
    command_stdin: str | None,
    stdin_mode: str,
    timeout_seconds: float | None = None,
    mirror_to_terminal: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Drop-in replacement for `subprocess.run(...)` used by `ait.runner`.

    Differences from the bare `subprocess.run(capture_output=True)`:

    - Child runs in a new session (`start_new_session=True`) so SIGINT
      escalation works.
    - stdout / stderr are streamed with a byte budget instead of fully
      buffered in RAM.
    - `timeout_seconds` is honored via SIGTERM → SIGKILL on the process
      group (default 5-second grace before SIGKILL).
    - First Ctrl-C sends SIGINT to the process group; a second Ctrl-C
      within 3 seconds escalates to SIGKILL.

    Returns a `subprocess.CompletedProcess[str]` whose `.stdout` and
    `.stderr` may be empty strings when `capture_output=False`.
    """
    if not capture_output:
        stdout_target: int | None = None
        stderr_target: int | None = None
    else:
        stdout_target = subprocess.PIPE
        stderr_target = subprocess.PIPE
    if command_stdin is not None:
        stdin_target: int | None = subprocess.PIPE
    elif stdin_mode == "none":
        stdin_target = subprocess.DEVNULL
    else:
        stdin_target = None

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdin=stdin_target,
        stdout=stdout_target,
        stderr=stderr_target,
        # Detach from AIT's process group so we can killpg() the child
        # tree without taking AIT down. Required for both Ctrl-C
        # escalation and timeout-driven cancellation.
        start_new_session=True,
    )

    # Per-call SIGINT escalation. First Ctrl-C → SIGINT to group;
    # second Ctrl-C inside 3s → SIGKILL to group.
    last_sigint_at: list[float] = []
    previous_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(_signum: int, _frame: object) -> None:
        now = time.monotonic()
        if last_sigint_at and now - last_sigint_at[-1] < 3.0:
            _kill_process_group(process.pid, signal.SIGKILL)
        else:
            _kill_process_group(process.pid, signal.SIGINT)
        last_sigint_at.append(now)

    # Only install the handler if we're on the main thread; pytest /
    # threaded harnesses must not have their handlers stomped.
    handler_installed = False
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, _on_sigint)
            handler_installed = True
        except (ValueError, OSError):
            handler_installed = False

    budget = _resolve_budget_bytes()
    stdout_result = _StreamResult(text="", truncated=False)
    stderr_result = _StreamResult(text="", truncated=False)
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None
    if capture_output and process.stdout is not None:
        def _read_stdout() -> None:
            nonlocal stdout_result
            stdout_result = _drain_stream_with_budget(
                process.stdout,  # type: ignore[arg-type]
                budget,
                mirror_to=sys.stdout if mirror_to_terminal else None,
            )
        stdout_thread = threading.Thread(
            target=_read_stdout, daemon=True, name="ait-runner-stdout",
        )
        stdout_thread.start()
    if capture_output and process.stderr is not None:
        def _read_stderr() -> None:
            nonlocal stderr_result
            stderr_result = _drain_stream_with_budget(
                process.stderr,  # type: ignore[arg-type]
                budget,
                mirror_to=sys.stderr if mirror_to_terminal else None,
            )
        stderr_thread = threading.Thread(
            target=_read_stderr, daemon=True, name="ait-runner-stderr",
        )
        stderr_thread.start()
    if command_stdin is not None and process.stdin is not None:
        try:
            process.stdin.write(command_stdin)
        except (OSError, ValueError):
            pass
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

    deadline = (
        time.monotonic() + timeout_seconds
        if (timeout_seconds := _resolve_timeout_seconds(timeout_seconds))
        is not None
        else None
    )
    try:
        while True:
            try:
                returncode = process.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if deadline is not None and time.monotonic() >= deadline:
                    _kill_process_group(process.pid, signal.SIGTERM)
                    try:
                        returncode = process.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        _kill_process_group(process.pid, signal.SIGKILL)
                        returncode = process.wait()
                    raise subprocess.TimeoutExpired(
                        cmd=command,
                        timeout=deadline,
                        output=stdout_result.text,
                        stderr=stderr_result.text,
                    )
    finally:
        # Restore caller's SIGINT handler regardless of outcome.
        if handler_installed:
            try:
                signal.signal(signal.SIGINT, previous_handler)
            except (ValueError, OSError):
                pass
        if stdout_thread is not None:
            stdout_thread.join(timeout=5.0)
        if stderr_thread is not None:
            stderr_thread.join(timeout=5.0)

    return subprocess.CompletedProcess(
        args=command,
        returncode=returncode,
        stdout=stdout_result.text if capture_output else "",
        stderr=stderr_result.text if capture_output else "",
    )
