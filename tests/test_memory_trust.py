from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import init_repo
from ait.db import NewAttempt, NewIntent, NewMemoryFact, connect_db, insert_attempt, insert_attempt_commit, insert_intent, run_migrations, upsert_memory_fact
from ait.memory import build_relevant_memory_recall
from ait.review import create_deterministic_review


class MemoryTrustFixtureTests(unittest.TestCase):
    def test_false_memory_fixture_does_not_promote_candidate_or_policy_blocked_facts(self) -> None:
        self._assert_fixture("false_memory.json")

    def test_stale_memory_fixture_does_not_trust_superseded_or_expired_facts(self) -> None:
        self._assert_fixture("stale_memory.json")

    def _assert_fixture(self, filename: str) -> None:
        fixture = _load_fixture(filename)
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")
            _seed_repo(repo_root, fixture)

            recall = build_relevant_memory_recall(repo_root, str(fixture["query"]), limit=10)
            recall_ids = {item.id for item in recall.selected}

            result = create_deterministic_review(repo_root, "latest-reviewable")
            assert result.review.baseline_ref is not None
            baseline = json.loads((repo_root / result.review.baseline_ref).read_text(encoding="utf-8"))
            trusted_ids = {str(item["id"]) for item in baseline["selected_facts"]}
            excluded = {str(item["id"]): str(item["reason"]) for item in baseline["excluded_sources_summary"]}

            for fact in fixture["facts"]:
                source_id = str(fact["source_id"])
                if fact["expected_in_context"]:
                    self.assertIn(source_id, recall_ids)
                else:
                    self.assertNotIn(source_id, recall_ids)
                if fact["expected_trusted"]:
                    self.assertIn(source_id, trusted_ids)
                else:
                    self.assertNotIn(source_id, trusted_ids)
                    if str(fact["trust_level"]) in {"policy_blocked", "superseded", "stale"}:
                        self.assertIn(source_id, excluded)


def _load_fixture(filename: str) -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "memory_trust" / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    required_fixture = {"schema_version", "id", "query", "policy", "facts"}
    missing = required_fixture.difference(payload)
    if missing:
        raise AssertionError(f"{filename} missing fixture field(s): {sorted(missing)}")
    if payload["schema_version"] != 1:
        raise AssertionError(f"{filename} must use schema_version 1")
    for fact in payload["facts"]:
        required_fact = {
            "source_id",
            "status",
            "trust_level",
            "topic",
            "body",
            "expected_in_context",
            "expected_trusted",
        }
        missing_fact = required_fact.difference(fact)
        if missing_fact:
            raise AssertionError(f"{filename} fact missing field(s): {sorted(missing_fact)}")
    return payload


def _seed_repo(repo_root: Path, fixture: dict[str, object]) -> None:
    init_result = init_repo(repo_root)
    policy_path = repo_root / ".ait" / "memory-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(fixture["policy"], indent=2) + "\n", encoding="utf-8")
    conn = connect_db(init_result.db_path)
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Memory trust fixture",
                created_at="2026-05-16T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="test",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id="repo:01ATTEMPT",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref=str(repo_root / ".ait" / "workspaces" / "attempt"),
                base_ref_oid="0" * 40,
                started_at="2026-05-16T00:01:00Z",
                ownership_token="memory-trust",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid="0" * 39 + "1",
            base_commit_oid="0" * 40,
            touched_files=("src/auth.py",),
        )
        for fact in fixture["facts"]:
            upsert_memory_fact(
                conn,
                NewMemoryFact(
                    id=str(fact["source_id"]),
                    kind="rule",
                    topic=str(fact["topic"]),
                    body=str(fact["body"]),
                    summary=str(fact["body"]),
                    status=str(fact["status"]),
                    confidence="high",
                    source_trace_ref=str(fact.get("source_trace_ref") or ""),
                    source_file_path=str(fact.get("source_file_path") or "") or None,
                    valid_from="2026-05-16T00:00:00Z",
                    valid_to=str(fact.get("valid_to") or "") or None,
                    superseded_by=str(fact.get("superseded_by") or "") or None,
                    created_at="2026-05-16T00:00:00Z",
                    updated_at="2026-05-16T00:00:00Z",
                    human_review_state="approved",
                    provenance="manual",
                ),
            )
    finally:
        conn.close()


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
