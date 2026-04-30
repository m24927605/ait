from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
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


@dataclass(slots=True, frozen=True)
class RebaseWorkspaceResult:
    onto_ref: str
    base_ref_oid: str
    head_oid: str


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

    try:
        _git_run(
            root,
            "worktree",
            "add",
            "--detach",
            str(location.worktree_path),
            base_ref_oid,
        )
    except WorkspaceError:
        _cleanup_failed_worktree_add(root, location.worktree_path)
        raise

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


def _cleanup_failed_worktree_add(repo_root: Path, worktree_path: Path) -> None:
    _git_run(repo_root, "worktree", "prune", allow_failure=True)
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


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
    if not commit_oids:
        return False
    root = Path(repo_root).resolve()
    ref_oid = ref_head_oid(root, ref_name)
    if not ref_oid:
        return False
    for commit_oid in commit_oids:
        merge_base = _git_stdout(root, "merge-base", commit_oid, ref_name, allow_failure=True)
        if merge_base != commit_oid:
            return False
    return True


def ref_head_oid(repo_root: str | Path, ref_name: str) -> str | None:
    root = Path(repo_root).resolve()
    return _git_stdout(root, "rev-parse", "--verify", ref_name, allow_failure=True) or None


def ref_matches_commit_patches(
    repo_root: str | Path,
    ref_name: str,
    *,
    base_ref_oid: str,
    commit_oids: tuple[str, ...],
) -> bool:
    if not commit_oids:
        return False
    root = Path(repo_root).resolve()
    ref_oid = ref_head_oid(root, ref_name)
    if not ref_oid:
        return False
    attempt_patch_ids = {
        patch_id
        for commit_oid in commit_oids
        if (patch_id := _commit_patch_id(root, commit_oid))
    }
    if not attempt_patch_ids:
        return False
    ref_commits = _git_stdout(
        root,
        "rev-list",
        "--reverse",
        f"{base_ref_oid}..{ref_name}",
        allow_failure=True,
    )
    ref_patch_ids = {
        patch_id
        for commit_oid in ref_commits.splitlines()
        if (patch_id := _commit_patch_id(root, commit_oid.strip()))
    }
    return attempt_patch_ids.issubset(ref_patch_ids)


def ref_matches_cumulative_patch(
    repo_root: str | Path,
    ref_name: str,
    *,
    base_ref_oid: str,
    attempt_head_oid: str,
) -> bool:
    root = Path(repo_root).resolve()
    ref_oid = ref_head_oid(root, ref_name)
    if not ref_oid:
        return False
    attempt_patch_id = _diff_patch_id(root, base_ref_oid, attempt_head_oid)
    ref_patch_id = _diff_patch_id(root, base_ref_oid, ref_name)
    return bool(attempt_patch_id and ref_patch_id and attempt_patch_id == ref_patch_id)


def _commit_patch_id(repo_root: Path, commit_oid: str) -> str | None:
    if not commit_oid:
        return None
    show = _git_run(repo_root, "show", "--format=", commit_oid, allow_failure=True)
    if show.returncode != 0 or not show.stdout.strip():
        return None
    patch_id = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=repo_root,
        input=show.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    if patch_id.returncode != 0 or not patch_id.stdout.strip():
        return None
    return patch_id.stdout.split()[0]


def _diff_patch_id(repo_root: Path, base_oid: str, target_ref: str) -> str | None:
    if not base_oid or not target_ref:
        return None
    diff = _git_run(repo_root, "diff", f"{base_oid}..{target_ref}", allow_failure=True)
    if diff.returncode != 0 or not diff.stdout.strip():
        return None
    patch_id = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=repo_root,
        input=diff.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    if patch_id.returncode != 0 or not patch_id.stdout.strip():
        return None
    return patch_id.stdout.split()[0]


def update_ref_to_workspace_head(repo_root: str | Path, ref_name: str, workspace_ref: str | Path) -> str:
    root = Path(repo_root).resolve()
    worktree_path = Path(workspace_ref).resolve()
    head_oid = _git_stdout(worktree_path, "rev-parse", "--verify", "HEAD")

    # When the target ref is the currently-checked-out branch of the main
    # repository, a bare `git update-ref` would move the branch pointer
    # forward without touching the working tree or index, leaving the user
    # with an inverted "changes to be committed" view. Detect that case and
    # use `git merge --ff-only` so index + working tree follow the ref.
    head_branch = _git_stdout(root, "symbolic-ref", "--quiet", "HEAD", allow_failure=True)
    if head_branch and head_branch == ref_name:
        if _has_uncommitted_changes(root):
            raise WorkspaceError(
                f"refusing to promote to currently-checked-out branch {ref_name}: "
                "main working tree has uncommitted tracked changes. "
                "Commit or stash those changes first, or promote to a branch "
                "that is not currently checked out."
            )
        completed = _git_run(
            root,
            "merge",
            "--ff-only",
            head_oid,
            allow_failure=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "fast-forward not possible"
            raise WorkspaceError(
                f"refusing to promote to currently-checked-out branch {ref_name}: "
                f"{stderr}. Rebase the attempt worktree onto the current branch "
                "head first, or promote to a branch that is not currently "
                "checked out."
            )
        return head_oid

    _git_run(root, "update-ref", ref_name, head_oid)
    return head_oid


def rebase_attempt_workspace(
    repo_root: str | Path,
    workspace_ref: str | Path,
    *,
    old_base_ref_oid: str,
    onto_ref: str,
) -> RebaseWorkspaceResult:
    root = Path(repo_root).resolve()
    worktree_path = Path(workspace_ref).resolve()
    ref_name = onto_ref if onto_ref.startswith("refs/") else f"refs/heads/{onto_ref}"
    base_ref_oid = _git_stdout(root, "rev-parse", "--verify", ref_name)

    if _has_uncommitted_changes(worktree_path):
        raise WorkspaceError(
            "refusing to rebase attempt worktree: it has uncommitted tracked "
            "changes. Commit or stash those changes inside the attempt "
            "worktree first."
        )

    completed = _git_run(
        worktree_path,
        "rebase",
        "--onto",
        base_ref_oid,
        old_base_ref_oid,
        allow_failure=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "rebase failed"
        raise WorkspaceError(
            f"refusing to rebase attempt worktree onto {ref_name}: {stderr}. "
            "Resolve the rebase in the attempt worktree, or run git rebase "
            "--abort there before retrying."
        )
    head_oid = _git_stdout(worktree_path, "rev-parse", "--verify", "HEAD")
    return RebaseWorkspaceResult(
        onto_ref=ref_name,
        base_ref_oid=base_ref_oid,
        head_oid=head_oid,
    )


def _has_uncommitted_changes(repo_root: Path) -> bool:
    completed = _git_run(
        repo_root,
        "status",
        "--porcelain",
        "--untracked-files=no",
        allow_failure=True,
    )
    return bool(completed.stdout.strip())


def create_attempt_commit(
    workspace_ref: str | Path,
    *,
    message: str,
    intent_id: str,
    attempt_id: str,
) -> str:
    worktree_path = Path(workspace_ref).resolve()
    trailer_message = (
        f"{message.rstrip()}\n\n"
        f"Intent-Id: {intent_id}\n"
        f"Attempt-Id: {attempt_id}\n"
    )
    _git_run(worktree_path, "commit", "-m", trailer_message)
    return _git_stdout(worktree_path, "rev-parse", "--verify", "HEAD")


def commit_message(workspace_ref: str | Path, commit_oid: str) -> str:
    worktree_path = Path(workspace_ref).resolve()
    return _git_stdout(worktree_path, "log", "-1", "--format=%B", commit_oid)


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
