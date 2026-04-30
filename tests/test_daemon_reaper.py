from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.daemon import run_reaper_loop
from ait.db import (
    NewAttempt,
    NewIntent,
    connect_db,
    get_attempt,
    insert_attempt,
    insert_intent,
    run_migrations,
)
from ait.events import reap_stale_attempts


class ReaperLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:", check_same_thread=False)
        run_migrations(self.conn)
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Reaper target",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker",
                trigger_source="cli",
            ),
        )
        self._insert_running_attempt(
            attempt_id="repo:01ATTEMPT",
            # Heartbeat far enough in the past that any TTL above zero
            # will mark this attempt stale.
            heartbeat_at="2000-01-01T00:00:00Z",
        )
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

    def tearDown(self) -> None:
        self.stop_event.set()
        self.conn.close()

    def test_reaper_loop_marks_stale_attempt_without_any_client(self) -> None:
        # Regression for Finding #3: the daemon used to reap only after
        # each client disconnect. An idle daemon must still reap via the
        # background timer.
        thread = threading.Thread(
            target=run_reaper_loop,
            kwargs={
                "conn": self.conn,
                "db_lock": self.lock,
                "stop_event": self.stop_event,
                "heartbeat_ttl_seconds": 1,
                "scan_interval_seconds": 0.02,
                "startup_grace_seconds": 0.0,
            },
            daemon=True,
        )
        thread.start()
        try:
            self._wait_for_status("repo:01ATTEMPT", "crashed", timeout=2.0)
        finally:
            self.stop_event.set()
            thread.join(timeout=2.0)

        attempt = get_attempt(self.conn, "repo:01ATTEMPT")
        assert attempt is not None
        self.assertEqual("crashed", attempt.reported_status)
        self.assertEqual("failed", attempt.verified_status)

    def test_reaper_loop_respects_startup_grace_period(self) -> None:
        # Regression for Finding #8: daemon restart should give legitimately
        # running harnesses a window to send a fresh heartbeat before
        # being marked crashed.
        thread = threading.Thread(
            target=run_reaper_loop,
            kwargs={
                "conn": self.conn,
                "db_lock": self.lock,
                "stop_event": self.stop_event,
                "heartbeat_ttl_seconds": 1,
                "scan_interval_seconds": 0.02,
                "startup_grace_seconds": 0.4,
            },
            daemon=True,
        )
        thread.start()
        try:
            # During the grace window the stale attempt must remain running.
            time.sleep(0.1)
            attempt = get_attempt(self.conn, "repo:01ATTEMPT")
            assert attempt is not None
            self.assertEqual("running", attempt.reported_status)
            # After grace expires, the reaper cycle marks it crashed.
            self._wait_for_status("repo:01ATTEMPT", "crashed", timeout=2.0)
        finally:
            self.stop_event.set()
            thread.join(timeout=2.0)

    def test_reaper_loop_stops_promptly_on_event(self) -> None:
        thread = threading.Thread(
            target=run_reaper_loop,
            kwargs={
                "conn": self.conn,
                "db_lock": self.lock,
                "stop_event": self.stop_event,
                "heartbeat_ttl_seconds": 1,
                "scan_interval_seconds": 5.0,
                "startup_grace_seconds": 0.0,
            },
            daemon=True,
        )
        thread.start()
        time.sleep(0.05)
        self.stop_event.set()
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())

    def test_reaper_waits_for_concurrent_writer_before_reading_stale_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.sqlite3"
            seed = connect_db(db_path)
            try:
                run_migrations(seed)
                insert_intent(
                    seed,
                    NewIntent(
                        id="repo:01FILEINTENT",
                        repo_id="repo",
                        title="File-backed reaper",
                        created_at="2026-04-23T00:00:00Z",
                        created_by_actor_type="agent",
                        created_by_actor_id="codex:worker",
                        trigger_source="cli",
                    ),
                )
                insert_attempt(
                    seed,
                    NewAttempt(
                        id="repo:01FILEATTEMPT",
                        intent_id="repo:01FILEINTENT",
                        agent_id="codex:worker",
                        workspace_ref="/tmp/reaper-file-backed",
                        base_ref_oid="0" * 40,
                        started_at="2026-04-23T00:00:00Z",
                        heartbeat_at="2000-01-01T00:00:00Z",
                        ownership_token="token",
                        reported_status="running",
                    ),
                )
            finally:
                seed.close()

            writer = connect_db(db_path)
            reaper_conn = connect_db(db_path, check_same_thread=False)
            result: list[tuple[str, ...]] = []
            try:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute(
                    """
                    UPDATE attempts
                    SET heartbeat_at = ?
                    WHERE id = ?
                    """,
                    ("2026-04-23T00:00:10Z", "repo:01FILEATTEMPT"),
                )

                thread = threading.Thread(
                    target=lambda: result.append(
                        reap_stale_attempts(
                            reaper_conn,
                            now="2026-04-23T00:00:10Z",
                            heartbeat_ttl_seconds=1,
                        )
                    ),
                    daemon=True,
                )
                thread.start()
                time.sleep(0.1)
                self.assertTrue(thread.is_alive())

                writer.commit()
                thread.join(timeout=2.0)
                self.assertFalse(thread.is_alive())
                self.assertEqual([()], result)

                attempt = get_attempt(reaper_conn, "repo:01FILEATTEMPT")
                assert attempt is not None
                self.assertEqual("running", attempt.reported_status)
                self.assertEqual("pending", attempt.verified_status)
            finally:
                if writer.in_transaction:
                    writer.rollback()
                writer.close()
                reaper_conn.close()

    def _insert_running_attempt(self, *, attempt_id: str, heartbeat_at: str) -> None:
        insert_attempt(
            self.conn,
            NewAttempt(
                id=attempt_id,
                intent_id="repo:01INTENT",
                agent_id="codex:worker",
                workspace_ref=f"/tmp/{attempt_id}",
                base_ref_oid="0" * 40,
                started_at="2026-04-23T00:00:00Z",
                ownership_token="token",
            ),
        )
        self.conn.execute(
            """
            UPDATE attempts
            SET reported_status = 'running', heartbeat_at = ?
            WHERE id = ?
            """,
            (heartbeat_at, attempt_id),
        )
        self.conn.commit()

    def _wait_for_status(self, attempt_id: str, expected: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            attempt = get_attempt(self.conn, attempt_id)
            assert attempt is not None
            if attempt.reported_status == expected:
                return
            time.sleep(0.02)
        attempt = get_attempt(self.conn, attempt_id)
        raise AssertionError(
            f"attempt {attempt_id} did not reach {expected} in {timeout}s "
            f"(last status: {attempt.reported_status if attempt else None})"
        )


if __name__ == "__main__":
    unittest.main()
