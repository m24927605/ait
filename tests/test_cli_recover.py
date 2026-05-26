from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import create_attempt, create_intent


class CliRecoverTests(unittest.TestCase):
    def test_recover_next_step_matches_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "a1"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Status: active", text)
        self.assertIn("Attempt: a1", text)
        self.assertIn("Next: ait resume a1", text)
        self.assertNotIn(attempt.workspace_ref, text)

    def test_json_contains_attempt_id_and_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "recover", "a1", "--json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(attempt.attempt_id, payload["attempt_id"])
        self.assertEqual("a1", payload["attempt_handle"])
        self.assertEqual(["ait resume a1"], payload["next_steps"])
        self.assertIn("workspace_ref", payload)


def _init_git_repo(path: Path) -> None:
    _git(path, "init", "-b", "main")


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
