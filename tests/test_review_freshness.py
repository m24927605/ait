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
    run_migrations,
    update_attempt_review_finding_status,
)
from ait.review import create_fake_reviewer_review
from ait.review_policy import evaluate_review_freshness


class ReviewFreshnessTests(unittest.TestCase):
    def test_review_is_fresh_when_metadata_matches(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")

        freshness = _freshness(repo_root, result.review.id)

        self.assertTrue(freshness.fresh)
        self.assertEqual("fresh", freshness.status)

    def test_target_head_change_makes_review_stale(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            insert_attempt_commit(
                conn,
                attempt_id="repo:01ATTEMPT",
                commit_oid="2" * 40,
                base_commit_oid="1" * 40,
                touched_files=("src/example.py",),
            )

        freshness = _freshness(repo_root, result.review.id)

        self.assertFalse(freshness.fresh)
        self.assertIn("commits changed", freshness.reason)

    def test_base_ref_change_makes_review_stale(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            conn.execute(
                "UPDATE attempts SET base_ref_oid = ? WHERE id = ?",
                ("9" * 40, "repo:01ATTEMPT"),
            )
            conn.commit()

        freshness = _freshness(repo_root, result.review.id)

        self.assertFalse(freshness.fresh)
        self.assertIn("base ref", freshness.reason)

    def test_policy_change_makes_review_stale(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        config_path = repo_root / ".ait" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["review"] = {"sensitive_paths": ["src/**"]}
        config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

        freshness = _freshness(repo_root, result.review.id)

        self.assertFalse(freshness.fresh)
        self.assertIn("policy changed", freshness.reason)

    def test_fixed_finding_makes_review_stale(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            update_attempt_review_finding_status(
                conn,
                result.findings[0].id,
                lifecycle_status="fixed",
            )

        freshness = _freshness(repo_root, result.review.id)

        self.assertFalse(freshness.fresh)
        self.assertIn("lifecycle", freshness.reason)


def _freshness(repo_root: Path, review_id: str):
    from ait.db import get_attempt_review

    with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
        review = get_attempt_review(conn, review_id)
        assert review is not None
        return evaluate_review_freshness(repo_root, conn, review)


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
                title="Review freshness",
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
            touched_files=("src/example.py",),
        )
    finally:
        conn.close()
    return repo_root


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
