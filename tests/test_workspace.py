from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from ait.workspace import (
    WorkspaceError,
    create_attempt_workspace,
    get_attempt_workspace_location,
    get_attempt_worktree_name,
    get_base_ref,
    get_workspaces_root,
    ref_contains_commits,
)


class WorkspaceTests(unittest.TestCase):
    def test_get_attempt_worktree_name_uses_stable_ordinal_and_attempt_suffix(self) -> None:
        self.assertEqual(
            get_attempt_worktree_name("repo:01ARZ3NDEKTSV4RRFFQ69G5FAA", 7),
            "attempt-0007-01arz3ndektsv4rrffq69g5faa",
        )

    def test_get_attempt_worktree_name_rejects_non_positive_ordinal(self) -> None:
        with self.assertRaisesRegex(ValueError, "ordinal"):
            get_attempt_worktree_name("repo:attempt", 0)

    def test_get_attempt_workspace_location_is_under_dot_ait_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            location = get_attempt_workspace_location(repo_root, "repo:attempt-01", 3)

            self.assertEqual(location.workspaces_root, get_workspaces_root(repo_root))
            self.assertEqual(
                location.worktree_path,
                repo_root.resolve()
                / ".ait"
                / "workspaces"
                / "attempt-0003-attempt-01",
            )

    def test_get_base_ref_returns_head_oid_and_branch_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            base_ref_oid, base_ref_name = get_base_ref(repo_root)

            self.assertEqual(base_ref_oid, _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"))
            self.assertEqual(
                base_ref_name,
                _git_stdout(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD"),
            )

    def test_create_attempt_workspace_provisions_detached_git_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = create_attempt_workspace(
                repo_root=repo_root,
                attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                ordinal=1,
            )

            worktree_path = repo_root.resolve() / ".ait" / "workspaces" / result.worktree_name
            self.assertEqual(result.worktree_path, worktree_path)
            self.assertEqual(result.workspace_ref, str(worktree_path))
            self.assertTrue(worktree_path.exists())
            self.assertTrue((worktree_path / ".git").exists())
            self.assertEqual(
                result.base_ref_oid,
                _git_stdout(repo_root, "rev-parse", "--verify", "HEAD"),
            )
            self.assertEqual(_git_stdout(worktree_path, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")
            self.assertEqual(
                _git_stdout(worktree_path, "rev-parse", "--verify", "HEAD"),
                result.base_ref_oid,
            )

    def test_create_attempt_workspace_rejects_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            create_attempt_workspace(
                repo_root=repo_root,
                attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                ordinal=1,
            )

            with self.assertRaisesRegex(WorkspaceError, "already exists"):
                create_attempt_workspace(
                    repo_root=repo_root,
                    attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                    ordinal=1,
                )

    def test_ref_contains_commits_returns_false_for_empty_commit_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            branch = _git_stdout(repo_root, "symbolic-ref", "--quiet", "HEAD")

            self.assertFalse(ref_contains_commits(repo_root, branch, ()))


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
