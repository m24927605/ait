from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
import struct
import sys
import termios


_FALLBACK_COLS = 80
_FALLBACK_ROWS = 24


@dataclass(frozen=True, slots=True)
class PtyWindowSize:
    rows: int
    cols: int


def current_pty_window_size() -> PtyWindowSize:
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            fd = stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
        try:
            size = os.get_terminal_size(fd)
        except OSError:
            continue
        if size.lines > 0 and size.columns > 0:
            return PtyWindowSize(rows=size.lines, cols=size.columns)
    return PtyWindowSize(rows=_FALLBACK_ROWS, cols=_FALLBACK_COLS)


def set_pty_window_size(fd: int, size: PtyWindowSize) -> bool:
    rows = size.rows if size.rows > 0 else _FALLBACK_ROWS
    cols = size.cols if size.cols > 0 else _FALLBACK_COLS
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        return False
    return True
