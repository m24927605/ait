from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def resolve_repo_root(repo_root: str | Path) -> Path:
    """Return the main repository root even when invoked from inside a worktree.

    All `ait` state (`.ait/` directory, SQLite database, daemon socket) is
    anchored to the main repository so that invoking `ait` from a worktree
    observes and mutates the same state as invoking it from the main
    checkout. Using `--git-common-dir` gives us the shared `.git` directory
    for both normal checkouts and worktrees; the main repo root is its
    parent.
    """
    root = Path(repo_root).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Not a git repository."
        raise ValueError(message)
    common_dir = Path(result.stdout.strip()).resolve()
    return common_dir.parent


def initialize_git_repo(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "init"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Unable to initialize git repository."
        raise ValueError(message)
    return resolve_repo_root(root)


def repository_has_commits(repo_root: str | Path) -> bool:
    root = resolve_repo_root(repo_root)
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def ensure_initial_commit(repo_root: str | Path) -> bool:
    root = resolve_repo_root(repo_root)
    if repository_has_commits(root):
        return False
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        add_result = subprocess.run(
            ["git", "add", "--", ".gitignore"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if add_result.returncode != 0:
            message = add_result.stderr.strip() or "Unable to stage .gitignore."
            raise ValueError(message)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "AIT",
        "GIT_AUTHOR_EMAIL": "ait@example.invalid",
        "GIT_COMMITTER_NAME": "AIT",
        "GIT_COMMITTER_EMAIL": "ait@example.invalid",
    }
    result = subprocess.run(
        [
            "git",
            "commit",
            "--allow-empty",
            "--no-verify",
            "-m",
            "chore: initialize repository for AIT",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Unable to create initial AIT baseline commit."
        raise ValueError(message)
    return True


def get_root_commit_oid(repo_root: str | Path) -> str:
    root = resolve_repo_root(repo_root)
    result = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "--reverse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Unable to determine root commit."
        if "ambiguous argument 'HEAD'" in message or "unknown revision" in message:
            raise ValueError("Repository has no commits.")
        raise ValueError(message)

    root_commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not root_commits:
        raise ValueError("Repository has no commits.")
    return root_commits[0]


def derive_repo_id(repo_root: str | Path, install_nonce: str) -> str:
    if not install_nonce:
        raise ValueError("install_nonce is required.")
    return f"{derive_repo_identity(repo_root)}:{install_nonce}"


def derive_repo_identity(repo_root: str | Path) -> str:
    try:
        return get_root_commit_oid(repo_root)
    except ValueError as exc:
        if "Repository has no commits." not in str(exc):
            raise
    root = resolve_repo_root(repo_root)
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]
    return f"unborn:{digest}"


def compose_repo_id(repo_identity: str, install_nonce: str) -> str:
    if not repo_identity:
        raise ValueError("repo_identity is required.")
    if not install_nonce:
        raise ValueError("install_nonce is required.")
    return f"{repo_identity}:{install_nonce}"
