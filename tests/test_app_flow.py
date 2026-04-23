from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import (
    abandon_intent,
    create_commit_for_attempt,
    create_attempt,
    create_intent,
    discard_attempt,
    promote_attempt,
    show_attempt,
    show_intent,
    supersede_intent,
    verify_attempt,
)
from ait.db import connect_db, update_attempt
from ait.workspace import commit_message


class AppFlowTests(unittest.TestCase):
    def test_verify_and_promote_attempt_materializes_commits_and_changes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Fix auth", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "src").mkdir()
            (worktree / "src" / "auth.py").write_text("print('ok')\n", encoding="utf-8")
            _git(worktree, "add", "src/auth.py")
            _git(worktree, "commit", "-m", "add auth")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)
            promoted = promote_attempt(repo_root, attempt_id=attempt.attempt_id, target_ref="fix/auth")
            intent_view = show_intent(repo_root, intent_id=intent.intent_id)

            self.assertEqual("succeeded", verified.attempt["verified_status"])
            self.assertEqual(("src/auth.py",), verified.files["changed"])
            self.assertEqual(1, len(verified.commits))
            self.assertEqual("promoted", promoted.attempt["verified_status"])
            self.assertEqual("finished", intent_view.intent["status"])
            self.assertEqual("refs/heads/fix/auth", promoted.attempt["result_promotion_ref"])
            self.assertEqual(1, len(intent_view.attempts))
            self.assertEqual(
                _git_stdout(repo_root, "rev-parse", "--verify", "refs/heads/fix/auth"),
                promoted.commits[0]["commit_oid"],
            )

    def test_attempt_commit_writes_git_trailers_and_updates_attempt_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Trailer", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "feature.py").write_text("flag = True\n", encoding="utf-8")
            _git(worktree, "add", "feature.py")

            result = create_commit_for_attempt(
                repo_root,
                attempt_id=attempt.attempt_id,
                message="add feature",
            )

            self.assertEqual("succeeded", result.attempt["verified_status"])
            self.assertEqual(("feature.py",), result.files["changed"])
            self.assertEqual(1, len(result.commits))
            message = commit_message(attempt.workspace_ref, result.commits[0]["commit_oid"])
            self.assertIn("Intent-Id: " + intent.intent_id, message)
            self.assertIn("Attempt-Id: " + attempt.attempt_id, message)

    def test_discard_attempt_marks_record_and_removes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Try fix", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            workspace = Path(attempt.workspace_ref)

            discarded = discard_attempt(repo_root, attempt_id=attempt.attempt_id)
            shown = show_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("discarded", discarded.attempt["verified_status"])
            self.assertEqual("finished", discarded.attempt["reported_status"])
            self.assertFalse(workspace.exists())
            self.assertEqual("discarded", shown.attempt["verified_status"])

    def test_abandon_intent_updates_status_and_show_aggregates_attempt_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Aggregate", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "lib.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "lib.py")
            _git(worktree, "commit", "-m", "add lib")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()
            verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            abandoned = abandon_intent(repo_root, intent_id=intent.intent_id)

            self.assertEqual("abandoned", abandoned.intent["status"])
            self.assertEqual(("lib.py",), abandoned.files["changed"])
            self.assertEqual(1, len(abandoned.commit_oids))

    def test_supersede_intent_marks_original_superseded_and_writes_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")

            result = supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                edge = conn.execute(
                    """
                    SELECT parent_intent_id, child_intent_id, edge_type
                    FROM intent_edges
                    WHERE parent_intent_id = ? AND child_intent_id = ?
                    """,
                    (original.intent_id, replacement.intent_id),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual("superseded", result.intent["status"])
            self.assertEqual("superseded_by", edge["edge_type"])

    def test_superseded_intent_rejects_new_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                create_attempt(repo_root, intent_id=original.intent_id)

            self.assertIn("superseded", str(raised.exception))

    def test_superseded_intent_rejects_commit_for_existing_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=original.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "edge.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "edge.py")
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                create_commit_for_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    message="edge",
                )

            self.assertIn("superseded", str(raised.exception))

    def test_superseded_intent_rejects_promotion_for_existing_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            original = create_intent(repo_root, title="Original", description=None, kind="bugfix")
            replacement = create_intent(repo_root, title="Replacement", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=original.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "drop.py").write_text("x = 1\n", encoding="utf-8")
            _git(worktree, "add", "drop.py")
            _git(worktree, "commit", "-m", "drop")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                )
            finally:
                conn.close()
            supersede_intent(
                repo_root,
                intent_id=original.intent_id,
                by_intent_id=replacement.intent_id,
            )

            with self.assertRaises(ValueError) as raised:
                promote_attempt(
                    repo_root,
                    attempt_id=attempt.attempt_id,
                    target_ref="fix/drop",
                )

            self.assertIn("superseded", str(raised.exception))

    def test_abandoned_intent_rejects_promoted_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Abandoned", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)
            worktree = Path(attempt.workspace_ref)
            _git(worktree, "config", "user.email", "test@example.com")
            _git(worktree, "config", "user.name", "Test User")
            (worktree / "reject.py").write_text("value = 1\n", encoding="utf-8")
            _git(worktree, "add", "reject.py")
            _git(worktree, "commit", "-m", "reject")
            abandon_intent(repo_root, intent_id=intent.intent_id)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    ended_at="2026-04-23T00:10:00Z",
                    result_exit_code=0,
                    result_promotion_ref="refs/heads/fix/reject",
                )
            finally:
                conn.close()

            verified = verify_attempt(repo_root, attempt_id=attempt.attempt_id)

            self.assertEqual("failed", verified.attempt["verified_status"])


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
