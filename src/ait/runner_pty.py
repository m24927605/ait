from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import termios
import time
import tty


# P0 fix: bound the PTY capture buffer. Was `output = bytearray()` with
# no cap (line 40). A 10-minute verbose Claude Code run can emit
# hundreds of MB and OOM the host before any downstream truncation
# applies. After the budget is exceeded we still drain the PTY (so the
# child does not block) and still mirror to terminal (so the user sees
# the live trace), but stop accumulating into the captured buffer.
_AIT_PTY_OUTPUT_BUDGET_BYTES = 32 * 1024 * 1024


def _resolve_pty_budget() -> int:
    raw = os.environ.get("AIT_RUN_OUTPUT_BUDGET_BYTES", "").strip()
    if not raw:
        return _AIT_PTY_OUTPUT_BUDGET_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _AIT_PTY_OUTPUT_BUDGET_BYTES
    if value < 1024:
        return _AIT_PTY_OUTPUT_BUDGET_BYTES
    return value


def _resolve_pty_timeout() -> float | None:
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


def _killpg_best_effort(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass


@dataclass(frozen=True, slots=True)
class _PtyCompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str = ""


def _stdio_is_tty() -> bool:
    return (
        hasattr(sys.stdin, "isatty")
        and hasattr(sys.stdout, "isatty")
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def _run_command_with_pty_transcript(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> _PtyCompletedProcess:
    master_fd, slave_fd = pty.openpty()
    old_stdin_attrs = None
    output = bytearray()
    # P0 fix: cap the captured buffer. Mirror-to-terminal is unaffected.
    budget = _resolve_pty_budget()
    truncated_marker = (
        f"\n... [ait: pty transcript truncated after {budget} bytes; "
        "raise AIT_RUN_OUTPUT_BUDGET_BYTES to capture more] ...\n"
    ).encode("utf-8")
    truncated = False
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    stdin_is_tty = sys.stdin.isatty()
    stdin_fd = sys.stdin.fileno() if stdin_is_tty else None
    if stdin_is_tty:
        assert stdin_fd is not None
        old_stdin_attrs = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            # P0 fix: own the process group so timeout / Ctrl-C
            # escalation can killpg the child tree.
            start_new_session=True,
        )
    finally:
        os.close(slave_fd)

    # P0 fix: optional timeout. Default None preserves prior behavior.
    timeout_seconds = _resolve_pty_timeout()
    deadline = (
        time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    )

    # P0 fix: Ctrl-C escalation. First SIGINT → process group; second
    # SIGINT within 3s → SIGKILL to group. Only the main thread can
    # install signal handlers.
    last_sigint_at: list[float] = []
    previous_handler = None
    handler_installed = False

    def _on_sigint(_signum: int, _frame: object) -> None:
        now = time.monotonic()
        if last_sigint_at and now - last_sigint_at[-1] < 3.0:
            _killpg_best_effort(process.pid, signal.SIGKILL)
        else:
            _killpg_best_effort(process.pid, signal.SIGINT)
        last_sigint_at.append(now)

    import threading as _threading

    if _threading.current_thread() is _threading.main_thread():
        try:
            previous_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, _on_sigint)
            handler_installed = True
        except (ValueError, OSError):
            handler_installed = False

    def _append_to_buffer(data: bytes) -> None:
        nonlocal truncated
        if truncated:
            return
        if len(output) + len(data) > budget:
            output.extend(truncated_marker)
            truncated = True
            return
        output.extend(data)

    try:
        while True:
            read_fds = [master_fd]
            if stdin_fd is not None and process.poll() is None:
                read_fds.append(stdin_fd)
            readable, _, _ = select.select(read_fds, [], [], 0.05)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    data = b""
                if data:
                    _append_to_buffer(data)
                    _write_terminal_bytes(stdout_buffer, data)
                elif process.poll() is not None:
                    break
            if stdin_fd is not None and stdin_fd in readable:
                data = os.read(stdin_fd, 4096)
                if data:
                    os.write(master_fd, data)
            if deadline is not None and time.monotonic() >= deadline and process.poll() is None:
                _killpg_best_effort(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    _killpg_best_effort(process.pid, signal.SIGKILL)
            if process.poll() is not None:
                try:
                    while True:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        _append_to_buffer(data)
                        _write_terminal_bytes(stdout_buffer, data)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                break
        return _PtyCompletedProcess(
            args=command,
            returncode=process.wait(),
            stdout=output.decode("utf-8", errors="replace"),
        )
    finally:
        if handler_installed:
            try:
                signal.signal(signal.SIGINT, previous_handler)
            except (ValueError, OSError):
                pass
        if old_stdin_attrs is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_stdin_attrs)
        os.close(master_fd)


def _write_terminal_bytes(stdout_buffer: object, data: bytes) -> None:
    if stdout_buffer is not None:
        stdout_buffer.write(data)  # type: ignore[attr-defined]
        stdout_buffer.flush()  # type: ignore[attr-defined]
        return
    sys.stdout.write(data.decode("utf-8", errors="replace"))
    sys.stdout.flush()
