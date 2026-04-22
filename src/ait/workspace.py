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


def remove_attempt_workspace(workspace_ref: str | Path) -> None:
    worktree_path = Path(workspace_ref).resolve()
    if not worktree_path.exists():
        return
    repo_root = _resolve_worktree_repo_root(worktree_path)
    _git_run(
        repo_root,
        "worktree",
        "remove",
        "--force",
        str(worktree_path),
    )


def list_attempt_commit_oids(workspace_ref: str | Path, base_ref_oid: str) -> tuple[str, ...]:
    worktree_path = Path(workspace_ref).resolve()
    output = _git_stdout(
        worktree_path,
        "rev-list",
        "--reverse",
        f"{base_ref_oid}..HEAD",
        allow_failure=True,
    )
    if not output:
        return ()
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def commit_parent_oid(workspace_ref: str | Path, commit_oid: str) -> str | None:
    worktree_path = Path(workspace_ref).resolve()
    line = _git_stdout(worktree_path, "rev-list", "--parents", "-n", "1", commit_oid)
    parts = [part for part in line.split() if part]
    if len(parts) <= 1:
        return None
    return parts[1]


def commit_stats(
    workspace_ref: str | Path,
    commit_oid: str,
) -> tuple[int | None, int | None, tuple[str, ...]]:
    worktree_path = Path(workspace_ref).resolve()
    output = _git_stdout(
        worktree_path,
        "show",
        "--numstat",
        "--format=",
        commit_oid,
    )
    insertions = 0
    deletions = 0
    touched_files: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add_text, del_text, file_path = parts
        if add_text.isdigit():
            insertions += int(add_text)
        else:
            insertions = None
        if del_text.isdigit():
            deletions += int(del_text)
        else:
            deletions = None
        touched_files.append(file_path)
    return insertions, deletions, tuple(touched_files)


def ref_contains_commits(repo_root: str | Path, ref_name: str, commit_oids: tuple[str, ...]) -> bool:
    root = Path(repo_root).resolve()
    ref_oid = _git_stdout(root, "rev-parse", "--verify", ref_name, allow_failure=True)
    if not ref_oid:
        return False
    for commit_oid in commit_oids:
        merge_base = _git_stdout(root, "merge-base", commit_oid, ref_name, allow_failure=True)
        if merge_base != commit_oid:
            return False
    return True


def update_ref_to_workspace_head(repo_root: str | Path, ref_name: str, workspace_ref: str | Path) -> str:
    root = Path(repo_root).resolve()
    worktree_path = Path(workspace_ref).resolve()
    head_oid = _git_stdout(worktree_path, "rev-parse", "--verify", "HEAD")
    _git_run(root, "update-ref", ref_name, head_oid)
    return head_oid


def _resolve_worktree_repo_root(worktree_path: Path) -> Path:
    root_text = _git_stdout(worktree_path, "rev-parse", "--show-toplevel")
    return Path(root_text).resolve()


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
