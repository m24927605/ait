from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import threading

from ait.daemon_state import _now
from ait.events import reap_stale_attempts
from ait.memory_policy import load_memory_policy
from ait.transcript_store import prune_transcripts


def run_reaper_loop(
    *,
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    stop_event: threading.Event,
    heartbeat_ttl_seconds: int,
    scan_interval_seconds: float,
    startup_grace_seconds: float,
    repo_root: Path | None = None,
) -> None:
    """Run the reaper on a timer until stop_event is set."""
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
        except Exception as exc:
            print(f"ait daemon reaper warning: {exc}", file=sys.stderr, flush=True)
        if repo_root is not None:
            try:
                policy = load_memory_policy(repo_root)
                prune_transcripts(repo_root, policy=policy)
            except Exception as exc:
                print(
                    f"ait daemon transcript prune warning: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        if stop_event.wait(scan_interval_seconds):
            return
