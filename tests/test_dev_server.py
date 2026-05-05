from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.dev_server import (
    DevServerError,
    PortProcess,
    check_preview_url,
    guard_preview_port,
    start_dev_server,
)


class DevServerTests(unittest.TestCase):
    def test_preview_guard_reports_port_cwd_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)
            static_file = worktree / "apps" / "flight_assistant" / "static" / "human_review.html"
            static_file.parent.mkdir(parents=True)
            static_file.write_text("<html>ok</html>\n", encoding="utf-8")

            result = check_preview_url(
                worktree,
                "http://localhost:8003/static/human_review.html",
                file_path="apps/flight_assistant/static/human_review.html",
                inspector=lambda port: PortProcess(
                    port=port,
                    pid=1234,
                    cwd=str(repo_root),
                    command="uvicorn",
                ),
            )

        self.assertFalse(result.ok)
        self.assertIsNone(result.http_status)
        self.assertIn("This preview will not include your AIT changes", result.message)
        self.assertIn(str(repo_root), result.message)
        self.assertIn(str(worktree), result.message)
        self.assertIn("ait dev stop --port 8003 --force", result.port_guard.fix_commands)
        self.assertIn(f"code {worktree.resolve()}", result.port_guard.fix_commands)

    def test_preview_guard_allows_current_worktree_and_validates_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)
            static_file = worktree / "apps" / "flight_assistant" / "static" / "human_review.html"
            static_file.parent.mkdir(parents=True)
            static_file.write_text("<html>ok</html>\n", encoding="utf-8")

            result = check_preview_url(
                worktree,
                "http://localhost:8003/static/human_review.html",
                file_path="apps/flight_assistant/static/human_review.html",
                inspector=lambda port: PortProcess(
                    port=port,
                    pid=5678,
                    cwd=str(worktree),
                    command="uvicorn",
                ),
                fetch=lambda url: 200,
            )

        self.assertTrue(result.ok)
        self.assertEqual(200, result.http_status)
        self.assertIn("returned HTTP 200", result.message)

    def test_preview_guard_reports_missing_static_file_before_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)

            result = check_preview_url(
                worktree,
                "http://localhost:8003/static/human_review.html",
                file_path="apps/flight_assistant/static/human_review.html",
                inspector=lambda port: PortProcess(
                    port=port,
                    pid=5678,
                    cwd=str(worktree),
                    command="uvicorn",
                ),
                fetch=lambda url: 200,
            )

        self.assertFalse(result.ok)
        self.assertIn("Preview file does not exist", result.message)

    def test_guard_reports_free_port_with_start_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)

            result = guard_preview_port(worktree, 8003, inspector=lambda port: None)

        self.assertFalse(result.ok)
        self.assertIn("Port 8003 is not serving anything", result.message)
        self.assertIn("ait run --port 8003 -- <command>", result.fix_commands[0])

    def test_start_dev_server_refuses_port_owned_by_main_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)

            with self.assertRaisesRegex(DevServerError, "will not include your AIT changes"):
                start_dev_server(
                    worktree,
                    ("unused-command",),
                    ports=(8003,),
                    inspector=lambda port: PortProcess(
                        port=port,
                        pid=1234,
                        cwd=str(repo_root),
                        command="uvicorn",
                    ),
                )

    def test_cli_dev_preview_outputs_cwd_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)
            static_file = worktree / "apps" / "flight_assistant" / "static" / "human_review.html"
            static_file.parent.mkdir(parents=True)
            static_file.write_text("<html>ok</html>\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(worktree):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "dev",
                            "preview",
                            "http://localhost:8003/static/human_review.html",
                            "--file",
                            "apps/flight_assistant/static/human_review.html",
                            "--format",
                            "json",
                        ],
                    ),
                    patch(
                        "ait.cli.dev.check_preview_url",
                        return_value=check_preview_url(
                            worktree,
                            "http://localhost:8003/static/human_review.html",
                            file_path="apps/flight_assistant/static/human_review.html",
                            inspector=lambda port: PortProcess(
                                port=port, pid=1234, cwd=str(repo_root), command="uvicorn"
                            ),
                        ),
                    ),
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(2, exit_code)
        self.assertFalse(payload["ok"])
        self.assertEqual(str(repo_root), payload["port_guard"]["process"]["cwd"])

    def test_cli_run_without_intent_uses_dev_server_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            _init_git_repo(repo_root)
            worktree = _add_ait_worktree(repo_root)
            stdout = io.StringIO()

            with chdir(worktree):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--port",
                            "8003",
                            "--",
                            sys.executable,
                            "-m",
                            "http.server",
                        ],
                    ),
                    patch("ait.cli.run.start_dev_server", return_value=()),
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertEqual("[]\n", stdout.getvalue())


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _add_ait_worktree(repo_root: Path) -> Path:
    worktree = repo_root / ".ait" / "workspaces" / "attempt-0001-test"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    head = _git_stdout(repo_root, "rev-parse", "HEAD")
    _git(repo_root, "worktree", "add", "--detach", str(worktree), head)
    return worktree


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
