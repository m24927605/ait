from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from ait.workspace import commit_stats


class CommitStatsTests(unittest.TestCase):
    def test_text_only_commit_returns_exact_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "a.txt").write_text("one\n", encoding="utf-8")
            _commit(repo, "seed")

            (repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            (repo / "b.txt").write_text("new\n", encoding="utf-8")
            oid = _commit(repo, "add lines")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertEqual(insertions, 3)
            self.assertEqual(deletions, 0)
            self.assertIn("a.txt", touched)
            self.assertIn("b.txt", touched)

    def test_binary_only_commit_returns_none_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)

            (repo / "binary.dat").write_bytes(b"\x7fELF" + b"\x00" * 1024)
            oid = _commit(repo, "binary")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertIsNone(insertions)
            self.assertIsNone(deletions)
            self.assertIn("binary.dat", touched)

    def test_pure_deletion_commit_reports_only_deletions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "doomed.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            _commit(repo, "seed")

            (repo / "doomed.txt").unlink()
            oid = _commit(repo, "delete")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertEqual(insertions, 0)
            self.assertEqual(deletions, 3)
            self.assertIn("doomed.txt", touched)

    def test_mode_only_change_returns_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            script = repo / "script.sh"
            script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
            _commit(repo, "seed")

            script.chmod(0o755)
            oid = _commit(repo, "make exec")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertEqual(insertions, 0)
            self.assertEqual(deletions, 0)
            self.assertIn("script.sh", touched)

    def test_mixed_text_then_binary_returns_none_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "text.txt").write_text("hi\n", encoding="utf-8")
            _commit(repo, "seed")

            (repo / "text.txt").write_text("hi\nthere\n", encoding="utf-8")
            (repo / "zbinary.dat").write_bytes(b"\x00" * 1024)
            oid = _commit(repo, "text then binary")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertIsNone(insertions)
            self.assertIsNone(deletions)
            self.assertIn("text.txt", touched)
            self.assertIn("zbinary.dat", touched)

    def test_mixed_binary_before_text_does_not_crash(self) -> None:
        """Regression: numstat lists files alphabetically, so a binary path
        sorting before a text path used to crash with TypeError on the next
        text accumulation (None += int)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "text.txt").write_text("hi\n", encoding="utf-8")
            _commit(repo, "seed")

            (repo / "binary.dat").write_bytes(b"\x00" * 1024)
            (repo / "text.txt").write_text("hi\nthere\n", encoding="utf-8")
            oid = _commit(repo, "binary then text")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertIsNone(insertions)
            self.assertIsNone(deletions)
            self.assertIn("binary.dat", touched)
            self.assertIn("text.txt", touched)

    def test_venv_mixed_commit_does_not_crash(self) -> None:
        """Regression: simulates a dispatched agent committing a .venv/
        directory alongside source code — the case that originally surfaced
        the bug. The leading '.' makes the venv binary sort before code.py."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            (repo / "code.py").write_text("print('hi')\n", encoding="utf-8")
            _commit(repo, "seed")

            (repo / "code.py").write_text("print('hi')\nprint('there')\n", encoding="utf-8")
            venv_bin = repo / ".venv311" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_bytes(b"\x7fELF" + b"\x00" * 1024)
            oid = _commit(repo, "code + venv binary")

            insertions, deletions, touched = commit_stats(repo, oid)

            self.assertIsNone(insertions)
            self.assertIsNone(deletions)
            self.assertIn("code.py", touched)
            self.assertIn(".venv311/bin/python", touched)


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / ".gitseed").write_text("seed\n", encoding="utf-8")
    _git(repo_root, "add", ".gitseed")
    _git(repo_root, "commit", "-m", "root")


def _commit(repo_root: Path, message: str) -> str:
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
