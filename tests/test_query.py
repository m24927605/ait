from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.db import (
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_evidence_file,
    insert_intent,
    run_migrations,
)
from ait.db.repositories import NewAttempt, NewIntent
from ait.query import (
    BinaryExpression,
    BlameTarget,
    Comparison,
    QueryError,
    blame_path,
    compile_query,
    execute_query,
    parse_blame_target,
    parse_query,
)


class QueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)
        self._seed_fixture()

    def tearDown(self) -> None:
        self.conn.close()

    def test_parse_query_builds_expression_tree(self) -> None:
        expression = parse_query('kind="bugfix" AND observed.tool_calls>0')

        self.assertIsInstance(expression, BinaryExpression)
        self.assertEqual("AND", expression.operator)
        self.assertEqual(
            Comparison(field="kind", operator="=", value="bugfix"),
            expression.left,
        )

    def test_attempt_query_joins_intent_evidence_and_indexed_file_filters(self) -> None:
        rows = execute_query(
            self.conn,
            "attempt",
            'kind="bugfix" AND observed.tool_calls>0 AND files_touched~"src/auth/"',
        )

        self.assertEqual(["repo:attempt-1"], [row["id"] for row in rows])

    def test_intent_query_uses_exists_semantics_for_attempt_fields(self) -> None:
        rows = execute_query(
            self.conn,
            "intent",
            'reported_status="finished" AND observed.build_passed=true',
        )

        self.assertEqual(["repo:intent-1"], [row["id"] for row in rows])

    def test_query_supports_or_not_and_in(self) -> None:
        rows = execute_query(
            self.conn,
            "attempt",
            'NOT verified_status="failed" AND agent.agent_id IN ("codex:worker-1", "codex:worker-9") AND (kind="bugfix" OR kind="chore")',
        )

        self.assertEqual(["repo:attempt-1"], [row["id"] for row in rows])

    def test_query_rejects_non_whitelisted_field(self) -> None:
        with self.assertRaises(QueryError):
            compile_query("attempt", 'metadata.ticket="ABC-123"')

    def test_query_uses_case_sensitive_substring_operator(self) -> None:
        rows = execute_query(self.conn, "attempt", 'files_touched~"src/Auth/"')

        self.assertEqual([], rows)

    def test_blame_path_reads_indexed_metadata_only(self) -> None:
        blame_rows = blame_path(self.conn, "src/auth/session.py")

        self.assertEqual(1, len(blame_rows))
        self.assertEqual("repo:attempt-1", blame_rows[0].attempt_id)
        self.assertEqual("changed", blame_rows[0].file_kind)
        self.assertEqual("def456", blame_rows[0].commit_oid)

    def test_parse_blame_target_supports_optional_line_suffix(self) -> None:
        self.assertEqual(
            BlameTarget(path="src/auth/session.py", line=42),
            parse_blame_target("src/auth/session.py:42"),
        )
        self.assertEqual(
            BlameTarget(path="src/auth/session.py", line=None),
            parse_blame_target("src/auth/session.py"),
        )

    def _seed_fixture(self) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:intent-1",
                repo_id="repo",
                title="Fix auth session",
                kind="bugfix",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-1",
                trigger_source="cli",
                tags=("auth", "session"),
            ),
        )
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:intent-2",
                repo_id="repo",
                title="Update docs",
                kind="docs",
                created_at="2026-04-23T01:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:worker-2",
                trigger_source="cli",
                tags=("docs",),
            ),
        )
        attempt_1 = insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:attempt-1",
                intent_id="repo:intent-1",
                agent_id="codex:worker-1",
                workspace_ref="/repo/.ait/workspaces/attempt-1",
                base_ref_oid="abc123",
                started_at="2026-04-23T00:10:00Z",
                ownership_token="token-1",
                reported_status="finished",
                verified_status="pending",
                agent_harness="codex",
            ),
        )
        attempt_2 = insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:attempt-2",
                intent_id="repo:intent-2",
                agent_id="codex:worker-2",
                workspace_ref="/repo/.ait/workspaces/attempt-2",
                base_ref_oid="abc123",
                started_at="2026-04-23T01:10:00Z",
                ownership_token="token-2",
                reported_status="running",
                verified_status="failed",
                agent_harness="codex",
            ),
        )

        self.conn.execute(
            """
            UPDATE evidence_summaries
            SET observed_tool_calls = ?,
                observed_file_reads = ?,
                observed_file_writes = ?,
                observed_commands_run = ?,
                observed_build_passed = ?
            WHERE attempt_id = ?
            """,
            (3, 1, 1, 1, 1, attempt_1.id),
        )
        self.conn.execute(
            """
            UPDATE evidence_summaries
            SET observed_tool_calls = ?,
                observed_file_reads = ?,
                observed_file_writes = ?,
                observed_commands_run = ?,
                observed_build_passed = ?
            WHERE attempt_id = ?
            """,
            (0, 2, 0, 0, 0, attempt_2.id),
        )

        insert_evidence_file(
            self.conn,
            attempt_id=attempt_1.id,
            file_path="src/auth/session.py",
            kind="touched",
        )
        insert_evidence_file(
            self.conn,
            attempt_id=attempt_1.id,
            file_path="src/auth/session.py",
            kind="changed",
        )
        insert_evidence_file(
            self.conn,
            attempt_id=attempt_2.id,
            file_path="docs/runbook.md",
            kind="touched",
        )
        insert_attempt_commit(
            self.conn,
            attempt_id=attempt_1.id,
            commit_oid="def456",
            base_commit_oid="abc123",
            touched_files=("src/auth/session.py",),
        )
        self.conn.commit()


if __name__ == "__main__":
    unittest.main()
