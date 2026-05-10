from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess

from ait.db import (
    connect_db,
    get_attempt,
    get_attempt_by_workspace_ref,
    list_attempt_commits,
    list_attempts,
    run_migrations,
)
from ait.repo import resolve_repo_root
from ait.workspace_lease import lease_payload


AGENT_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GitWorktreeSnapshot:
    path: str
    is_primary: bool
    is_ait_workspace: bool
    current_branch: str | None
    head_oid: str | None
    dirty_tracked_files: tuple[str, ...]
    untracked_files: tuple[str, ...]
    remote_tracking_branch: str | None

    @property
    def dirty(self) -> bool:
        return bool(self.dirty_tracked_files or self.untracked_files)


@dataclass(frozen=True, slots=True)
class AttemptLineage:
    attempt_id: str | None
    base_ref_oid: str | None
    base_ref_name: str | None
    reported_status: str | None
    verified_status: str | None
    result_promotion_ref: str | None
    recorded_commit_oids: tuple[str, ...]
    recorded_changed_files: tuple[str, ...]
    actual_commit_oids: tuple[str, ...]
    actual_changed_files: tuple[str, ...]
    result_metadata_exists: bool
    manual_commits_can_be_synthetic: bool


@dataclass(frozen=True, slots=True)
class AgentState:
    schema_version: int
    current_state: str
    repo_root: str | None
    cwd: str
    worktree: GitWorktreeSnapshot | None
    primary_worktree: GitWorktreeSnapshot | None
    target_branch: str | None
    target_ref: str | None
    base_branch: str | None
    attempt: AttemptLineage
    commits_ahead_of_base: tuple[str, ...]
    ahead_by: int
    blocking_reasons: tuple[str, ...]
    recovery_commands: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["detected_context"] = detected_context_payload(self)
        return payload


def inspect_agent_state(cwd: str | Path, *, target_branch: str | None = None) -> AgentState:
    cwd_path = Path(cwd).resolve()
    try:
        repo_root = resolve_repo_root(cwd_path)
        worktree_path = _git_stdout(cwd_path, "rev-parse", "--show-toplevel")
    except Exception as exc:
        return AgentState(
            schema_version=AGENT_STATE_SCHEMA_VERSION,
            current_state="not_git_repository",
            repo_root=None,
            cwd=str(cwd_path),
            worktree=None,
            primary_worktree=None,
            target_branch=target_branch,
            target_ref=_branch_ref(target_branch) if target_branch else None,
            base_branch=None,
            attempt=_empty_attempt_lineage(),
            commits_ahead_of_base=(),
            ahead_by=0,
            blocking_reasons=(str(exc),),
            recovery_commands=("git status",),
        )

    current_worktree = Path(worktree_path).resolve()
    is_primary = current_worktree == repo_root
    is_workspace = _is_ait_workspace(repo_root, current_worktree)
    worktree = _worktree_snapshot(current_worktree, repo_root=repo_root)
    primary = _worktree_snapshot(repo_root, repo_root=repo_root)
    attempt = _attempt_lineage(repo_root, current_worktree)
    resolved_target = (
        target_branch
        or attempt.base_ref_name
        or _default_branch(repo_root)
        or primary.current_branch
        or worktree.current_branch
    )
    target_ref = _branch_ref(resolved_target) if resolved_target else None
    commits_ahead = attempt.actual_commit_oids
    base_branch = attempt.base_ref_name or resolved_target
    blocking_reasons = _blocking_reasons(worktree, primary, is_primary=is_primary)
    recovery_commands = _recovery_commands(
        attempt=attempt,
        target_branch=resolved_target,
        dirty=bool(blocking_reasons),
    )
    current_state = _classify_state(
        worktree=worktree,
        is_workspace=is_workspace,
        attempt=attempt,
        target_branch=resolved_target,
        blocking_reasons=blocking_reasons,
    )
    return AgentState(
        schema_version=AGENT_STATE_SCHEMA_VERSION,
        current_state=current_state,
        repo_root=str(repo_root),
        cwd=str(cwd_path),
        worktree=worktree,
        primary_worktree=primary,
        target_branch=resolved_target,
        target_ref=target_ref,
        base_branch=base_branch,
        attempt=attempt,
        commits_ahead_of_base=commits_ahead,
        ahead_by=len(commits_ahead),
        blocking_reasons=blocking_reasons,
        recovery_commands=recovery_commands,
    )


