from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_repo_root(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Not a git repository."
        raise ValueError(message)
    return Path(result.stdout.strip()).resolve()


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
