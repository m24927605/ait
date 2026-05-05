from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios
import tty


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
        )
    finally:
        os.close(slave_fd)

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
                    output.extend(data)
                    _write_terminal_bytes(stdout_buffer, data)
                elif process.poll() is not None:
                    break
            if stdin_fd is not None and stdin_fd in readable:
                data = os.read(stdin_fd, 4096)
                if data:
                    os.write(master_fd, data)
            if process.poll() is not None:
                try:
                    while True:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        output.extend(data)
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
