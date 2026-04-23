from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.db import connect_db, get_attempt, get_evidence_summary, insert_attempt, insert_intent, run_migrations
from ait.db.repositories import NewAttempt, NewIntent
from ait.events import (
    EventConflictError,
    EventOwnershipError,
    process_event,
    reap_stale_attempts,
)


class EventProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Fix oauth expiry",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-5",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT1",
                intent_id="repo:01INTENT",
                agent_id="codex:worker-5",
                workspace_ref="/repo/.ait/workspaces/attempt-1",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:01:00Z",
                ownership_token="token-1",
            ),
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_attempt_started_sets_running_status_and_agent_metadata(self) -> None:
        result = process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT1",
                "event_type": "attempt_started",
                "sent_at": "2026-04-23T00:02:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {
                    "agent": {
                        "agent_id": "codex:worker-5",
                        "model": "gpt-5",
                        "harness": "codex",
                        "harness_version": "1.0.0",
                    }
                },
            },
        )

        attempt = get_attempt(self.conn, "repo:01ATTEMPT1")
        assert attempt is not None
        self.assertFalse(result.duplicate)
        self.assertTrue(result.mutated)
        self.assertEqual("running", attempt.reported_status)
        self.assertEqual("2026-04-23T00:02:00Z", attempt.heartbeat_at)
        self.assertEqual("gpt-5", attempt.agent_model)
        self.assertEqual("codex", attempt.agent_harness)
        intent_row = self.conn.execute(
            "SELECT status FROM intents WHERE id = ?",
            ("repo:01INTENT",),
        ).fetchone()
        self.assertEqual("running", intent_row["status"])

    def test_tool_event_updates_counters_files_and_dedupes_event_id(self) -> None:
        first = process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT2",
                "event_type": "tool_event",
                "sent_at": "2026-04-23T00:03:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {
                    "tool_name": "Read",
                    "category": "read",
                    "duration_ms": 42,
                    "files": [
                        {"path": "src/auth.ts", "access": "read"},
                        {"path": "src/session.ts", "access": "write"},
                    ],
                },
            },
        )
        second = process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT2",
                "event_type": "tool_event",
                "sent_at": "2026-04-23T00:03:01Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {
                    "tool_name": "Read",
                    "category": "read",
                    "duration_ms": 42,
                    "files": [{"path": "src/auth.ts", "access": "read"}],
                },
            },
        )

        evidence = get_evidence_summary(self.conn, "repo:01ATTEMPT1")
        assert evidence is not None
        file_rows = self.conn.execute(
            """
            SELECT file_path, kind
            FROM evidence_files
            WHERE attempt_id = ?
            ORDER BY file_path, kind
            """,
            ("repo:01ATTEMPT1",),
        ).fetchall()

        self.assertTrue(first.mutated)
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(1, evidence.observed_tool_calls)
        self.assertEqual(1, evidence.observed_file_reads)
        self.assertEqual(0, evidence.observed_file_writes)
        self.assertEqual(42, evidence.observed_duration_ms)
        self.assertEqual(
            [("src/auth.ts", "read"), ("src/session.ts", "touched")],
            [(row["file_path"], row["kind"]) for row in file_rows],
        )

    def test_invalid_ownership_token_is_rejected(self) -> None:
        with self.assertRaises(EventOwnershipError):
            process_event(
                self.conn,
                {
                    "schema_version": 1,
                    "event_id": "repo:01EVENT3",
                    "event_type": "attempt_heartbeat",
                    "sent_at": "2026-04-23T00:04:00Z",
                    "attempt_id": "repo:01ATTEMPT1",
                    "ownership_token": "wrong-token",
                    "payload": {},
                },
            )

    def test_attempt_finished_updates_terminal_fields_and_evidence_refs(self) -> None:
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT4",
                "event_type": "attempt_finished",
                "sent_at": "2026-04-23T00:05:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {
                    "exit_code": 0,
                    "raw_trace_ref": ".ait/objects/trace",
                    "logs_ref": ".ait/objects/logs",
                },
            },
        )

        attempt = get_attempt(self.conn, "repo:01ATTEMPT1")
        evidence = get_evidence_summary(self.conn, "repo:01ATTEMPT1")
        assert attempt is not None
        assert evidence is not None
        self.assertEqual("finished", attempt.reported_status)
        self.assertEqual("2026-04-23T00:05:00Z", attempt.ended_at)
        self.assertEqual(0, attempt.result_exit_code)
        self.assertEqual(".ait/objects/trace", evidence.raw_trace_ref)
        self.assertEqual(".ait/objects/logs", evidence.logs_ref)

    def test_promoted_then_discarded_is_a_no_op_for_discard(self) -> None:
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT5",
                "event_type": "attempt_promoted",
                "sent_at": "2026-04-23T00:06:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"promotion_ref": "refs/heads/fix/oauth-expiry", "commit_oids": ["abc123"]},
            },
        )
        result = process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT6",
                "event_type": "attempt_discarded",
                "sent_at": "2026-04-23T00:07:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"reason": "user-requested"},
            },
        )

        attempt = get_attempt(self.conn, "repo:01ATTEMPT1")
        assert attempt is not None
        self.assertFalse(result.duplicate)
        self.assertTrue(result.mutated)
        self.assertEqual("discarded", attempt.verified_status)
        self.assertEqual("refs/heads/fix/oauth-expiry", attempt.result_promotion_ref)
        intent_row = self.conn.execute(
            "SELECT status FROM intents WHERE id = ?",
            ("repo:01INTENT",),
        ).fetchone()
        self.assertEqual("open", intent_row["status"])

    def test_promoting_a_discarded_attempt_conflicts(self) -> None:
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT7",
                "event_type": "attempt_discarded",
                "sent_at": "2026-04-23T00:08:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"reason": "user-requested"},
            },
        )

        with self.assertRaises(EventConflictError):
            process_event(
                self.conn,
                {
                    "schema_version": 1,
                    "event_id": "repo:01EVENT8",
                    "event_type": "attempt_promoted",
                    "sent_at": "2026-04-23T00:09:00Z",
                    "attempt_id": "repo:01ATTEMPT1",
                    "ownership_token": "token-1",
                    "payload": {"promotion_ref": "refs/heads/fix/oauth-expiry"},
                },
            )

    def test_reaper_marks_only_stale_running_attempts_crashed(self) -> None:
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT9",
                "event_type": "attempt_started",
                "sent_at": "2026-04-23T00:02:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"agent": {"agent_id": "codex:worker-5"}},
            },
        )
        insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT2",
                intent_id="repo:01INTENT",
                agent_id="codex:worker-5",
                workspace_ref="/repo/.ait/workspaces/attempt-2",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:10:00Z",
                heartbeat_at="2026-04-23T00:10:31Z",
                ownership_token="token-2",
                reported_status="running",
            ),
        )

        stale_ids = reap_stale_attempts(
            self.conn,
            now="2026-04-23T00:12:00Z",
            heartbeat_ttl_seconds=90,
        )

        stale_attempt = get_attempt(self.conn, "repo:01ATTEMPT1")
        fresh_attempt = get_attempt(self.conn, "repo:01ATTEMPT2")
        assert stale_attempt is not None
        assert fresh_attempt is not None
        self.assertEqual(("repo:01ATTEMPT1",), stale_ids)
        self.assertEqual("crashed", stale_attempt.reported_status)
        self.assertEqual("failed", stale_attempt.verified_status)
        self.assertEqual("running", fresh_attempt.reported_status)

    def test_discard_does_not_regress_running_intent_back_to_open(self) -> None:
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT10",
                "event_type": "attempt_started",
                "sent_at": "2026-04-23T00:02:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"agent": {"agent_id": "codex:worker-5"}},
            },
        )
        process_event(
            self.conn,
            {
                "schema_version": 1,
                "event_id": "repo:01EVENT11",
                "event_type": "attempt_discarded",
                "sent_at": "2026-04-23T00:08:00Z",
                "attempt_id": "repo:01ATTEMPT1",
                "ownership_token": "token-1",
                "payload": {"reason": "user-requested"},
            },
        )

        intent_row = self.conn.execute(
            "SELECT status FROM intents WHERE id = ?",
            ("repo:01INTENT",),
        ).fetchone()
        # Forward-only transitions: once the intent has reached running, it
        # must not fall back to open simply because every active attempt
        # was discarded. The user must explicitly abandon or supersede.
        self.assertEqual("running", intent_row["status"])


if __name__ == "__main__":
    unittest.main()
