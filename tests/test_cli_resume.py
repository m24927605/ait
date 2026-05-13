from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import create_attempt, create_intent
from ait.resume import ResumeResult, launch_resume_shell


class CliResumeTests(unittest.TestCase):
    def test_resume_print_outputs_latest_attempt_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "resume", "latest", "--print"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertEqual(f"{attempt.workspace_ref}\n", stdout.getvalue())

    def test_resume_json_returns_finish_steps_without_launching_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo_root):
                with (
                    patch("sys.argv", ["ait", "resume", "latest", "--json"]),
                    patch("ait.cli.resume.launch_resume_shell") as launch,
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertFalse(launch.called)
        self.assertIn(attempt.attempt_id, stdout.getvalue())
        self.assertIn(attempt.workspace_ref, stdout.getvalue())
        self.assertIn("ait attempt commit", stdout.getvalue())

    def test_resume_no_interactive_prints_cd_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "resume", "latest", "--no-interactive"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        text = stdout.getvalue()
        self.assertIn(f"cd {attempt.workspace_ref}", text)
        self.assertIn("continue editing", text)
        self.assertIn("ait apply", text)

    def test_launch_resume_shell_sanitizes_repo_wrappers_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            workspace = repo_root / ".ait" / "workspaces" / "attempt-0001"
            wrapper_dir = repo_root / ".ait" / "bin"
            workspace_wrapper_dir = workspace / ".ait" / "bin"
            workspace.mkdir(parents=True)
            result = ResumeResult(
                attempt_id="repo:01TEST",
                workspace_ref=str(workspace),
                repo_root=str(repo_root),
                status="active",
                reported_status="running",
                verified_status="pending",
                shell="/bin/sh",
                finish_steps=("git status",),
            )

            fake_path = os.pathsep.join(
                [str(wrapper_dir), "/usr/bin", str(workspace_wrapper_dir)]
            )
            with (
                patch.dict(os.environ, {"PATH": fake_path}),
                patch("ait.resume.subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess(["/bin/sh"], 0)
                exit_code = launch_resume_shell(result)

        self.assertEqual(0, exit_code)
        _, kwargs = run.call_args
        env = kwargs["env"]
        self.assertEqual(str(workspace), kwargs["cwd"])
        self.assertEqual("repo:01TEST", env["AIT_RESUME_ATTEMPT_ID"])
        self.assertEqual(str(workspace), env["AIT_WORKSPACE_REF"])
        self.assertEqual(["/usr/bin"], env["PATH"].split(os.pathsep))


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
