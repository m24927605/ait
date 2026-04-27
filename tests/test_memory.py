from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_commit_for_attempt, create_attempt, create_intent
from ait.memory import build_repo_memory, render_repo_memory_text


class MemoryTests(unittest.TestCase):
    def test_build_repo_memory_summarizes_recent_attempts_and_hot_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            intent = create_intent(repo_root, title="Remember change", description=None, kind="feature")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
            worktree = Path(attempt.workspace_ref)
            (worktree / "memory.txt").write_text("remember me\n", encoding="utf-8")
            _git(worktree, "add", "memory.txt")
            create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="memory")

            memory = build_repo_memory(repo_root)
            text = render_repo_memory_text(memory)

            self.assertEqual(str(repo_root.resolve()), memory.repo_root)
            self.assertEqual(1, len(memory.recent_attempts))
            self.assertEqual("Remember change", memory.recent_attempts[0].intent_title)
            self.assertEqual(("memory.txt",), memory.recent_attempts[0].changed_files)
            self.assertEqual(("memory.txt",), memory.hot_files)
            self.assertIn("AIT Long-Term Repo Memory", text)
            self.assertIn("Remember change", text)
            self.assertIn("memory.txt", text)


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
