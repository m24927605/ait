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
    run_migrations,
    update_attempt_review_finding_status,
    update_attempt_review_status,
)
from ait.report import build_work_graph, render_work_graph_html, render_work_graph_text
from ait.review import create_fake_multi_reviewer_review, create_fake_reviewer_review


class ReviewQueryTests(unittest.TestCase):
    def test_list_open_high_findings(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        review = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")

        payload = _cli_json(
            repo_root,
            [
                "ait",
                "review",
                "finding",
                "list",
                "--status",
                "open",
                "--severity",
                "high",
                "--format",
                "json",
            ],
        )

        self.assertEqual([review.findings[0].id], [item["id"] for item in payload["findings"]])

    def test_list_accepted_risk_findings(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        review = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            update_attempt_review_finding_status(
                conn,
                review.findings[0].id,
                lifecycle_status="accepted_risk",
            )

        payload = _cli_json(
            repo_root,
            [
                "ait",
                "review",
                "finding",
                "list",
                "--status",
                "accepted_risk",
                "--format",
                "json",
            ],
        )

        self.assertEqual([review.findings[0].id], [item["id"] for item in payload["findings"]])

    def test_list_overridden_reviews(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        review = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:pass")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            update_attempt_review_status(
                conn,
                review.review.id,
                status="overridden",
                summary="human override",
            )

        payload = _cli_json(repo_root, ["ait", "review", "status", "--status", "overridden", "--format", "json"])

        self.assertEqual([review.review.id], [item["review_id"] for item in payload["reviews"]])

    def test_report_shows_profile_results_and_disagreement(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        create_fake_multi_reviewer_review(
            repo_root,
            "latest-reviewable",
            profiles=("security", "regression"),
            profile_adapters={"security": "fake:disagree", "regression": "fake:pass"},
        )

        graph = build_work_graph(repo_root)
        text = render_work_graph_text(graph)
        html = render_work_graph_html(graph)

        self.assertIn("Review profiles: security, regression", text)
        self.assertIn("Review summary: review_disagreement", text)
        self.assertIn("review_disagreement", html)
        self.assertIn("security, regression", html)

    def test_report_shows_accepted_risk_separately(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        review = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            update_attempt_review_finding_status(
                conn,
                review.findings[0].id,
                lifecycle_status="accepted_risk",
            )

        text = render_work_graph_text(build_work_graph(repo_root))
        html = render_work_graph_html(build_work_graph(repo_root))

        self.assertIn("Review accepted risk: 1", text)
        self.assertIn("Accepted Risk", html)


def _cli_json(repo_root: Path, argv: list[str]) -> dict[str, object]:
    stdout = io.StringIO()
    with _chdir(repo_root):
        with patch("sys.argv", argv):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(stdout.getvalue())
    payload = json.loads(stdout.getvalue())
    if not isinstance(payload, dict):
        raise AssertionError("expected object payload")
    return payload


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
                title="Review query",
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
