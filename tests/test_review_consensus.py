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
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    list_attempt_review_findings,
    run_migrations,
)
from ait.review import create_fake_multi_reviewer_review


class ReviewConsensusTests(unittest.TestCase):
    def test_all_required_profiles_pass(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        result = create_fake_multi_reviewer_review(
            repo_root,
            "latest-reviewable",
            profiles=("security", "regression"),
            profile_adapters={"security": "fake:pass", "regression": "fake:pass"},
        )

        self.assertEqual("passed", result.review.status)
        self.assertFalse(result.review.blocking)
        self.assertEqual(("security", "regression"), result.review.profiles)

    def test_high_blocking_finding_blocks_consensus(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        result = create_fake_multi_reviewer_review(
            repo_root,
            "latest-reviewable",
            profiles=("security", "regression"),
            profile_adapters={"security": "fake:high", "regression": "fake:pass"},
        )

        self.assertEqual("blocked", result.review.status)
        self.assertTrue(result.review.blocking)
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            findings = list_attempt_review_findings(conn, result.review.id)
        self.assertEqual("high", findings[0].severity)
        self.assertTrue(findings[0].blocking)

    def test_missing_required_profile_blocks(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        result = create_fake_multi_reviewer_review(
            repo_root,
            "latest-reviewable",
            profiles=("security", "regression"),
            profile_adapters={"security": "fake:pass"},
        )

        self.assertEqual("blocked", result.review.status)
        self.assertTrue(result.review.blocking)
        self.assertIn("missing required profile", result.review.summary)

    def test_disagreement_blocks_for_human_review(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        result = create_fake_multi_reviewer_review(
            repo_root,
            "latest-reviewable",
            profiles=("security", "regression"),
            profile_adapters={"security": "fake:disagree", "regression": "fake:pass"},
        )

        artifact = json.loads((repo_root / result.review.artifact_ref).read_text(encoding="utf-8"))
        self.assertEqual("blocked", result.review.status)
        self.assertEqual("review_disagreement", result.review.summary)
        self.assertEqual("review_disagreement", artifact["consensus_reason"])


def _repo_with_reviewable_attempt() -> Path:
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
                title="Review consensus",
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
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid="1" * 40,
            base_commit_oid="0" * 40,
            touched_files=("src/auth/session.py",),
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


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
