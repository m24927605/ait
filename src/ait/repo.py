from __future__ import annotations

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
        raise ValueError(message)

    root_commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not root_commits:
        raise ValueError("Repository has no commits.")
    return root_commits[0]


def derive_repo_id(repo_root: str | Path, install_nonce: str) -> str:
    if not install_nonce:
        raise ValueError("install_nonce is required.")
    return f"{get_root_commit_oid(repo_root)}:{install_nonce}"
