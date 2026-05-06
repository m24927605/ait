from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DaemonStatus:
    socket_path: Path
    pid_file: Path
    running: bool
    pid: int | None
    pid_running: bool = False
    pid_matches: bool = False
    socket_connectable: bool = False
    stale_reason: str | None = None
