from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli


class CliRunTests(unittest.TestCase):
    def test_run_json_format_outputs_parseable_json_with_command_output(self) -> None:
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
                        "--intent",
                        "Capture output",
                        "--",
                        sys.executable,
                        "-c",
                        "import sys; print('agent out'); print('agent err', file=sys.stderr)",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(0, payload["exit_code"])
        self.assertEqual("agent out\n", payload["command_stdout"])
        self.assertEqual("agent err\n", payload["command_stderr"])

    def test_memory_text_outputs_repo_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertIn("AIT Long-Term Repo Memory", stdout.getvalue())
        self.assertIn("Recent Attempts:", stdout.getvalue())

    def test_memory_note_cli_adds_lists_and_removes_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_stdout = io.StringIO()
            list_stdout = io.StringIO()
            remove_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "architecture",
                        "Use repo-local state only.",
                    ],
                ):
                    with redirect_stdout(add_stdout):
                        add_exit = cli.main()
                note_id = json.loads(add_stdout.getvalue())["id"]
                with patch("sys.argv", ["ait", "memory", "note", "list", "--topic", "architecture"]):
                    with redirect_stdout(list_stdout):
                        list_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "note", "remove", note_id]):
                    with redirect_stdout(remove_stdout):
                        remove_exit = cli.main()

        self.assertEqual(0, add_exit)
        self.assertEqual(0, list_exit)
        self.assertEqual(0, remove_exit)
        self.assertIn("Use repo-local state only.", list_stdout.getvalue())
        self.assertTrue(json.loads(remove_stdout.getvalue())["removed"])

    def test_memory_search_cli_outputs_parseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_stdout = io.StringIO()
            search_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    ["ait", "memory", "note", "add", "--topic", "workflow", "Run tests before release."],
                ):
                    with redirect_stdout(add_stdout):
                        add_exit = cli.main()
                with patch(
                    "sys.argv",
                    ["ait", "memory", "search", "tests release", "--format", "json"],
                ):
                    with redirect_stdout(search_stdout):
                        search_exit = cli.main()

        payload = json.loads(search_stdout.getvalue())
        self.assertEqual(0, add_exit)
        self.assertEqual(0, search_exit)
        self.assertEqual("note", payload[0]["kind"])
        self.assertIn("Run tests before release.", payload[0]["text"])


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
