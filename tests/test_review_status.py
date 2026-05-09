from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
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
    run_migrations,
)
from ait.review_queue import enqueue_review, mark_review_running


class ReviewStatusTests(unittest.TestCase):
    def test_review_status_json_lists_jobs(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        queued = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")
        mark_review_running(repo_root, queued.id)
        stdout = io.StringIO()

        with _chdir(repo_root):
            with patch("sys.argv", ["ait", "review", "status", "--format", "json"]):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(1, len(payload["reviews"]))
        self.assertEqual(queued.id, payload["reviews"][0]["review_id"])
        self.assertEqual("running", payload["reviews"][0]["status"])
        self.assertTrue(payload["reviews"][0]["blocking"])

    def test_review_status_text_is_actionable(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        queued = enqueue_review(repo_root, "latest-reviewable", mode="adversarial", adapter="fake:pass")
        stdout = io.StringIO()

        with _chdir(repo_root):
            with patch("sys.argv", ["ait", "review", "status"]):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("AIT Reviews", text)
        self.assertIn(queued.id, text)
        self.assertIn("status=queued", text)
        self.assertIn("Next: ait review status --format json", text)


class _chdir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.original: Path | None = None

    def __enter__(self):
        import os

        self.original = Path.cwd()
        os.chdir(self.path)

    def __exit__(self, exc_type, exc, tb):
        import os

        assert self.original is not None
        os.chdir(self.original)


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
                title="Review status",
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
