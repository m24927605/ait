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
    NewAttemptReview,
    NewAttemptReviewFinding,
    NewMemoryFact,
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    insert_attempt_review,
    insert_attempt_review_finding,
    run_migrations,
    upsert_memory_fact,
)
from ait.review import create_deterministic_review
from ait.review_baseline import render_reviewer_brief


class ReviewBaselineTests(unittest.TestCase):
    def test_baseline_includes_only_approved_accepted_facts_as_trusted(self) -> None:
        repo_root = _repo_with_attempt_and_memory()

        result = create_deterministic_review(repo_root, "latest-reviewable")

        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        payload = json.loads((repo_root / baseline_ref).read_text(encoding="utf-8"))
        selected_ids = {fact["id"] for fact in payload["selected_facts"]}
        excluded = {item["id"]: item["reason"] for item in payload["excluded_sources_summary"]}

        self.assertIn("fact:approved", selected_ids)
        self.assertNotIn("fact:candidate", selected_ids)
        self.assertNotIn("fact:secret", selected_ids)
        self.assertEqual("excluded_source_path", excluded["fact:secret"])
        self.assertTrue(payload["baseline_policy_hash"])

    def test_baseline_marks_producer_trace_as_advisory(self) -> None:
        repo_root = _repo_with_attempt_and_memory(raw_trace_ref=".ait/traces/attempt.txt")

        result = create_deterministic_review(repo_root, "latest-reviewable")

        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        payload = json.loads((repo_root / baseline_ref).read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "kind": "producer_trace",
                    "ref": ".ait/traces/attempt.txt",
                    "trust": "advisory",
                }
            ],
            payload["advisory_sources"],
        )

    def test_baseline_records_prior_failed_attempts_touching_same_files(self) -> None:
        repo_root = _repo_with_attempt_and_memory(include_failed_attempt=True)

        result = create_deterministic_review(repo_root, "latest-reviewable")

        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        payload = json.loads((repo_root / baseline_ref).read_text(encoding="utf-8"))
        self.assertEqual("repo:01FAILED", payload["prior_failed_attempts"][0]["attempt_id"])
        self.assertEqual(["src/example.py"], payload["prior_failed_attempts"][0]["overlap"])

    def test_baseline_records_diff_prior_findings_and_test_evidence(self) -> None:
        repo_root = _repo_with_real_commit_context()

        result = create_deterministic_review(repo_root, "latest-reviewable")

        baseline_ref = result.review.baseline_ref
        assert baseline_ref is not None
        payload = json.loads((repo_root / baseline_ref).read_text(encoding="utf-8"))
        diff = payload["changed_diff_excerpts"][0]["diff"]
        self.assertIn("+    return 'new'", diff)
        self.assertEqual("repo:review-old", payload["prior_review_findings"][0]["review_id"])
        self.assertEqual("src/example.py", payload["prior_review_findings"][0]["path"])
        self.assertEqual(2, payload["test_evidence"]["observed_commands_run"])
        self.assertEqual(1, payload["test_evidence"]["observed_tests_run"])
        self.assertEqual(0, payload["test_evidence"]["result_exit_code"])
        self.assertEqual("pytest tests/test_example.py", payload["test_evidence"]["command"])
        self.assertEqual(0, payload["test_evidence"]["trace_exit_code"])
        brief = render_reviewer_brief(
            repo_root,
            review_id=result.review.id,
            target=result.target,
            assessment=result.assessment,
            baseline_ref=baseline_ref,
            budget="deep",
        )
        self.assertIn("## Changed Diff Excerpts", brief)
        self.assertIn("+    return 'new'", brief)
        self.assertIn("## Prior Failed Attempts", brief)
        self.assertIn("## Prior Review Findings", brief)
        self.assertIn("Prior regression", brief)
        self.assertIn("- observed_commands_run: 2", brief)
        self.assertIn("- command: pytest tests/test_example.py", brief)


def _repo_with_attempt_and_memory(
    *,
    raw_trace_ref: str | None = None,
    include_failed_attempt: bool = False,
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
                title="Review baseline",
                created_at="2026-05-09T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        _insert_attempt(
            conn,
            "repo:01ATTEMPT",
            verified_status="succeeded",
            touched_files=("src/example.py",),
            raw_trace_ref=raw_trace_ref,
        )
        if include_failed_attempt:
            _insert_attempt(
                conn,
                "repo:01FAILED",
                verified_status="failed",
                touched_files=("src/example.py",),
            )
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id="fact:approved",
                kind="rule",
                topic="testing",
                body="Use regression tests for bug fixes.",
                summary="Bug fixes need regression tests.",
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
                id="fact:candidate",
                kind="rule",
                topic="testing",
                body="Candidate fact should not be trusted.",
                summary="Candidate fact.",
                status="candidate",
                confidence="medium",
                valid_from="2026-05-09T00:00:00Z",
                created_at="2026-05-09T00:00:00Z",
                updated_at="2026-05-09T00:00:00Z",
                human_review_state="pending",
            ),
        )
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id="fact:secret",
                kind="rule",
                topic="security",
                body="Secret-path fact should be excluded.",
                summary="Secret-path fact.",
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
    return repo_root


