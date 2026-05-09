from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.db import connect_db, list_attempt_reviews


class CliRunReviewTests(unittest.TestCase):
    def test_run_review_never_keeps_existing_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--review",
                        "never",
                        "--intent",
                        "No review",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('no-review.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("never", payload["run_review_policy"])
            self.assertIsNone(payload["review"])
            with connect_db(repo_root / ".ait" / "state.sqlite3") as conn:
                self.assertEqual([], list_attempt_reviews(conn, target_attempt_id=payload["attempt_id"]))

    def test_risk_based_run_records_deterministic_review_without_fake_for_medium_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--review",
                        "risk-based",
                        "--review-adapter",
                        "fake:high",
                        "--intent",
                        "Medium review",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('medium.py').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("risk-based", payload["run_review_policy"])
            self.assertEqual("light", payload["review"]["mode"])
            self.assertEqual("medium", payload["review"]["risk_level"])
            self.assertEqual("warning", payload["review"]["status"])
            self.assertFalse(payload["review"]["blocking"])

    def test_high_risk_apply_never_queues_review_without_blocking_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--review",
                        "risk-based",
                        "--review-adapter",
                        "fake:pass",
                        "--apply",
                        "never",
                        "--intent",
                        "High review queue",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('.github/workflows').mkdir(parents=True, exist_ok=True); Path('.github/workflows/release.yml').write_text('name: release\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("queued", payload["review"]["status"])
            self.assertEqual("adversarial", payload["review"]["mode"])
            self.assertIsNone(payload["apply"])

    def test_high_risk_auto_apply_holds_when_required_review_is_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _init_ait_and_commit_gitignore(repo_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--review",
                        "risk-based",
                        "--review-adapter",
                        "fake:pass",
                        "--apply",
                        "auto",
                        "--intent",
                        "High review queued",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('.github/workflows').mkdir(parents=True, exist_ok=True); Path('.github/workflows/release.yml').write_text('name: release\\n')",
                    ],
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("queued", payload["review"]["status"])
            self.assertEqual("held", payload["apply"]["status"])
            self.assertEqual("queued", payload["apply"]["debug"]["review_gate"]["status"])
            self.assertIn("review gate", payload["apply"]["reason"])


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _init_ait_and_commit_gitignore(repo_root: Path) -> None:
    with chdir(repo_root):
        with patch("sys.argv", ["ait", "init"]):
            cli.main()
    if (repo_root / ".gitignore").exists() and _git_stdout(repo_root, "status", "--short", "--", ".gitignore"):
        _git(repo_root, "add", ".gitignore")
        _git(repo_root, "commit", "-m", "ignore ait state")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
