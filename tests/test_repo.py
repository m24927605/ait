from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.repo import resolve_repo_root


class ResolveRepoRootTests(unittest.TestCase):
    def test_returns_main_root_from_main_repo_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "main"
            repo.mkdir()
            _git(repo, "init")
            _seed_commit(repo)

            self.assertEqual(resolve_repo_root(repo).resolve(), repo.resolve())

    def test_returns_main_root_when_called_from_inside_worktree(self) -> None:
        # Regression for dogfood-session-1 Bug D: invoking ait from within a
        # worktree previously returned the worktree path, causing a separate
        # `.ait/` store to be created inside each worktree.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "main"
            repo.mkdir()
            _git(repo, "init")
            _seed_commit(repo)
            worktree = Path(tmp) / "worktree"
            _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")

            self.assertEqual(resolve_repo_root(worktree).resolve(), repo.resolve())

    def test_returns_main_root_from_nested_subdirectory_of_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "main"
            repo.mkdir()
            _git(repo, "init")
            _seed_commit(repo)
            worktree = Path(tmp) / "worktree"
            _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
            nested = worktree / "nested" / "deep"
            nested.mkdir(parents=True)

            self.assertEqual(resolve_repo_root(nested).resolve(), repo.resolve())

    def test_raises_for_non_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                resolve_repo_root(Path(tmp))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _seed_commit(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-m", "init")


if __name__ == "__main__":
    unittest.main()
