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
    get_attempt_review_finding,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    list_attempt_review_overrides,
    list_attempt_reviews,
    run_migrations,
)
from ait.review import create_fake_reviewer_review


class ReviewFindingsTests(unittest.TestCase):
    def test_list_findings_by_status_and_severity(self) -> None:
        repo_root, finding_id = _repo_with_high_finding()
        stdout = io.StringIO()

        with _chdir(repo_root):
            with patch(
                "sys.argv",
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
            ):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual([finding_id], [item["id"] for item in payload["findings"]])

    def test_update_open_to_acknowledged(self) -> None:
        repo_root, finding_id = _repo_with_high_finding()

        payload = _update_finding(repo_root, finding_id, "acknowledged")

        self.assertEqual("acknowledged", payload["finding"]["lifecycle_status"])
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            finding = get_attempt_review_finding(conn, finding_id)
        assert finding is not None
        self.assertEqual("Potential regression", finding.title)
        self.assertEqual("diff-hunk-1", finding.evidence_ref)

    def test_false_positive_requires_reason(self) -> None:
        repo_root, finding_id = _repo_with_high_finding()
        stdout = io.StringIO()

        with _chdir(repo_root):
            with patch(
                "sys.argv",
                [
                    "ait",
                    "review",
                    "finding",
                    "update",
                    finding_id,
                    "--status",
                    "false_positive",
                    "--format",
                    "json",
                ],
            ):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(2, exit_code)
        self.assertIn("requires --reason", payload["error"])

    def test_accepted_risk_requires_reason_and_creates_audit(self) -> None:
        repo_root, finding_id = _repo_with_high_finding()

        payload = _update_finding(repo_root, finding_id, "accepted_risk", reason="accepted for release")

        self.assertEqual("accepted_risk", payload["finding"]["lifecycle_status"])
        self.assertIsNotNone(payload["override"])
        self.assertEqual("accepted for release", payload["override"]["reason"])
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            overrides = list_attempt_review_overrides(conn, reviews[-1].id)
            finding = get_attempt_review_finding(conn, finding_id)
        self.assertEqual(1, len(overrides))
        assert finding is not None
        self.assertEqual("Potential regression", finding.title)
        self.assertIn("sensitive behavior change", finding.body)


def _repo_with_high_finding() -> tuple[Path, str]:
    repo_root = _repo_with_reviewable_attempt()
    result = create_fake_reviewer_review(repo_root, "latest-reviewable", fake_adapter="fake:high")
    return repo_root, result.findings[0].id


def _update_finding(repo_root: Path, finding_id: str, status: str, *, reason: str | None = None) -> dict[str, object]:
    stdout = io.StringIO()
    argv = ["ait", "review", "finding", "update", finding_id, "--status", status, "--format", "json"]
    if reason is not None:
        argv.extend(["--reason", reason])
    with _chdir(repo_root):
        with patch("sys.argv", argv):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(stdout.getvalue())
    return json.loads(stdout.getvalue())


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
                title="Review finding",
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
