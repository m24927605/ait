from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.db import (
    connect_db,
    get_attempt,
    get_evidence_summary,
    get_intent,
    insert_attempt,
    insert_attempt_commit,
    insert_evidence_file,
    insert_intent,
    run_migrations,
)
from ait.db.repositories import NewAttempt, NewIntent


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_insert_intent_round_trips_json_fields(self) -> None:
        record = insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Fix oauth expiry",
                description="Refresh token flow",
                kind="bugfix",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-1",
                trigger_source="cli",
                tags=("auth", "oauth"),
                metadata={"ticket": "ABC-123"},
            ),
        )

        fetched = get_intent(self.conn, record.id)
        assert fetched is not None
        self.assertEqual("repo:01INTENT", fetched.id)
        self.assertEqual(("auth", "oauth"), fetched.tags)
        self.assertEqual({"ticket": "ABC-123"}, fetched.metadata)
        self.assertEqual(record.id, record.root_intent_id)

    def test_insert_attempt_allocates_monotonic_ordinals_and_bootstraps_evidence(self) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Fix oauth expiry",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-1",
                trigger_source="cli",
            ),
        )

        first = insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT1",
                intent_id="repo:01INTENT",
                agent_id="codex:worker-1",
                workspace_ref="/repo/.ait/workspaces/attempt-1",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:01:00Z",
                ownership_token="token-1",
            ),
        )
        second = insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT2",
                intent_id="repo:01INTENT",
                agent_id="codex:worker-1",
                workspace_ref="/repo/.ait/workspaces/attempt-2",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:02:00Z",
                ownership_token="token-2",
            ),
        )

        self.assertEqual(1, first.ordinal)
        self.assertEqual(2, second.ordinal)
        evidence = get_evidence_summary(self.conn, first.id)
        assert evidence is not None
        self.assertEqual(0, evidence.observed_tool_calls)
        self.assertEqual(0, evidence.observed_tests_run)

    def test_insert_attempt_requires_existing_intent(self) -> None:
        with self.assertRaises(LookupError):
            insert_attempt(
                self.conn,
                NewAttempt(
                    id="repo:01ATTEMPT1",
                    intent_id="repo:missing",
                    agent_id="codex:worker-1",
                    workspace_ref="/repo/.ait/workspaces/attempt-1",
                    base_ref_oid="abc123",
                    started_at="2026-04-23T00:01:00Z",
                    ownership_token="token-1",
                ),
            )

    def test_commit_and_evidence_helpers_write_index_tables(self) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Fix oauth expiry",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-1",
                trigger_source="cli",
            ),
        )
        attempt = insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT1",
                intent_id="repo:01INTENT",
                agent_id="codex:worker-1",
                workspace_ref="/repo/.ait/workspaces/attempt-1",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:01:00Z",
                ownership_token="token-1",
            ),
        )

        insert_attempt_commit(
            self.conn,
            attempt_id=attempt.id,
            commit_oid="def456",
            base_commit_oid="abc123",
            touched_files=("src/auth.ts",),
            insertions=10,
            deletions=2,
        )
        insert_evidence_file(
            self.conn,
            attempt_id=attempt.id,
            file_path="src/auth.ts",
            kind="touched",
        )

        commit_row = self.conn.execute(
            "SELECT * FROM attempt_commits WHERE attempt_id = ?",
            (attempt.id,),
        ).fetchone()
        file_row = self.conn.execute(
            "SELECT * FROM evidence_files WHERE attempt_id = ?",
            (attempt.id,),
        ).fetchone()
        fetched_attempt = get_attempt(self.conn, attempt.id)
        assert fetched_attempt is not None

        self.assertEqual("def456", commit_row["commit_oid"])
        self.assertEqual("src/auth.ts", file_row["file_path"])
        self.assertEqual("token-1", fetched_attempt.ownership_token)


if __name__ == "__main__":
    unittest.main()
