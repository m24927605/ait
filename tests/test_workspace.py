from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ait.workspace import (
    WorkspaceError,
    create_attempt_workspace,
    get_attempt_workspace_location,
    get_attempt_worktree_name,
    get_base_ref,
    get_workspaces_root,
    ref_contains_commits,
    remove_attempt_workspace,
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

    def test_create_attempt_workspace_repairs_poetry_sibling_path_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            repo_root = parent / "repo-a"
            sibling = parent / "repo-b"
            sibling.mkdir()
            (sibling / "pyproject.toml").write_text(
                """
[tool.poetry]
name = "repo-b"
version = "0.1.0"
description = ""
authors = ["Test <test@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
""".lstrip(),
                encoding="utf-8",
            )
            repo_root.mkdir()
            _init_git_repo(repo_root)
            (repo_root / "pyproject.toml").write_text(
                """
[tool.poetry]
name = "repo-a"
version = "0.1.0"
description = ""
authors = ["Test <test@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
repo-b = { path = "../repo-b", develop = true }
""".lstrip(),
                encoding="utf-8",
            )
            _git(repo_root, "add", "pyproject.toml")
            _git(repo_root, "commit", "-m", "add poetry project")
            bin_dir = parent / "bin"
            _write_fake_poetry(bin_dir)

            with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                result = create_attempt_workspace(
                    repo_root=repo_root,
                    attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                    ordinal=1,
                )

            worktree_path = result.worktree_path
            repaired_link = repo_root / ".ait" / "workspaces" / "repo-b"
            self.assertTrue(repaired_link.is_symlink())
            self.assertEqual(repaired_link.resolve(), sibling.resolve())
            self.assertTrue((worktree_path / ".venv" / "bin" / "python").exists())
            settings = json.loads((worktree_path / ".vscode" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(
                settings["python.defaultInterpreterPath"],
                str(worktree_path / ".venv" / "bin" / "python"),
            )
            metadata = repo_root / ".ait" / "workspaces" / f"{result.worktree_name}.python-env.json"
            self.assertTrue(metadata.exists())
            status = _git_stdout(worktree_path, "status", "--short", "--ignored")
            self.assertIn("!! .venv/", status)
            self.assertIn("!! .vscode/", status)
            self.assertIn("!! poetry.toml", status)

            remove_attempt_workspace(worktree_path)

            self.assertFalse(repaired_link.exists())
            self.assertFalse(metadata.exists())

    def test_create_attempt_workspace_fails_when_source_path_dependency_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo-a"
            repo_root.mkdir()
            _init_git_repo(repo_root)
            (repo_root / "pyproject.toml").write_text(
                """
[tool.poetry]
name = "repo-a"
version = "0.1.0"
description = ""
authors = ["Test <test@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
missing = { path = "../missing-repo", develop = true }
""".lstrip(),
                encoding="utf-8",
            )
            _git(repo_root, "add", "pyproject.toml")
            _git(repo_root, "commit", "-m", "add missing path dependency")

            with patch.dict(os.environ, {"AIT_SKIP_PYTHON_ENV_SETUP": "1"}):
                with self.assertRaisesRegex(WorkspaceError, "local path dependency cannot be resolved"):
                    create_attempt_workspace(
                        repo_root=repo_root,
                        attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                        ordinal=1,
                    )

            location = get_attempt_workspace_location(
                repo_root,
                "repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                1,
            )
            self.assertFalse(location.worktree_path.exists())

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

    def test_create_attempt_workspace_cleans_directory_after_git_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            def fail_after_mkdir(root: Path, *args: str, allow_failure: bool = False):
                del root, allow_failure
                if args[:2] == ("worktree", "add"):
                    worktree_path = Path(args[-2])
                    worktree_path.mkdir(parents=True)
                    raise WorkspaceError("simulated worktree add failure")
                return subprocess.CompletedProcess(["git", *args], 0, "", "")

            with patch("ait.workspace._git_run", side_effect=fail_after_mkdir):
                with self.assertRaisesRegex(WorkspaceError, "simulated"):
                    create_attempt_workspace(
                        repo_root=repo_root,
                        attempt_id="repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                        ordinal=2,
                    )

            location = get_attempt_workspace_location(
                repo_root,
                "repo:01ARZ3NDEKTSV4RRFFQ69G5FAA",
                2,
            )
            self.assertFalse(location.worktree_path.exists())

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


def _write_fake_poetry(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    poetry = bin_dir / "poetry"
    poetry.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys

cmd = sys.argv[1:]
cwd = Path.cwd()
if cmd[:4] == ["config", "virtualenvs.in-project", "true", "--local"]:
    (cwd / "poetry.toml").write_text("[virtualenvs]\\nin-project = true\\n", encoding="utf-8")
    raise SystemExit(0)
if cmd == ["check"]:
    if not (cwd.parent / "repo-b").exists():
        print("Path ../repo-b does not exist", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0)
if cmd == ["install"]:
    python = cwd / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("#!/usr/bin/env python3\\n", encoding="utf-8")
    raise SystemExit(0)
if cmd == ["env", "info", "--path"]:
    print(cwd / ".venv")
    raise SystemExit(0)
print("unsupported fake poetry command: " + " ".join(cmd), file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    poetry.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
