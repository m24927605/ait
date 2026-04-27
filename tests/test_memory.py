from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path

from ait.app import create_commit_for_attempt, create_attempt, create_intent
from ait.db import connect_db, run_migrations
from ait.memory import (
    add_memory_note,
    build_repo_memory,
    list_memory_notes,
    remove_memory_note,
    render_repo_memory_text,
    search_repo_memory,
)
from ait.memory_policy import init_memory_policy


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

    def test_memory_notes_can_be_added_listed_filtered_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            note = add_memory_note(
                repo_root,
                topic="architecture",
                body="Keep API adapters thin.",
            )

            self.assertEqual((note,), list_memory_notes(repo_root, topic="architecture"))
            memory = build_repo_memory(repo_root, topic="architecture")
            text = render_repo_memory_text(memory)
            self.assertEqual((note,), memory.notes)
            self.assertIn("Curated Notes:", text)
            self.assertIn("Keep API adapters thin.", text)

            self.assertTrue(remove_memory_note(repo_root, note_id=note.id))
            self.assertEqual((), list_memory_notes(repo_root))

    def test_memory_filters_attempts_by_path_and_promoted_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            src_attempt = _commit_attempt(repo_root, "Source change", "src/app.py")
            docs_attempt = _commit_attempt(repo_root, "Docs change", "docs/guide.md")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            run_migrations(conn)
            with conn:
                conn.execute(
                    "UPDATE attempts SET verified_status = 'promoted' WHERE id = ?",
                    (src_attempt,),
                )

            src_memory = build_repo_memory(repo_root, path_filter="src/")
            self.assertEqual(1, len(src_memory.recent_attempts))
            self.assertEqual(src_attempt, src_memory.recent_attempts[0].attempt_id)
            self.assertEqual(("src/app.py",), src_memory.hot_files)

            promoted_memory = build_repo_memory(repo_root, promoted_only=True)
            self.assertEqual(1, len(promoted_memory.recent_attempts))
            self.assertEqual(src_attempt, promoted_memory.recent_attempts[0].attempt_id)
            self.assertNotEqual(docs_attempt, promoted_memory.recent_attempts[0].attempt_id)

    def test_render_repo_memory_text_compacts_to_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(repo_root, body="x" * 400)

            text = render_repo_memory_text(build_repo_memory(repo_root), budget_chars=160)

            self.assertLessEqual(len(text), 160)
            self.assertIn("ait memory compacted", text)

    def test_search_repo_memory_finds_notes_and_attempt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="architecture",
                body="Adapters should keep repo-local context handoff stable.",
            )
            attempt_id = _commit_attempt(repo_root, "Refactor billing adapter", "src/billing.py")

            note_results = search_repo_memory(repo_root, "context handoff")
            attempt_results = search_repo_memory(repo_root, "billing adapter")

            self.assertEqual("note", note_results[0].kind)
            self.assertIn("repo-local context", note_results[0].text)
            self.assertEqual("attempt", attempt_results[0].kind)
            self.assertEqual(attempt_id, attempt_results[0].id)
            self.assertEqual(["src/billing.py"], attempt_results[0].metadata["changed_files"])
            self.assertEqual("vector", attempt_results[0].metadata["ranker"])

    def test_search_repo_memory_can_use_lexical_ranker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="release",
                body="Run smoke tests before publishing packages.",
            )

            results = search_repo_memory(repo_root, "smoke packages", ranker="lexical")

            self.assertEqual("note", results[0].kind)
            self.assertEqual("lexical", results[0].metadata["ranker"])

    def test_search_repo_memory_rejects_unknown_ranker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            with self.assertRaises(ValueError):
                search_repo_memory(repo_root, "anything", ranker="unknown")

    def test_memory_notes_are_redacted_in_rendering_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_memory_note(
                repo_root,
                topic="security",
                body="Do not leak GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456",
            )

            text = render_repo_memory_text(build_repo_memory(repo_root))
            results = search_repo_memory(repo_root, "redacted")

            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", text)
            self.assertIn("[REDACTED]", text)
            self.assertIn("redacted: true", text)
            self.assertEqual("note", results[0].kind)
            self.assertTrue(results[0].metadata["redacted"])

    def test_memory_policy_excludes_sensitive_changed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_memory_policy(repo_root)
            policy_path = repo_root / ".ait" / "memory-policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "exclude_paths": [".env", "secrets/"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                    }
                ),
                encoding="utf-8",
            )

            attempt_id = _commit_attempt_with_files(
                repo_root,
                "Mixed policy change",
                {
                    ".env": "SECRET_VALUE=hidden\n",
                    "src/app.py": "visible change\n",
                    "secrets/token.txt": "hidden\n",
                },
            )

            memory = build_repo_memory(repo_root)
            search_results = search_repo_memory(repo_root, "src/app.py")

            self.assertEqual(attempt_id, memory.recent_attempts[0].attempt_id)
            self.assertEqual(("src/app.py",), memory.recent_attempts[0].changed_files)
            self.assertEqual(("src/app.py",), memory.hot_files)
            self.assertNotIn(".env", render_repo_memory_text(memory))
            self.assertEqual(["src/app.py"], search_results[0].metadata["changed_files"])


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _commit_attempt(repo_root: Path, title: str, file_path: str) -> str:
    intent = create_intent(repo_root, title=title, description=None, kind="feature")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
    worktree = Path(attempt.workspace_ref)
    target = worktree / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{title}\n", encoding="utf-8")
    _git(worktree, "add", file_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id


def _commit_attempt_with_files(repo_root: Path, title: str, files: dict[str, str]) -> str:
    intent = create_intent(repo_root, title=title, description=None, kind="feature")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id="claude-code:test")
    worktree = Path(attempt.workspace_ref)
    for file_path, contents in files.items():
        target = worktree / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
        _git(worktree, "add", file_path)
    create_commit_for_attempt(repo_root, attempt_id=attempt.attempt_id, message=title)
    return attempt.attempt_id


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
