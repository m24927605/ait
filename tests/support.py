from __future__ import annotations

import os
import subprocess
from pathlib import Path


_GIT_AUTHOR_ENV = {
    "GIT_AUTHOR_NAME": "AIT Tests",
    "GIT_AUTHOR_EMAIL": "ait@example.invalid",
    "GIT_COMMITTER_NAME": "AIT Tests",
    "GIT_COMMITTER_EMAIL": "ait@example.invalid",
}


def init_git_repo(repo_root: Path, *, branch: str | None = None, readme_text: str = "test\n") -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    init_args = ["git", "init", "-q"]
    if branch is not None:
        init_args.extend(["-b", branch])
    _run(init_args, cwd=repo_root)
    (repo_root / "README.md").write_text(readme_text, encoding="utf-8")
    git(repo_root, "add", "README.md")
    git(repo_root, "commit", "-q", "--no-gpg-sign", "--no-verify", "-m", "init")


def git(repo_root: Path, *args: str) -> None:
    _run(["git", *args], cwd=repo_root)


def git_stdout(repo_root: Path, *args: str) -> str:
    return _run(["git", *args], cwd=repo_root).stdout.strip()


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env={**os.environ, **_GIT_AUTHOR_ENV},
        check=True,
        capture_output=True,
        text=True,
    )
