from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.runner import run_agent_command


class RunnerTests(unittest.TestCase):
    def test_run_agent_command_records_command_and_finishes_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Run command",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                ],
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual("shell:test", result.attempt.attempt["agent_id"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_tool_calls"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_commands_run"])
            self.assertTrue((Path(result.workspace_ref) / "agent.txt").exists())

    def test_run_agent_command_returns_process_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Fail command",
                agent_id="shell:test",
                command=[sys.executable, "-c", "raise SystemExit(7)"],
            )

            self.assertEqual(7, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("failed", result.attempt.attempt["verified_status"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_commands_run"])

    def test_run_agent_command_can_write_context_file_for_wrapped_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Context file",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "p=Path(os.environ['AIT_CONTEXT_FILE']);"
                        "Path('context-copy.txt').write_text(p.read_text())"
                    ),
                ],
                with_context=True,
            )

            copied = Path(result.workspace_ref) / "context-copy.txt"
            self.assertEqual(0, result.exit_code)
            self.assertTrue((Path(result.workspace_ref) / ".ait-context.md").exists())
            self.assertIn("Intent: Context file", copied.read_text(encoding="utf-8"))


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
