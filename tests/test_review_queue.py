from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
)
from ait.review_queue import (
    enqueue_review,
    mark_review_failed,
    mark_review_passed,
    mark_review_running,
    reconcile_stale_review_jobs,
)


class ReviewQueueTests(unittest.TestCase):
    def test_enqueue_review_creates_queued_job(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        job = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")

        self.assertEqual("queued", job.status)
        self.assertEqual("adversarial", job.mode)
        self.assertEqual("repo:01ATTEMPT", job.target_attempt_id)
        self.assertTrue(job.baseline_ref)

    def test_duplicate_queue_request_dedupes_active_job(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        first = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")
        second = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")

        self.assertEqual(first.id, second.id)

    def test_status_transitions_running_to_passed(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        job = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")

        running = mark_review_running(repo_root, job.id)
        passed = mark_review_passed(repo_root, job.id)

        self.assertEqual("running", running.status)
        self.assertEqual("passed", passed.status)
        self.assertFalse(passed.blocking)
        self.assertIsNotNone(passed.completed_at)

    def test_failure_transition_stores_reason(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        job = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")

        failed = mark_review_failed(repo_root, job.id, reason="review command failed")

        self.assertEqual("failed", failed.status)
        self.assertTrue(failed.blocking)
        self.assertEqual("review command failed", failed.summary)

    def test_stale_running_job_becomes_failed(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        job = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")
        mark_review_running(repo_root, job.id)
        old = (datetime.now(tz=UTC) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            conn.execute("UPDATE attempt_reviews SET created_at = ? WHERE id = ?", (old, job.id))
            conn.commit()

        updated = reconcile_stale_review_jobs(repo_root)

        self.assertEqual(1, len(updated))
        self.assertEqual("failed", updated[0].status)
        self.assertEqual("review job stale", updated[0].summary)


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
                title="Review queue",
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
