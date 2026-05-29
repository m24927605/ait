from __future__ import annotations

import io
import json
import shlex
import subprocess
import sys
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
    get_attempt,
    insert_attempt,
    insert_attempt_commit,
    insert_intent,
    list_attempt_review_findings,
    list_attempt_reviews,
    run_migrations,
)


class CliReviewAdversarialTests(unittest.TestCase):
    def test_fake_pass_creates_passed_review(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        exit_code, payload = _review_json(repo_root, "fake:pass")

        self.assertEqual(0, exit_code)
        self.assertEqual("adversarial", payload["mode"])
        self.assertEqual("passed", payload["status"])
        self.assertFalse(payload["blocking"])
        self.assertEqual(0, payload["finding_count"])
        self.assertTrue((repo_root / payload["artifact_ref"]).exists())
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            attempt = get_attempt(conn, "repo:01ATTEMPT")
        self.assertEqual("passed", reviews[-1].status)
        assert attempt is not None
        self.assertEqual("succeeded", attempt.verified_status)

    def test_fake_low_creates_warning_review_with_finding(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        exit_code, payload = _review_json(repo_root, "fake:low")

        self.assertEqual(0, exit_code)
        self.assertEqual("warning", payload["status"])
        self.assertFalse(payload["blocking"])
        self.assertEqual(1, payload["finding_count"])
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            findings = list_attempt_review_findings(conn, reviews[-1].id)
        self.assertEqual("low", findings[0].severity)
        self.assertFalse(findings[0].blocking)
        self.assertEqual("open", findings[0].lifecycle_status)

    def test_fake_high_creates_blocked_review_with_blocking_finding(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        exit_code, payload = _review_json(repo_root, "fake:high")

        self.assertEqual(0, exit_code)
        self.assertEqual("blocked", payload["status"])
        self.assertTrue(payload["blocking"])
        self.assertEqual(1, payload["finding_count"])
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            findings = list_attempt_review_findings(conn, reviews[-1].id)
        self.assertEqual("high", findings[0].severity)
        self.assertTrue(findings[0].blocking)

    def test_fake_malformed_creates_failed_review_without_changing_attempt_status(self) -> None:
        repo_root = _repo_with_reviewable_attempt()

        exit_code, payload = _review_json(repo_root, "fake:malformed")

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertTrue(payload["blocking"])
        self.assertIn("not valid JSON", payload["error"])
        with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
            reviews = list_attempt_reviews(conn, target_attempt_id="repo:01ATTEMPT")
            attempt = get_attempt(conn, "repo:01ATTEMPT")
        self.assertEqual("failed", reviews[-1].status)
        assert attempt is not None
        self.assertEqual("succeeded", attempt.verified_status)

    def test_adversarial_mode_requires_adapter(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        stdout = io.StringIO()

        with (
            _chdir(repo_root),
            patch(
                "sys.argv",
                [
                    "ait",
                    "review",
                    "attempt",
                    "latest-reviewable",
                    "--mode",
                    "adversarial",
                    "--format",
                    "json",
                ],
            ),
            redirect_stdout(stdout),
        ):
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(2, exit_code)
        self.assertIn("review adapter is required", payload["error"])

    def test_command_reviewer_passes_and_captures_invocation(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "reviewer.py"
        script.write_text(
            "import json, sys\n"
            "sys.stdin.read()\n"
            "print(json.dumps({'summary': 'command ok', 'findings': []}))\n",
            encoding="utf-8",
        )

        exit_code, payload = _review_json(
            repo_root,
            f"command:{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
        )

        artifact = json.loads((repo_root / payload["artifact_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(0, exit_code)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(0, artifact["adapter_invocation"]["returncode"])
        self.assertIn(".ait/reviewer-runs", artifact["adapter_invocation"]["cwd"])
        self.assertIn("command ok", artifact["adapter_invocation"]["stdout"])

    def test_command_reviewer_nonzero_exit_creates_failed_review(self) -> None:
        repo_root = _repo_with_reviewable_attempt()
        script = repo_root / "reviewer_fail.py"
        script.write_text(
            "import sys\n"
            "print('partial stdout')\n"
            "print('boom stderr', file=sys.stderr)\n"
            "raise SystemExit(7)\n",
            encoding="utf-8",
        )

        exit_code, payload = _review_json(
            repo_root,
            f"command:{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
        )

        artifact = json.loads((repo_root / payload["artifact_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertIn("exited with code 7", payload["error"])
        self.assertEqual(7, artifact["adapter_invocation"]["returncode"])
        self.assertIn("partial stdout", artifact["adapter_invocation"]["stdout"])
        self.assertIn("boom stderr", artifact["adapter_invocation"]["stderr"])


def _review_json(repo_root: Path, adapter: str) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    with (
        _chdir(repo_root),
        patch(
            "sys.argv",
            [
                "ait",
                "review",
                "attempt",
                "latest-reviewable",
                "--mode",
                "adversarial",
                "--review-adapter",
                adapter,
                "--format",
                "json",
            ],
        ),
        redirect_stdout(stdout),
    ):
        exit_code = cli.main()
    payload = json.loads(stdout.getvalue())
    return exit_code, payload


def _repo_with_reviewable_attempt() -> Path:
    """Create a fixture repo with a real git commit so the reviewer
    can materialize the pinned snapshot (see review_adapter.run_review_adapter).
    """
    tmp = tempfile.TemporaryDirectory()
    repo_root = Path(tmp.name)
    _TEMP_DIRS.append(tmp)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "t@example.com")
    _git(repo_root, "config", "user.name", "Test")
    (repo_root / "src").mkdir(exist_ok=True)
    (repo_root / "src" / "example.py").write_text(
        "def example():\n    return 'fixture'\n", encoding="utf-8"
    )
    _git(repo_root, "add", "src/example.py")
    _git(repo_root, "commit", "-q", "-m", "fixture")
    head_oid = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    base_oid = head_oid
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review target",
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
                base_ref_oid=base_oid,
                started_at="2026-05-09T00:01:00Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        insert_attempt_commit(
            conn,
            attempt_id="repo:01ATTEMPT",
            commit_oid=head_oid,
            base_commit_oid=base_oid,
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
