from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from ait.config import DEFAULT_DAEMON_SOCKET_PATH, ensure_local_config
from ait.daemon_transport import NDJSONSocketStream, bind_unix_socket, remove_socket_file
from ait.db import connect_db, run_migrations
from ait.events import EventError, process_event, reap_stale_attempts, recover_running_attempts
from ait.protocol import ProtocolError, envelope_to_dict
from ait.repo import resolve_repo_root

DEFAULT_REAPER_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class DaemonStatus:
    socket_path: Path
    pid_file: Path
    running: bool
    pid: int | None


def start_daemon(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    status = daemon_status(root)
    if status.running:
        return status
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
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
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
    if status.pid is not None:
        os.kill(status.pid, signal.SIGTERM)
    if status.socket_path.exists():
        try:
            remove_socket_file(status.socket_path)
        except Exception:
            pass
    if status.pid_file.exists():
        status.pid_file.unlink()
    return daemon_status(root)


def daemon_status(repo_root: str | Path) -> DaemonStatus:
    root = resolve_repo_root(repo_root)
    socket_path = _socket_path(root)
    pid_file = _pid_file(root)
    pid = None
    running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            running = True
        except Exception:
            running = False
    return DaemonStatus(socket_path=socket_path, pid_file=pid_file, running=running and socket_path.exists(), pid=pid)


def serve_daemon(repo_root: str | Path) -> None:
    root = resolve_repo_root(repo_root)
    socket_path = _socket_path(root)
    pid_file = _pid_file(root)
    if socket_path.exists():
        remove_socket_file(socket_path)
    server = bind_unix_socket(socket_path)
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    db_path = root / ".ait" / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        recover_running_attempts(conn, now=_now(), heartbeat_ttl_seconds=_reaper_ttl(root))
        while True:
            client, _ = server.accept()
            with client:
                _handle_client(conn, client)
            reap_stale_attempts(conn, now=_now(), heartbeat_ttl_seconds=_reaper_ttl(root))
    finally:
        conn.close()
        server.close()
        if socket_path.exists():
            remove_socket_file(socket_path)
        if pid_file.exists():
            pid_file.unlink()


def _handle_client(conn, client: socket.socket) -> None:
    stream = NDJSONSocketStream(client.makefile("rwb"))
    while True:
        try:
            envelope = stream.read_envelope()
        except (ProtocolError, OSError) as exc:
            _write_response(client, {"ok": False, "error": str(exc)})
            return
        if envelope is None:
            return
        try:
            result = process_event(conn, envelope_to_dict(envelope))
            _write_response(client, {"ok": True, **result.__dict__})
        except EventError as exc:
            _write_response(client, {"ok": False, "error": str(exc)})


def _write_response(client: socket.socket, payload: dict[str, object]) -> None:
    client.sendall((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))


def _socket_path(repo_root: Path) -> Path:
    config = ensure_local_config(repo_root)
    socket_path = Path(config.daemon_socket_path or DEFAULT_DAEMON_SOCKET_PATH)
    return socket_path if socket_path.is_absolute() else (repo_root / socket_path)


def _pid_file(repo_root: Path) -> Path:
    return repo_root / ".ait" / "daemon.pid"


def _pythonpath_with_src(repo_root: Path) -> str:
    del repo_root
    src_path = str(Path(__file__).resolve().parents[1])
    existing = os.environ.get("PYTHONPATH")
    return src_path if not existing else f"{src_path}{os.pathsep}{existing}"


def _reaper_ttl(repo_root: Path) -> int:
    config = ensure_local_config(repo_root)
    return config.reaper_ttl_seconds or DEFAULT_REAPER_TTL_SECONDS


def _now() -> str:
    from ait.db.core import utc_now

    return utc_now()
