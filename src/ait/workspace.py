from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


class WorkspaceError(RuntimeError):
    """Raised when attempt workspace provisioning fails."""


@dataclass(slots=True, frozen=True)
class AttemptWorkspaceLocation:
    attempt_id: str
    ordinal: int
    workspaces_root: Path
    worktree_name: str
    worktree_path: Path


@dataclass(slots=True, frozen=True)
class AttemptWorkspaceResult:
    attempt_id: str
    ordinal: int
    workspace_ref: str
    worktree_path: Path
    worktree_name: str
    workspaces_root: Path
    base_ref_oid: str
    base_ref_name: str | None


def get_workspaces_root(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / ".ait" / "workspaces"


def get_attempt_worktree_name(attempt_id: str, ordinal: int) -> str:
    if ordinal < 1:
        raise ValueError("ordinal must be >= 1")
    slug = attempt_id.rsplit(":", 1)[-1].lower()
    return f"attempt-{ordinal:04d}-{slug}"


def get_attempt_workspace_location(
    repo_root: str | Path,
    attempt_id: str,
    ordinal: int,
) -> AttemptWorkspaceLocation:
    workspaces_root = get_workspaces_root(repo_root)
    worktree_name = get_attempt_worktree_name(attempt_id=attempt_id, ordinal=ordinal)
    worktree_path = workspaces_root / worktree_name
    return AttemptWorkspaceLocation(
        attempt_id=attempt_id,
        ordinal=ordinal,
        workspaces_root=workspaces_root,
        worktree_name=worktree_name,
        worktree_path=worktree_path,
    )


def get_base_ref(repo_root: str | Path) -> tuple[str, str | None]:
    root = Path(repo_root).resolve()
    base_ref_oid = _git_stdout(root, "rev-parse", "--verify", "HEAD")
    base_ref_name = _git_stdout(
        root,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
        allow_failure=True,
    )
    return base_ref_oid, base_ref_name or None


def create_attempt_workspace(
    repo_root: str | Path,
    attempt_id: str,
    ordinal: int,
) -> AttemptWorkspaceResult:
    root = Path(repo_root).resolve()
    location = get_attempt_workspace_location(
        repo_root=root,
        attempt_id=attempt_id,
        ordinal=ordinal,
    )
    base_ref_oid, base_ref_name = get_base_ref(root)
    location.workspaces_root.mkdir(parents=True, exist_ok=True)

    if location.worktree_path.exists():
        raise WorkspaceError(
            f"attempt workspace path already exists: {location.worktree_path}"
        )

    _git_run(
        root,
        "worktree",
        "add",
        "--detach",
        str(location.worktree_path),
        base_ref_oid,
    )

    return AttemptWorkspaceResult(
        attempt_id=attempt_id,
        ordinal=ordinal,
        workspace_ref=str(location.worktree_path),
        worktree_path=location.worktree_path,
        worktree_name=location.worktree_name,
        workspaces_root=location.workspaces_root,
        base_ref_oid=base_ref_oid,
        base_ref_name=base_ref_name,
    )


def _git_stdout(
    repo_root: Path,
    *args: str,
    allow_failure: bool = False,
) -> str:
    completed = _git_run(repo_root, *args, allow_failure=allow_failure)
    return completed.stdout.strip()


def _git_run(
    repo_root: Path,
    *args: str,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not allow_failure:
        stderr = completed.stderr.strip()
        raise WorkspaceError(stderr or f"git {' '.join(args)} failed")
    return completed
