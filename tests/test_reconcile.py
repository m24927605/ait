from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import create_attempt, create_intent
from ait.db import connect_db, insert_attempt_commit
from ait.hooks import install_post_rewrite_hook
from ait.reconcile import reconcile_repo


class ReconcileTests(unittest.TestCase):
    def test_reconcile_updates_attempt_commit_mapping_from_post_rewrite_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            intent = create_intent(repo_root, title="Rewrite", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                insert_attempt_commit(
                    conn,
                    attempt_id=attempt.attempt_id,
                    commit_oid="oldcommit",
                    base_commit_oid="baseold",
                    touched_files=("app.py",),
                )
            finally:
                conn.close()

            (repo_root / ".ait" / "post-rewrite.last").write_text(
                "oldcommit newcommit\nbaseold basenew\n",
                encoding="utf-8",
            )
            (repo_root / ".ait" / "manual-reconcile-required").write_text("", encoding="utf-8")

            result = reconcile_repo(repo_root)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                row = conn.execute(
                    "SELECT commit_oid, base_commit_oid FROM attempt_commits WHERE attempt_id = ?",
                    (attempt.attempt_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(2, result.processed_mappings)
            self.assertEqual(0, result.unmapped_mappings)
            self.assertEqual("newcommit", row["commit_oid"])
            self.assertEqual("basenew", row["base_commit_oid"])
            self.assertFalse((repo_root / ".ait" / "post-rewrite.last").exists())
            self.assertFalse((repo_root / ".ait" / "manual-reconcile-required").exists())

    def test_reconcile_surfaces_unmapped_rewrite_mapping_for_manual_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            create_intent(repo_root, title="Rewrite", description=None, kind="bugfix")

            post_rewrite = repo_root / ".ait" / "post-rewrite.last"
            post_rewrite.write_text("unknownold unknownnew\n", encoding="utf-8")

            result = reconcile_repo(repo_root)

            marker = repo_root / ".ait" / "manual-reconcile-required"
            self.assertEqual(1, result.processed_mappings)
            self.assertEqual(0, result.updated_commit_rows)
            self.assertEqual(0, result.updated_base_rows)
            self.assertEqual(1, result.unmapped_mappings)
            self.assertTrue(result.manual_repair_required)
            self.assertTrue(post_rewrite.exists())
            self.assertIn("unknownold unknownnew", marker.read_text(encoding="utf-8"))

    def test_reconcile_handles_chained_amends_from_real_post_rewrite_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            install_post_rewrite_hook(repo_root)
            intent = create_intent(repo_root, title="Chained amend", description=None, kind="bugfix")
            attempt = create_attempt(repo_root, intent_id=intent.intent_id)

            tracked = repo_root / "tracked.txt"
            tracked.write_text("v1\n", encoding="utf-8")
            _git(repo_root, "add", "tracked.txt")
            _git(repo_root, "commit", "-m", "tracked v1")
            base_oid = _git_stdout(repo_root, "rev-parse", "HEAD~1")
            current_oid = _git_stdout(repo_root, "rev-parse", "HEAD")
            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                insert_attempt_commit(
                    conn,
                    attempt_id=attempt.attempt_id,
                    commit_oid=current_oid,
                    base_commit_oid=base_oid,
                    touched_files=("tracked.txt",),
                )
            finally:
                conn.close()

            for index in range(2, 5):
                tracked.write_text(f"v{index}\n", encoding="utf-8")
                _git(repo_root, "add", "tracked.txt")
                _git(repo_root, "commit", "--amend", "-m", f"tracked v{index}")
                current_oid = _git_stdout(repo_root, "rev-parse", "HEAD")

                result = reconcile_repo(repo_root)

                conn = connect_db(repo_root / ".ait" / "state.sqlite3")
                try:
                    row = conn.execute(
                        "SELECT commit_oid FROM attempt_commits WHERE attempt_id = ?",
                        (attempt.attempt_id,),
                    ).fetchone()
                finally:
                    conn.close()
                self.assertEqual(1, result.processed_mappings)
                self.assertEqual(1, result.updated_commit_rows)
                self.assertEqual(0, result.unmapped_mappings)
                self.assertEqual(current_oid, row["commit_oid"])
                self.assertFalse((repo_root / ".ait" / "post-rewrite.last").exists())


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
