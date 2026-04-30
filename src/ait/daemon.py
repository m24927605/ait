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

from ait.config import DEFAULT_DAEMON_IDLE_TIMEOUT_SECONDS, DEFAULT_DAEMON_SOCKET_PATH, ensure_local_config
from ait.daemon_transport import NDJSONSocketStream, bind_unix_socket, remove_socket_file
from ait.db import connect_db, run_migrations
from ait.events import EventError, process_event, reap_stale_attempts, recover_running_attempts
from ait.protocol import ProtocolError, envelope_to_dict
from ait.repo import resolve_repo_root
from ait.verifier import verify_attempt

DEFAULT_REAPER_TTL_SECONDS = 300
DEFAULT_REAPER_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_REAPER_STARTUP_GRACE_SECONDS = 30.0
_VERIFIER_THREADS: list[threading.Thread] = []
_VERIFIER_THREADS_LOCK = threading.Lock()


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
    if status.pid is not None and status.pid_matches:
        os.kill(status.pid, signal.SIGTERM)
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
            recover_running_attempts(
                conn,
                now=_now(),
                heartbeat_ttl_seconds=_reaper_ttl(root),
            )
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
            idle_timeout_seconds=_daemon_idle_timeout(root),
        )
    finally:
        stop_event.set()
        if reaper_thread is not None:
            reaper_thread.join(timeout=5.0)
        _join_verifier_threads(timeout=5.0)
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
    idle_timeout_seconds: float | None = None,
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
    last_activity = time.monotonic()
    active_clients = 0
    active_clients_lock = threading.Lock()

    def run_client(client: socket.socket) -> None:
        nonlocal active_clients, last_activity
        try:
            _handle_client_safely(conn, db_lock, client, repo_root)
        finally:
            with active_clients_lock:
                active_clients -= 1
                last_activity = time.monotonic()

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            client, _ = server.accept()
        except socket.timeout:
            if idle_timeout_seconds is not None and idle_timeout_seconds > 0:
                with active_clients_lock:
                    idle = active_clients == 0 and (time.monotonic() - last_activity) >= idle_timeout_seconds
                if idle:
                    if stop_event is not None:
                        stop_event.set()
                    return
            continue
        except OSError:
            return
        with active_clients_lock:
            active_clients += 1
            last_activity = time.monotonic()
        threading.Thread(
            target=run_client,
            args=(client,),
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
    except Exception as exc:
        # Per-client errors must not crash the whole daemon.
        print(f"ait daemon client warning: {exc}", file=sys.stderr)
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
            should_verify = repo_root is not None and envelope.event_type in {
                "attempt_finished",
                "attempt_promoted",
            }
            with db_lock:
                result = process_event(conn, envelope_to_dict(envelope))
            if should_verify and not result.duplicate:
                _verify_attempt_in_background(repo_root, envelope.attempt_id)
            _write_response(client, {"ok": True, **result.__dict__})
        except EventError as exc:
            _write_response(client, {"ok": False, "error": str(exc)})
        except Exception as exc:
            _write_response(client, {"ok": False, "error": f"internal daemon error: {exc}"})


def _write_response(client: socket.socket, payload: dict[str, object]) -> None:
    try:
        client.sendall((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
    except (BrokenPipeError, ConnectionResetError, OSError):
        return


def _verify_attempt_in_background(repo_root: Path, attempt_id: str) -> threading.Thread:
    def run() -> None:
        try:
            verify_attempt(repo_root, attempt_id)
        except Exception as exc:
            # Verification can be retried by explicit `ait attempt verify`.
            print(f"ait daemon verifier warning: {exc}", file=sys.stderr)
        finally:
            current = threading.current_thread()
            with _VERIFIER_THREADS_LOCK:
                if current in _VERIFIER_THREADS:
                    _VERIFIER_THREADS.remove(current)

    thread = threading.Thread(
        target=run,
        daemon=True,
        name="ait-verifier",
    )
    with _VERIFIER_THREADS_LOCK:
        _VERIFIER_THREADS.append(thread)
    thread.start()
    return thread


def _join_verifier_threads(*, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        with _VERIFIER_THREADS_LOCK:
            threads = list(_VERIFIER_THREADS)
        if not threads:
            return
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            thread.join(timeout=remaining)
        with _VERIFIER_THREADS_LOCK:
            _VERIFIER_THREADS[:] = [
                thread for thread in _VERIFIER_THREADS if thread.is_alive()
            ]


def _socket_path(repo_root: Path) -> Path:
    config = ensure_local_config(repo_root)
    socket_path = Path(config.daemon_socket_path or DEFAULT_DAEMON_SOCKET_PATH)
    return socket_path if socket_path.is_absolute() else (repo_root / socket_path)


def _pid_file(repo_root: Path) -> Path:
    return repo_root / ".ait" / "daemon.pid"


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
