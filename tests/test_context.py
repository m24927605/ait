from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ait.app import create_commit_for_attempt, create_attempt, create_intent, verify_attempt
from ait.context import build_agent_context, render_agent_context_text
from ait.db import connect_db, update_attempt


class ContextTests(unittest.TestCase):
    def test_build_agent_context_summarizes_attempt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Context", description="summarize", kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="shell:test")
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "context.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "context.py")
            create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message="context")

            context = build_agent_context(repo_root, intent_id=intent.intent_id)
            text = render_agent_context_text(context)

            self.assertEqual(intent.intent_id, context.intent["id"])
            self.assertEqual(1, len(context.attempts))
            self.assertEqual(("context.py",), context.files["changed"])
            self.assertIn("Intent: Context", text)
            self.assertIn("files.changed: context.py", text)
            self.assertIn("inspect latest succeeded attempt", text)

    def test_agent_context_includes_failed_attempt_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Failed", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="shell:test")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-26T00:00:00Z",
                    result_exit_code=7,
                )
            finally:
                conn.close()
            verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            text = render_agent_context_text(
                build_agent_context(repo_root, intent_id=intent.intent_id)
            )

            self.assertIn("verified=failed", text)
            self.assertIn("review latest failed attempt", text)

    def test_agent_context_redacts_intent_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            secret = "sk-ant-api03-" + ("a" * 32)
            intent = create_intent(
                repo_root,
                title=f"Use {secret}",
                description=f"Authorization: Bearer {'b' * 32}",
                kind="bugfix",
            )

            text = render_agent_context_text(build_agent_context(repo_root, intent_id=intent.intent_id))

            self.assertNotIn(secret, text)
            self.assertNotIn("Bearer " + ("b" * 32), text)
            self.assertIn("[REDACTED]", text)


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