def detected_context_payload(state: AgentState) -> dict[str, object]:
    worktree = state.worktree
    primary = state.primary_worktree
    attempt = state.attempt
    return {
        "repo_root": state.repo_root,
        "cwd": state.cwd,
        "is_primary_worktree": bool(worktree and worktree.is_primary),
        "is_ait_workspace": bool(worktree and worktree.is_ait_workspace),
        "workspace_ref": worktree.path if worktree and worktree.is_ait_workspace else None,
        "attempt_id": attempt.attempt_id,
        "current_branch": worktree.current_branch if worktree else None,
        "base_branch": state.base_branch,
        "target_branch": state.target_branch,
        "head_oid": worktree.head_oid if worktree else None,
        "base_ref_oid": attempt.base_ref_oid,
        "commits_ahead_of_base": list(state.commits_ahead_of_base),
        "ahead_by": state.ahead_by,
        "remote_tracking_branch": worktree.remote_tracking_branch if worktree else None,
        "result_metadata_exists": attempt.result_metadata_exists,
        "manual_commits_can_be_synthetic": attempt.manual_commits_can_be_synthetic,
        "dirty": worktree.dirty if worktree else False,
        "dirty_tracked_files": list(worktree.dirty_tracked_files) if worktree else [],
        "untracked_files": list(worktree.untracked_files) if worktree else [],
        "primary_dirty": primary.dirty if primary else False,
        "primary_dirty_tracked_files": list(primary.dirty_tracked_files) if primary else [],
        "primary_untracked_files": list(primary.untracked_files) if primary else [],
    }


def _attempt_lineage(repo_root: Path, worktree: Path) -> AttemptLineage:
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return _empty_attempt_lineage()
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        attempt = get_attempt_by_workspace_ref(conn, str(worktree))
        if attempt is None:
            lease = lease_payload(worktree)
            lease_attempt_id = str(lease.get("attempt_id")) if isinstance(lease, dict) and lease.get("attempt_id") else None
            if lease_attempt_id:
                attempt = get_attempt(conn, lease_attempt_id)
        if attempt is None:
            return _empty_attempt_lineage()
        recorded = tuple(list_attempt_commits(conn, attempt.id))
    finally:
        conn.close()

    actual_commit_oids = _commit_oids_since(worktree, attempt.base_ref_oid)
    actual_changed = _changed_files_since(worktree, attempt.base_ref_oid)
    recorded_commit_oids = tuple(commit.commit_oid for commit in recorded)
    recorded_changed = tuple(sorted({path for commit in recorded for path in commit.touched_files}))
    result_path = repo_root / ".ait" / "results" / f"{_safe_attempt_filename(attempt.id)}.json"
    result_metadata_exists = bool(recorded_commit_oids or attempt.result_promotion_ref or result_path.exists())
    return AttemptLineage(
        attempt_id=attempt.id,
        base_ref_oid=attempt.base_ref_oid,
        base_ref_name=attempt.base_ref_name,
        reported_status=attempt.reported_status,
        verified_status=attempt.verified_status,
        result_promotion_ref=attempt.result_promotion_ref,
        recorded_commit_oids=recorded_commit_oids,
        recorded_changed_files=recorded_changed,
        actual_commit_oids=actual_commit_oids,
        actual_changed_files=actual_changed,
        result_metadata_exists=result_metadata_exists,
        manual_commits_can_be_synthetic=bool(
            actual_commit_oids
            and not result_metadata_exists
            and attempt.verified_status not in {"promoted", "discarded"}
        ),
    )


def _worktree_snapshot(path: Path, *, repo_root: Path) -> GitWorktreeSnapshot:
    status = _porcelain_status(path)
    dirty_tracked: list[str] = []
    untracked: list[str] = []
    for code, rel_path in status:
        if code == "??":
            untracked.append(rel_path)
        else:
            dirty_tracked.append(rel_path)
    return GitWorktreeSnapshot(
        path=str(path),
        is_primary=path == repo_root,
        is_ait_workspace=_is_ait_workspace(repo_root, path),
        current_branch=_git_stdout(path, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True) or None,
        head_oid=_git_stdout(path, "rev-parse", "--verify", "HEAD", allow_failure=True) or None,
        dirty_tracked_files=tuple(sorted(set(dirty_tracked))),
        untracked_files=tuple(sorted(set(untracked))),
        remote_tracking_branch=_git_stdout(
            path,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
            allow_failure=True,
        )
        or None,
    )


