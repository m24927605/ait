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
    connect_db,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    list_attempt_review_findings,
    list_attempt_reviews,
    run_migrations,
)
from ait.review_queue import enqueue_review, process_review_queue


class ReviewQueueWorkerTests(unittest.TestCase):
    def test_worker_processes_fake_pass_job(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        job = enqueue_review(repo_root, "latest-reviewable", adapter="fake:pass")

        result = process_review_queue(repo_root, max_jobs=1)

        self.assertEqual(1, result.processed)
        self.assertEqual(1, result.passed)
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
        self.assertEqual(job.id, reviews[-1].id)
        self.assertEqual("passed", reviews[-1].status)
        self.assertFalse(reviews[-1].blocking)
        assert reviews[-1].artifact_ref is not None
        self.assertTrue((repo_root / reviews[-1].artifact_ref).exists())

    def test_worker_processes_fake_high_job_as_blocked(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        job = enqueue_review(repo_root, "latest-reviewable", adapter="fake:high")

        result = process_review_queue(repo_root, max_jobs=1)

        self.assertEqual(1, result.blocked)
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            findings = list_attempt_review_findings(conn, job.id)
        self.assertEqual("blocked", reviews[-1].status)
        self.assertEqual(1, len(findings))
        self.assertEqual("high", findings[0].severity)

    def test_worker_processes_malformed_output_as_failed(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        enqueue_review(repo_root, "latest-reviewable", adapter="fake:malformed")

        result = process_review_queue(repo_root, max_jobs=1)

        self.assertEqual(1, result.failed)
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
        self.assertEqual("failed", reviews[-1].status)
        self.assertTrue(reviews[-1].blocking)

    def test_worker_respects_max_jobs(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        enqueue_review(repo_root, "latest-reviewable", budget="quick", adapter="fake:pass")
        enqueue_review(repo_root, "latest-reviewable", budget="deep", adapter="fake:pass")

        result = process_review_queue(repo_root, max_jobs=1)

        self.assertEqual(1, result.processed)
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            statuses = [review.status for review in list_attempt_reviews(conn)]
        self.assertEqual(["passed", "queued"], statuses)

    def test_cli_worker_json_reports_counts(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        enqueue_review(repo_root, "latest-reviewable", adapter="fake:pass")

        stdout = io.StringIO()
        with (
            _chdir(repo_root),
            patch("sys.argv", ["ait", "review", "worker", "--once", "--format", "json"]),
            redirect_stdout(stdout),
        ):
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, payload["processed"])
        self.assertEqual(1, payload["passed"])


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
                title="Review worker",
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


@contextmanager
def _chdir(path: Path):
    original = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        os.chdir(original)


if __name__ == "__main__":
    unittest.main()
