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
    get_memory_fact,
    get_memory_retrieval_event,
    insert_attempt,
    insert_attempt_commit,
    insert_evidence_file,
    insert_intent,
    insert_memory_fact_edge,
    insert_memory_retrieval_event,
    list_memory_fact_edges,
    list_memory_fact_entities,
    list_memory_facts,
    list_memory_retrieval_events,
    replace_memory_fact_entities,
    run_migrations,
    upsert_memory_fact,
)
from ait.db.repositories import (
    MemoryFactEntityRecord,
    NewAttempt,
    NewIntent,
    NewMemoryFact,
    NewMemoryFactEdge,
    NewMemoryRetrievalEvent,
)


class RepositoryTests(unittest.TestCase):
    def test_split_repository_modules_reexport_current_public_symbols(self) -> None:
        from ait.db import core_repositories, memory_repositories, records

        self.assertIs(records.NewIntent, NewIntent)
        self.assertIs(records.NewMemoryFact, NewMemoryFact)
        self.assertIs(core_repositories.insert_intent, insert_intent)
        self.assertIs(core_repositories.get_attempt, get_attempt)
        self.assertIs(memory_repositories.upsert_memory_fact, upsert_memory_fact)
        self.assertIs(memory_repositories.list_memory_facts, list_memory_facts)

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

    def test_memory_fact_round_trips_with_entities_and_filters(self) -> None:
        fact = upsert_memory_fact(
            self.conn,
            NewMemoryFact(
                id="fact:rule:1",
                kind="rule",
                topic="testing",
                body="All API routes must use zod validation.",
                summary="API routes require zod validation.",
                status="accepted",
                confidence="high",
                source_attempt_id=None,
                source_trace_ref=".ait/traces/run.txt",
                source_commit_oid="abc123",
                source_file_path="src/api/users.ts",
                valid_from="2026-04-30T00:00:00Z",
                created_at="2026-04-30T00:00:00Z",
                updated_at="2026-04-30T00:00:00Z",
            ),
        )
        replace_memory_fact_entities(
            self.conn,
            memory_fact_id=fact.id,
            entities=(
                MemoryFactEntityRecord(fact.id, "src/api/users.ts", "file", 1.0),
                MemoryFactEntityRecord(fact.id, "zod", "package", 0.8),
            ),
        )

        fetched = get_memory_fact(self.conn, fact.id)
        by_status = list_memory_facts(self.conn, status="accepted")
        by_kind = list_memory_facts(self.conn, kind="rule")
        entities = list_memory_fact_entities(self.conn, fact.id)

        assert fetched is not None
        self.assertEqual("rule", fetched.kind)
        self.assertEqual("testing", fetched.topic)
        self.assertEqual("accepted", fetched.status)
        self.assertEqual(["fact:rule:1"], [item.id for item in by_status])
        self.assertEqual(["fact:rule:1"], [item.id for item in by_kind])
        self.assertEqual(("file", "package"), tuple(item.entity_type for item in entities))

    def test_memory_fact_supersession_edge_and_default_filtering(self) -> None:
        old_fact = upsert_memory_fact(
            self.conn,
            NewMemoryFact(
                id="fact:workflow:old",
                kind="workflow",
                topic="testing",
                body="Run npm test.",
                summary="Use npm test.",
                status="accepted",
                confidence="high",
                valid_from="2026-04-29T00:00:00Z",
                created_at="2026-04-29T00:00:00Z",
                updated_at="2026-04-29T00:00:00Z",
            ),
        )
        new_fact = upsert_memory_fact(
            self.conn,
            NewMemoryFact(
                id="fact:workflow:new",
                kind="workflow",
                topic="testing",
                body="Run pnpm test.",
                summary="Use pnpm test.",
                status="accepted",
                confidence="high",
                valid_from="2026-04-30T00:00:00Z",
                created_at="2026-04-30T00:00:00Z",
                updated_at="2026-04-30T00:00:00Z",
            ),
        )
        upsert_memory_fact(
            self.conn,
            NewMemoryFact(
                id=old_fact.id,
                kind=old_fact.kind,
                topic=old_fact.topic,
                body=old_fact.body,
                summary=old_fact.summary,
                status="superseded",
                confidence=old_fact.confidence,
                valid_from=old_fact.valid_from,
                valid_to="2026-04-30T00:00:00Z",
                superseded_by=new_fact.id,
                created_at=old_fact.created_at,
                updated_at="2026-04-30T00:00:00Z",
            ),
        )
        edge = insert_memory_fact_edge(
            self.conn,
            NewMemoryFactEdge(
                id="edge:1",
                source_fact_id=new_fact.id,
                target_fact_id=old_fact.id,
                edge_type="supersedes",
                confidence="high",
                created_at="2026-04-30T00:00:00Z",
            ),
        )

        default_facts = list_memory_facts(self.conn)
        all_facts = list_memory_facts(self.conn, include_superseded=True)
        edges = list_memory_fact_edges(self.conn, source_fact_id=new_fact.id)

        self.assertEqual("supersedes", edge.edge_type)
        self.assertEqual(["fact:workflow:new"], [fact.id for fact in default_facts])
        self.assertEqual({"fact:workflow:old", "fact:workflow:new"}, {fact.id for fact in all_facts})
        self.assertEqual(["edge:1"], [item.id for item in edges])

    def test_memory_retrieval_event_round_trips_selected_fact_ids(self) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Use memory",
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
        event = insert_memory_retrieval_event(
            self.conn,
            NewMemoryRetrievalEvent(
                id="retrieval:1",
                attempt_id=attempt.id,
                query="zod validation",
                selected_fact_ids=("fact:rule:1", "fact:workflow:1"),
                ranker_version="hybrid-v1",
                budget_chars=4000,
                created_at="2026-04-30T00:00:00Z",
            ),
        )

        fetched = get_memory_retrieval_event(self.conn, event.id)
        events = list_memory_retrieval_events(self.conn, attempt_id=attempt.id)

        assert fetched is not None
        self.assertEqual(("fact:rule:1", "fact:workflow:1"), fetched.selected_fact_ids)
        self.assertEqual("hybrid-v1", fetched.ranker_version)
        self.assertEqual(["retrieval:1"], [item.id for item in events])


if __name__ == "__main__":
    unittest.main()