def _insert_attempt(
    conn,
    attempt_id: str,
    *,
    verified_status: str,
    touched_files: tuple[str, ...],
    raw_trace_ref: str | None = None,
) -> None:
    insert_attempt(
        conn,
        NewAttempt(
            id=attempt_id,
            intent_id="repo:01INTENT",
            agent_id="codex:main",
            workspace_ref=f"/tmp/{attempt_id}",
            base_ref_oid="0" * 40,
            started_at="2026-05-09T00:01:00Z",
            ownership_token=f"token-{attempt_id}",
            reported_status="finished",
            verified_status=verified_status,
        ),
    )
    if raw_trace_ref is not None:
        conn.execute(
            "UPDATE attempts SET raw_trace_ref = ? WHERE id = ?",
            (raw_trace_ref, attempt_id),
        )
        conn.commit()
    insert_attempt_commit(
        conn,
        attempt_id=attempt_id,
        commit_oid=f"{attempt_id}:commit",
        base_commit_oid="0" * 40,
        touched_files=touched_files,
    )


def _repo_with_real_commit_context() -> Path:
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    _TEMP_DIRS.append(tmp)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    src = repo_root / "src"
    src.mkdir()
    (src / "example.py").write_text("def value():\n    return 'old'\n", encoding="utf-8")
    _git(repo_root, "add", "src/example.py")
    _git(repo_root, "commit", "-m", "base")
    base_oid = _git_stdout(repo_root, "rev-parse", "HEAD")
    (src / "example.py").write_text("def value():\n    return 'new'\n", encoding="utf-8")
    _git(repo_root, "add", "src/example.py")
    _git(repo_root, "commit", "-m", "attempt")
    attempt_oid = _git_stdout(repo_root, "rev-parse", "HEAD")
    trace_ref = ".ait/traces/attempt.txt"
    (repo_root / ".ait" / "traces").mkdir(parents=True, exist_ok=True)
    (repo_root / trace_ref).write_text(
        "\n".join(
            [
                "AIT Agent Transcript",
                "Attempt-Id: repo:01ATTEMPT",
                "Command: pytest tests/test_example.py",
                "Exit-Code: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review baseline",
                created_at="2026-05-09T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id="repo:01OLD",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref="/tmp/old",
                base_ref_oid=base_oid,
                started_at="2026-05-09T00:00:00Z",
                ownership_token="old",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01OLD",
            commit_oid=base_oid,
            base_commit_oid=base_oid,
            touched_files=("src/example.py",),
        )
        review = insert_attempt_review(
            conn,
            NewAttemptReview(
                id="repo:review-old",
                target_attempt_id="repo:01OLD",
                mode="adversarial",
                budget="standard",
                profiles=("regression",),
                risk_level="high",
                risk_score=70,
                risk_reasons=(),
                status="blocked",
                blocking=True,
                policy_hash="policy",
                baseline_policy_hash="baseline",
                created_at="2026-05-09T00:02:00Z",
                summary="old finding",
            ),
        )
        insert_attempt_review_finding(
            conn,
            NewAttemptReviewFinding(
                id="repo:finding-old",
                review_id=review.id,
                severity="high",
                blocking=True,
                lifecycle_status="open",
                path="src/example.py",
                title="Prior regression",
                body="Previous review found a regression here.",
                confidence="high",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id="repo:01ATTEMPT",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref="/tmp/attempt",
                base_ref_oid=base_oid,
                started_at="2026-05-09T00:03:00Z",
                ownership_token="attempt",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        conn.execute(
            "UPDATE attempts SET raw_trace_ref = ?, result_exit_code = 0 WHERE id = ?",
            (trace_ref, "repo:01ATTEMPT"),
        )
        conn.execute(
            """
            UPDATE evidence_summaries
            SET observed_commands_run = 2,
                observed_tests_run = 1,
                observed_tests_passed = 1,
                observed_tests_failed = 0,
                raw_trace_ref = ?
            WHERE attempt_id = ?
            """,
            (trace_ref, "repo:01ATTEMPT"),
        )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid=attempt_oid,
            base_commit_oid=base_oid,
            touched_files=("src/example.py",),
        )
    finally:
        conn.close()
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


def _git_stdout(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
