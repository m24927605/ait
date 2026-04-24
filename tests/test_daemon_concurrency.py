from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.daemon import run_accept_loop
from ait.daemon_transport import bind_unix_socket, remove_socket_file
from ait.db import (
    NewAttempt,
    NewIntent,
    connect_db,
    get_evidence_summary,
    insert_attempt,
    insert_intent,
    run_migrations,
)
from ait.harness import AitHarness


class DaemonConcurrencyTests(unittest.TestCase):
    """Two harnesses must be able to stream events in parallel.

    Regression for Finding #4: the original daemon accept loop ran one
    client to completion before the next connection was even accepted,
    which directly contradicts the v1 promise of concurrent multi-agent
    attempts under one intent.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._socket_path = Path(self._tmp.name) / "daemon.sock"
        self._server = bind_unix_socket(self._socket_path)
        self.conn = connect_db(":memory:", check_same_thread=False)
        run_migrations(self.conn)
        self._seed_intent_and_attempts()
        self._db_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._accept_thread = threading.Thread(
            target=run_accept_loop,
            kwargs={
                "server": self._server,
                "conn": self.conn,
                "db_lock": self._db_lock,
                "repo_root": None,
                "stop_event": self._stop_event,
                "poll_interval_seconds": 0.05,
            },
            daemon=True,
        )
        self._accept_thread.start()

    def tearDown(self) -> None:
        self._stop_event.set()
        self._accept_thread.join(timeout=2.0)
        try:
            self._server.close()
        except Exception:
            pass
        if self._socket_path.exists():
            try:
                remove_socket_file(self._socket_path)
            except Exception:
                pass
        self.conn.close()
        self._tmp.cleanup()

    def test_two_harnesses_stream_in_parallel_without_loss(self) -> None:
        per_client_events = 20

        def run_client(attempt_id: str, token: str) -> None:
            with AitHarness.open(
                attempt_id=attempt_id,
                ownership_token=token,
                socket_path=self._socket_path,
                agent={
                    "agent_id": f"concurrent:{attempt_id[-1]}",
                    "harness": "concurrent",
                    "harness_version": "0",
                },
            ) as harness:
                for _ in range(per_client_events):
                    harness.record_tool(
                        tool_name="Read",
                        category="read",
                        duration_ms=1,
                        success=True,
                    )
                harness.finish(exit_code=0)

        t1 = threading.Thread(target=run_client, args=("repo:01ATTEMPT_A", "token-A"))
        t2 = threading.Thread(target=run_client, args=("repo:01ATTEMPT_B", "token-B"))
        t1.start()
        # Small stagger so both clients are genuinely active concurrently.
        time.sleep(0.01)
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertFalse(t1.is_alive(), "client A did not finish")
        self.assertFalse(t2.is_alive(), "client B did not finish")

        evidence_a = get_evidence_summary(self.conn, "repo:01ATTEMPT_A")
        evidence_b = get_evidence_summary(self.conn, "repo:01ATTEMPT_B")
        assert evidence_a is not None and evidence_b is not None
        # Each harness sent start + N tool_events + finish.
        # observed_tool_calls counts only tool_events.
        self.assertEqual(per_client_events, evidence_a.observed_tool_calls)
        self.assertEqual(per_client_events, evidence_b.observed_tool_calls)

    def _seed_intent_and_attempts(self) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Concurrent",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="concurrent:main",
                trigger_source="cli",
            ),
        )
        for suffix, token in (("A", "token-A"), ("B", "token-B")):
            insert_attempt(
                self.conn,
                NewAttempt(
                    id=f"repo:01ATTEMPT_{suffix}",
                    intent_id="repo:01INTENT",
                    agent_id=f"concurrent:{suffix}",
                    workspace_ref=f"/tmp/attempt-{suffix}",
                    base_ref_oid="0" * 40,
                    started_at="2026-04-23T00:00:00Z",
                    ownership_token=token,
                ),
            )


if __name__ == "__main__":
    unittest.main()
