from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time

from ait.config import DEFAULT_DAEMON_SOCKET_PATH, ensure_local_config
from ait.daemon_transport import NDJSONSocketStream, bind_unix_socket, remove_socket_file
from ait.db import connect_db, run_migrations
from ait.events import EventError, process_event, reap_stale_attempts
from ait.protocol import ProtocolError, envelope_to_dict
from ait.repo import resolve_repo_root
from ait.verifier import verify_attempt_with_connection

DEFAULT_REAPER_TTL_SECONDS = 300
DEFAULT_REAPER_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_REAPER_STARTUP_GRACE_SECONDS = 30.0


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
    conn = connect_db(db_path, check_same_thread=False)
    db_lock = threading.Lock()
    stop_event = threading.Event()
    reaper_thread: threading.Thread | None = None
    try:
        with db_lock:
            run_migrations(conn)
        reaper_thread = threading.Thread(
            target=run_reaper_loop,
            kwargs={
                "conn": conn,
                "db_lock": db_lock,
                "stop_event": stop_event,
                "heartbeat_ttl_seconds": _reaper_ttl(root),
                "scan_interval_seconds": DEFAULT_REAPER_SCAN_INTERVAL_SECONDS,
                "startup_grace_seconds": DEFAULT_REAPER_STARTUP_GRACE_SECONDS,
            },
            daemon=True,
            name="ait-reaper",
        )
        reaper_thread.start()
        run_accept_loop(
            server=server,
            conn=conn,
            db_lock=db_lock,
            repo_root=root,
            stop_event=stop_event,
        )
    finally:
        stop_event.set()
        if reaper_thread is not None:
            reaper_thread.join(timeout=5.0)
        conn.close()
        server.close()
        if socket_path.exists():
            remove_socket_file(socket_path)
        if pid_file.exists():
            pid_file.unlink()


def run_reaper_loop(
    *,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    stop_event: threading.Event,
    heartbeat_ttl_seconds: int,
    scan_interval_seconds: float,
    startup_grace_seconds: float,
) -> None:
    """Run the reaper on a timer until stop_event is set.

    Startup grace: give attempts in `reported_status='running'` one full
    `startup_grace_seconds` window to send a fresh heartbeat before the
    first reap cycle. This prevents daemon-restart from immediately
    killing harnesses whose last heartbeat happened to predate the
    restart by more than one TTL.
    """
    if stop_event.wait(startup_grace_seconds):
        return
    while True:
        try:
            with db_lock:
                reap_stale_attempts(
                    conn,
                    now=_now(),
                    heartbeat_ttl_seconds=heartbeat_ttl_seconds,
                )
        except Exception:
            # Transient errors (e.g. sqlite OperationalError during
            # contention) must not kill the reaper thread.
            pass
        if stop_event.wait(scan_interval_seconds):
            return


def run_accept_loop(
    *,
    server: socket.socket,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    repo_root: Path | None,
    stop_event: threading.Event | None = None,
    poll_interval_seconds: float = 0.1,
) -> None:
    """Accept client connections and hand each off to its own worker thread.

    One thread per client so multiple harnesses can stream events in
    parallel without queueing behind each other. Writes against the
    shared SQLite connection are serialised via ``db_lock``.

    If ``stop_event`` is supplied the server socket is put into
    ``poll_interval_seconds`` timeout mode so the loop can periodically
    notice shutdown requests. Production ``serve_daemon`` uses this to
    cleanly unwind when the process is asked to exit; tests use it to
    shut down a test loop.
    """
    if stop_event is not None:
        server.settimeout(poll_interval_seconds)
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            client, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        threading.Thread(
            target=_handle_client_safely,
            args=(conn, db_lock, client, repo_root),
            daemon=True,
            name="ait-client",
        ).start()


def _handle_client_safely(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    client: socket.socket,
    repo_root: Path | None,
) -> None:
    try:
        _handle_client(conn, db_lock, client, repo_root)
    except Exception:
        # Per-client errors must not crash the whole daemon.
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass


def _handle_client(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    client: socket.socket,
    repo_root: Path | None = None,
) -> None:
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
            with db_lock:
                result = process_event(conn, envelope_to_dict(envelope))
                if repo_root is not None and envelope.event_type in {
                    "attempt_finished",
                    "attempt_promoted",
                }:
                    verify_attempt_with_connection(conn, repo_root, envelope.attempt_id)
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
