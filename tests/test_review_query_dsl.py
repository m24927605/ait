from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import init_repo
from ait.db import (
    NewAttempt,
    NewIntent,
    NewAttemptReviewOverride,
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_attempt_review_override,
    insert_intent,
    run_migrations,
    utc_now,
)
from ait.review import create_fake_reviewer_review


class ReviewQueryDslTests(unittest.TestCase):
    def test_query_review_status_and_profile(self) -> None:
        repo_root = _repo_with_reviewable_attempt(touched_files=("src/auth/session.py",))
        create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")

        rows = _query(repo_root, 'review.status="blocked" AND review.profile="security"')

        self.assertEqual(["repo:01ATTEMPT"], [row["id"] for row in rows])

    def test_query_review_override(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        review = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            insert_attempt_review_override(
                conn,
                NewAttemptReviewOverride(
                    id="override:1",
                    review_id=review.review.id,
                    reason="accepted risk",
                    created_at=utc_now(),
                ),
            )

        rows = _query(repo_root, "review.override=true")

        self.assertEqual(["repo:01ATTEMPT"], [row["id"] for row in rows])

    def test_query_finding_severity_and_lifecycle(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")

        rows = _query(repo_root, 'finding.severity IN ("high", "critical") AND finding.lifecycle_status="open"')

        self.assertEqual(["repo:01ATTEMPT"], [row["id"] for row in rows])

    def test_query_review_fresh_false(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            conn.execute("UPDATE attempt_reviews SET target_head_oid = ? WHERE target_attempt_id = ?", ("9" * 40, "repo:01ATTEMPT"))
            conn.commit()

        rows = _query(repo_root, "review.fresh=false")

        self.assertEqual(["repo:01ATTEMPT"], [row["id"] for row in rows])

    def test_query_review_field_does_not_match_attempt_without_review(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        rows = _query(repo_root, 'review.status="passed"')

        self.assertEqual([], rows)


def _query(repo_root: Path, expression: str) -> list[dict[str, object]]:
    stdout = io.StringIO()
    with (
        _chdir(repo_root),
        patch("sys.argv", ["ait", "query", expression, "--format", "jsonl"]),
        redirect_stdout(stdout),
    ):
        exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(stdout.getvalue())
    text = stdout.getvalue().strip()
    return [json.loads(line) for line in text.splitlines()] if text else []


def _repo_with_reviewable_attempt(*, touched_files: tuple[str, ...] = ("src/example.py",)) -> Path:
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
                title="Review query dsl",
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
            touched_files=touched_files,
        )
    finally:
        conn.close()
    return repo_root


@contextmanager
def _chdir(path: Path):
    original = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        os.chdir(original)


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
