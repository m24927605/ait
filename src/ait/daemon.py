from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import sys
import threading
import time

from ait.bug_report.api import report_internal_error
from ait.daemon_lifecycle import daemon_status, prune_daemon, start_daemon, stop_daemon
from ait.daemon_models import DaemonStatus
from ait.daemon_reaper import run_reaper_loop
from ait.daemon_state import (
    DEFAULT_REAPER_TTL_SECONDS,
    _cleanup_stale_daemon_state,
    _daemon_idle_timeout,
    _daemon_stale_reason,
    _now,
    _pid_command,
    _pid_file,
    _pid_matches_ait_daemon,
    _pythonpath_with_src,
    _reaper_ttl,
    _socket_connectable,
    _socket_path,
    _wait_for_pid_exit,
    _write_pid_file,
)
from ait.daemon_transport import NDJSONSocketStream, bind_unix_socket, remove_socket_file
from ait.db import connect_db, run_migrations
from ait.events import EventError, process_event, recover_running_attempts
from ait.protocol import ProtocolError, envelope_to_dict
from ait.repo import resolve_repo_root
from ait.transcript_summarizer import summarize_attempt_transcript
from ait.verifier import verify_attempt

DEFAULT_REAPER_SCAN_INTERVAL_SECONDS = 30.0
DEFAULT_REAPER_STARTUP_GRACE_SECONDS = 30.0
_VERIFIER_THREADS: list[threading.Thread] = []
_VERIFIER_THREADS_LOCK = threading.Lock()


def serve_daemon(repo_root: str | Path) -> None:
    root = resolve_repo_root(repo_root)
    socket_path = _socket_path(root)
    pid_file = _pid_file(root)
    if socket_path.exists():
        remove_socket_file(socket_path)
    server = bind_unix_socket(socket_path)
    _write_pid_file(pid_file, os.getpid())
    db_path = root / ".ait" / "state.sqlite3"
    conn = connect_db(db_path, check_same_thread=False)
    db_lock = threading.Lock()
    stop_event = threading.Event()
    previous_signal_handlers = _install_stop_signal_handlers(stop_event)
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
                "repo_root": root,
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
        _restore_signal_handlers(previous_signal_handlers)


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
    """Accept client connections and hand each off to its own worker thread."""
    if stop_event is not None or idle_timeout_seconds is not None:
        server.settimeout(poll_interval_seconds)
    last_activity = time.monotonic()
    active_clients = 0
    active_clients_lock = threading.Lock()
    client_threads: list[threading.Thread] = []

    def finish_loop() -> None:
        deadline = time.monotonic() + 5.0
        for thread in list(client_threads):
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)

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
            finish_loop()
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
                    finish_loop()
                    return
            continue
        except OSError:
            finish_loop()
            return
        with active_clients_lock:
            active_clients += 1
            last_activity = time.monotonic()
        thread = threading.Thread(
            target=run_client,
            args=(client,),
            daemon=True,
            name="ait-client",
        )
        client_threads.append(thread)
        thread.start()


def _handle_client_safely(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    client: socket.socket,
    repo_root: Path | None,
) -> None:
    try:
        _handle_client(conn, db_lock, client, repo_root)
    except Exception as exc:
        print(f"ait daemon client warning: {exc}", file=sys.stderr, flush=True)
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
            report_internal_error(category="daemon.protocol.main", exc=exc)
            _write_response(client, {"ok": False, "error": str(exc)})
            return
        if envelope is None:
            return
        try:
            should_verify = repo_root is not None and envelope.event_type in {
                "attempt_finished",
                "attempt_promoted",
            }
            should_summarize = repo_root is not None and envelope.event_type == "attempt_finished"
            with db_lock:
                result = process_event(conn, envelope_to_dict(envelope))
            if should_verify and not result.duplicate:
                _verify_attempt_in_background(repo_root, envelope.attempt_id)
            if should_summarize and not result.duplicate:
                _summarize_attempt_in_background(repo_root, envelope.attempt_id)
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
            print(f"ait daemon verifier warning: {exc}", file=sys.stderr, flush=True)
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


def _summarize_attempt_in_background(repo_root: Path, attempt_id: str) -> threading.Thread:
    def run() -> None:
        try:
            summarize_attempt_transcript(repo_root, attempt_id)
        except Exception as exc:
            print(
                f"ait daemon summarizer warning: {exc}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            current = threading.current_thread()
            with _VERIFIER_THREADS_LOCK:
                if current in _VERIFIER_THREADS:
                    _VERIFIER_THREADS.remove(current)

    thread = threading.Thread(
        target=run,
        daemon=True,
        name="ait-summarizer",
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


def _install_stop_signal_handlers(
    stop_event: threading.Event,
) -> dict[int, signal.Handlers] | None:
    if threading.current_thread() is not threading.main_thread():
        return None
    previous: dict[int, signal.Handlers] = {}

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)
    return previous


def _restore_signal_handlers(previous: dict[int, signal.Handlers] | None) -> None:
    if previous is None:
        return
    for signum, handler in previous.items():
        signal.signal(signum, handler)
