from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from ait.daemon_models import DaemonStatus
from ait.daemon_state import (
    _cleanup_stale_daemon_state,
    _daemon_stale_reason,
    _pid_file,
    _pid_matches_ait_daemon,
    _pythonpath_with_src,
    _socket_connectable,
    _socket_path,
    _wait_for_pid_exit,
    _write_pid_file,
)
from ait.daemon_transport import remove_socket_file
from ait.repo import resolve_repo_root

_STARTED_DAEMON_PROCESSES: dict[int, subprocess.Popen] = {}


def start_daemon(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    status = daemon_status(root)
    if status.running:
        return status
    _cleanup_stale_daemon_state(status)
    process = subprocess.Popen(
        [sys.executable, "-m", "ait.cli", "daemon", "serve"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "PYTHONPATH": _pythonpath_with_src(root)},
    )
    pid_file = _pid_file(root)
    _write_pid_file(pid_file, process.pid)
    _STARTED_DAEMON_PROCESSES[process.pid] = process
    for _ in range(50):
        status = daemon_status(root)
        if status.running:
            return status
        if process.poll() is not None:
            break
        time.sleep(0.1)
    return daemon_status(root)


def stop_daemon(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    status = daemon_status(root)
    if status.pid is not None and status.pid_matches:
        os.kill(status.pid, signal.SIGTERM)
        process = _STARTED_DAEMON_PROCESSES.pop(status.pid, None)
        if process is not None:
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        elif not _wait_for_pid_exit(status.pid, timeout=5.0):
            try:
                os.kill(status.pid, signal.SIGKILL)
            except OSError:
                pass
            _wait_for_pid_exit(status.pid, timeout=2.0)
    if status.socket_path.exists():
        try:
            remove_socket_file(status.socket_path)
        except Exception:
            pass
    if status.pid_file.exists():
        status.pid_file.unlink()
    return daemon_status(root)


def prune_daemon(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    status = daemon_status(root)
    _cleanup_stale_daemon_state(status)
    return daemon_status(root)


def daemon_status(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    socket_path = _socket_path(root)
    pid_file = _pid_file(root)
    pid = None
    pid_running = False
    pid_matches = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            pid_running = True
            pid_matches = _pid_matches_ait_daemon(pid)
        except Exception:
            pid_running = False
            pid_matches = False
    socket_connectable = _socket_connectable(socket_path)
    stale_reason = _daemon_stale_reason(
        socket_path=socket_path,
        pid_file=pid_file,
        pid=pid,
        pid_running=pid_running,
        pid_matches=pid_matches,
        socket_connectable=socket_connectable,
    )
    running = socket_connectable and (pid is None or not pid_file.exists() or pid_matches)
    return DaemonStatus(
        socket_path=socket_path,
        pid_file=pid_file,
        running=running,
        pid=pid if pid_running else None,
        pid_running=pid_running,
        pid_matches=pid_matches,
        socket_connectable=socket_connectable,
        stale_reason=stale_reason,
    )
