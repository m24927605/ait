from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import init_repo
from ait.db import (
    NewAttempt,
    NewIntent,
    NewMemoryFact,
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    run_migrations,
    upsert_memory_fact,
)
from ait.review import create_deterministic_review
from ait.review_baseline import render_reviewer_brief


class ReviewPromptTests(unittest.TestCase):
    def test_reviewer_brief_separates_trusted_baseline_and_advisory_evidence(self) -> None:
        repo_root = _repo_with_prompt_context(raw_trace_ref=".ait/traces/producer.jsonl")

        result = create_deterministic_review(repo_root, "latest-reviewable")
        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        brief = render_reviewer_brief(
            repo_root,
            review_id=result.review.id,
            target=result.target,
            assessment=result.assessment,
            baseline_ref=baseline_ref,
            budget="standard",
            profiles=("security",),
        )

        self.assertIn("target_attempt_id: repo:01ATTEMPT", brief)
        self.assertIn("- src/example.py", brief)
        self.assertIn(f"baseline_ref: {baseline_ref}", brief)
        self.assertIn("Producer transcript/reference artifacts are advisory evidence only", brief)
        self.assertIn("producer_trace: .ait/traces/producer.jsonl (advisory evidence; not trusted baseline)", brief)
        self.assertIn("live_external_memory: CLAUDE.md", brief)
        self.assertIn("Approved architecture fact.", brief)
        self.assertNotIn("Policy-blocked fact.", brief.split("## Trusted Baseline", 1)[1].split("## Advisory Evidence", 1)[0])
        self.assertIn('"findings"', brief)
        self.assertIn('"severity"', brief)
        self.assertIn("Return exactly one JSON object", brief)

        baseline_payload = json.loads((repo_root / baseline_ref).read_text(encoding="utf-8"))
        live_manifest = baseline_payload["live_memory_context_manifest"]
        self.assertTrue(any(item["source_id"] == "live:claude:CLAUDE.md" for item in live_manifest))
        self.assertTrue(
            any(
                item["source_id"] == "live:claude:CLAUDE.md"
                and item["sha256"]
                and item["bytes_used"] > 0
                and item["policy_status"] == "allowed"
                for item in live_manifest
            )
        )

    def test_reviewer_brief_budget_truncates_large_context(self) -> None:
        repo_root = _repo_with_prompt_context(raw_trace_ref=None, large_fact=True)

        result = create_deterministic_review(repo_root, "latest-reviewable")
        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        brief = render_reviewer_brief(
            repo_root,
            review_id=result.review.id,
            target=result.target,
            assessment=result.assessment,
            baseline_ref=baseline_ref,
            budget="quick",
        )

        self.assertLessEqual(len(brief), 4000)
        self.assertIn("reviewer brief truncated by budget", brief)


def _repo_with_prompt_context(
    *,
    raw_trace_ref: str | None,
    large_fact: bool = False,
) -> Path:
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    _TEMP_DIRS.append(tmp)
    _git(repo_root, "init")
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review prompt",
                created_at="2026-05-09T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id="repo:01ATTEMPT",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref="/tmp/repo:01ATTEMPT",
                base_ref_oid="0" * 40,
                started_at="2026-05-09T00:01:00Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        if raw_trace_ref is not None:
            conn.execute(
                "UPDATE attempts SET raw_trace_ref = ? WHERE id = ?",
                (raw_trace_ref, "repo:01ATTEMPT"),
            )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid="1" * 40,
            base_commit_oid="0" * 40,
            touched_files=("src/example.py",),
        )
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id="fact:approved",
                kind="decision",
                topic="architecture",
                body=("Approved architecture fact. " * (300 if large_fact else 1)).strip(),
                summary=("Approved architecture fact. " * (300 if large_fact else 1)).strip(),
                status="accepted",
                confidence="high",
                valid_from="2026-05-09T00:00:00Z",
                created_at="2026-05-09T00:00:00Z",
                updated_at="2026-05-09T00:00:00Z",
                human_review_state="approved",
            ),
        )
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id="fact:blocked",
                kind="decision",
                topic="security",
                body="Policy-blocked fact.",
                summary="Policy-blocked fact.",
                status="accepted",
                confidence="high",
                valid_from="2026-05-09T00:00:00Z",
                created_at="2026-05-09T00:00:00Z",
                updated_at="2026-05-09T00:00:00Z",
                source_file_path=".env",
                human_review_state="approved",
            ),
        )
    finally:
        conn.close()
    (repo_root / ".ait" / "memory-policy.json").write_text(
        json.dumps({"exclude_paths": [".env"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (repo_root / "CLAUDE.md").write_text("Review live source guidance.\n", encoding="utf-8")
    return repo_root


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