def _empty_attempt_lineage() -> AttemptLineage:
    return AttemptLineage(
        attempt_id=None,
        base_ref_oid=None,
        base_ref_name=None,
        reported_status=None,
        verified_status=None,
        result_promotion_ref=None,
        recorded_commit_oids=(),
        recorded_changed_files=(),
        actual_commit_oids=(),
        actual_changed_files=(),
        result_metadata_exists=False,
        manual_commits_can_be_synthetic=False,
    )


def _blocking_reasons(
    worktree: GitWorktreeSnapshot,
    primary: GitWorktreeSnapshot,
    *,
    is_primary: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if worktree.dirty:
        reasons.append("current worktree has uncommitted or untracked changes")
    if not is_primary and primary.dirty:
        reasons.append("primary worktree has uncommitted or untracked changes")
    return tuple(reasons)


def _recovery_commands(
    *,
    attempt: AttemptLineage,
    target_branch: str | None,
    dirty: bool,
) -> tuple[str, ...]:
    commands: list[str] = ["ait whereami --json", "ait status --json"]
    if dirty:
        commands.append("git status --short")
    if attempt.manual_commits_can_be_synthetic:
        commands.append("ait reconcile --json")
    if target_branch:
        commands.append(f"ait merge --to {target_branch} --dry-run --json")
    return tuple(dict.fromkeys(commands))


def _classify_state(
    *,
    worktree: GitWorktreeSnapshot,
    is_workspace: bool,
    attempt: AttemptLineage,
    target_branch: str | None,
    blocking_reasons: tuple[str, ...],
) -> str:
    if blocking_reasons:
        return "dirty_worktree"
    if is_workspace and attempt.manual_commits_can_be_synthetic:
        return "manual_commit_without_recorded_result"
    if is_workspace and attempt.result_metadata_exists and attempt.actual_commit_oids:
        return "recorded_result_ready"
    if is_workspace and attempt.attempt_id:
        return "ait_workspace_idle"
    if worktree.current_branch and target_branch and worktree.current_branch != target_branch:
        target_oid = _git_stdout(Path(worktree.path), "rev-parse", "--verify", target_branch, allow_failure=True)
        head_oid = worktree.head_oid
        if target_oid and head_oid and target_oid != head_oid:
            ahead = _git_stdout(Path(worktree.path), "rev-list", "--count", f"{target_branch}..HEAD", allow_failure=True)
            if ahead and ahead.isdigit() and int(ahead) > 0:
                return "branch_ahead_of_target"
    return "idle"


def _commit_oids_since(worktree: Path, base_oid: str | None) -> tuple[str, ...]:
    if not base_oid:
        return ()
    output = _git_stdout(worktree, "rev-list", "--reverse", f"{base_oid}..HEAD", allow_failure=True)
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def _changed_files_since(worktree: Path, base_oid: str | None) -> tuple[str, ...]:
    if not base_oid:
        return ()
    output = _git_stdout(worktree, "diff", "--name-only", f"{base_oid}..HEAD", allow_failure=True)
    return tuple(sorted(line.strip() for line in output.splitlines() if line.strip()))


def _porcelain_status(worktree: Path) -> tuple[tuple[str, str], ...]:
    output = _git_stdout(worktree, "status", "--porcelain", allow_failure=True)
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        code = line[:2]
        rel_path = line[3:] if len(line) > 3 else ""
        if " -> " in rel_path:
            rel_path = rel_path.split(" -> ", 1)[1]
        rows.append((code, rel_path))
    return tuple(rows)


def _is_ait_workspace(repo_root: Path, worktree: Path) -> bool:
    try:
        worktree.relative_to(repo_root / ".ait" / "workspaces")
    except ValueError:
        return False
    return True


def _default_branch(repo_root: Path) -> str | None:
    configured = _git_stdout(repo_root, "config", "--get", "ait.defaultBranch", allow_failure=True)
    if configured:
        return configured
    remote_head = _git_stdout(
        repo_root,
        "symbolic-ref",
        "--quiet",
        "--short",
        "refs/remotes/origin/HEAD",
        allow_failure=True,
    )
    if remote_head.startswith("origin/"):
        return remote_head.removeprefix("origin/")
    for branch in ("main", "master"):
        if _git_stdout(repo_root, "rev-parse", "--verify", f"refs/heads/{branch}", allow_failure=True):
            return branch
    return None


def _branch_ref(branch: str | None) -> str | None:
    if not branch:
        return None
    return branch if branch.startswith("refs/") else f"refs/heads/{branch}"


def _safe_attempt_filename(attempt_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in attempt_id.rsplit(":", 1)[-1])


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if allow_failure:
            return ""
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()
