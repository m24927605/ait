from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time

from ait.config import DEFAULT_DAEMON_IDLE_TIMEOUT_SECONDS, DEFAULT_DAEMON_SOCKET_PATH, ensure_local_config
from ait.daemon_models import DaemonStatus
from ait.daemon_transport import remove_socket_file

DEFAULT_REAPER_TTL_SECONDS = 300


def _socket_path(repo_root: Path) -> Path:
    config = ensure_local_config(repo_root)
    socket_path = Path(config.daemon_socket_path or DEFAULT_DAEMON_SOCKET_PATH)
    return socket_path if socket_path.is_absolute() else (repo_root / socket_path)


def _pid_file(repo_root: Path) -> Path:
    return repo_root / ".ait" / "daemon.pid"


def _write_pid_file(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = pid_file.with_name(f"{pid_file.name}.{os.getpid()}.tmp")
    tmp_path.write_text(f"{pid}\n", encoding="utf-8")
    os.replace(tmp_path, pid_file)


def _wait_for_pid_exit(pid: int, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def _cleanup_stale_daemon_state(status: DaemonStatus) -> None:
    if status.running:
        return
    if status.pid_file.exists() and not status.pid_matches:
        try:
            status.pid_file.unlink()
        except OSError:
            pass
    if status.socket_path.exists() and not status.socket_connectable:
        try:
            if status.socket_path.is_socket():
                remove_socket_file(status.socket_path)
            elif status.socket_path.is_file() or status.socket_path.is_symlink():
                status.socket_path.unlink()
        except OSError:
            pass


def _daemon_stale_reason(
    *,
    socket_path: Path,
    pid_file: Path,
    pid: int | None,
    pid_running: bool,
    pid_matches: bool,
    socket_connectable: bool,
) -> str | None:
    if socket_connectable and (pid is None or not pid_file.exists() or pid_matches):
        return None
    if pid_file.exists() and pid is None:
        return "pid_file_invalid"
    if pid is not None and not pid_running:
        return "pid_not_running"
    if pid_running and not pid_matches:
        return "pid_not_ait_daemon"
    if socket_path.exists() and not socket_connectable:
        return "socket_not_connectable"
    if pid_matches and not socket_connectable:
        return "socket_missing_or_not_connectable"
    return None


def _socket_connectable(socket_path: Path) -> bool:
    import socket

    if not socket_path.exists() or not socket_path.is_socket():
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(0.2)
        client.connect(str(socket_path))
        return True
    except OSError:
        return False
    finally:
        client.close()


def _pid_matches_ait_daemon(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return False
    command = _pid_command(pid)
    if not command:
        return False
    normalized = " ".join(command.split())
    return (
        "daemon serve" in normalized
        and ("ait.cli" in normalized or "/ait" in normalized or " ait " in f" {normalized} ")
    )


def _pid_command(pid: int) -> str:
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        if proc_cmdline.exists():
            return proc_cmdline.read_text(encoding="utf-8", errors="replace").replace("\x00", " ")
    except OSError:
        pass
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _pythonpath_with_src(repo_root: Path) -> str:
    del repo_root
    src_path = str(Path(__file__).resolve().parents[1])
    existing = os.environ.get("PYTHONPATH")
    return src_path if not existing else f"{src_path}{os.pathsep}{existing}"


def _reaper_ttl(repo_root: Path) -> int:
    config = ensure_local_config(repo_root)
    return config.reaper_ttl_seconds or DEFAULT_REAPER_TTL_SECONDS


def _daemon_idle_timeout(repo_root: Path) -> int:
    config = ensure_local_config(repo_root)
    return config.daemon_idle_timeout_seconds or DEFAULT_DAEMON_IDLE_TIMEOUT_SECONDS


def _now() -> str:
    from ait.db.core import utc_now

    return utc_now()
