from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess

from ait.app import init_repo, land_attempt, promote_attempt, rebase_attempt
from ait.db import (
    connect_db,
    get_attempt,
    list_attempt_commits,
    list_attempts,
)
from ait.decision_codes import ApplyCode
from ait.decision_report import DecisionReport, daily_step, decision_report
from ait.idresolver import resolve_attempt_id
from ait.local_artifacts import scan_local_artifacts
from ait.policy import apply_cleanup_after_apply, apply_dirty_strategy
from ait.verifier import verify_attempt_with_connection
from ait.workspace import (
    WorkspaceError,
    current_branch_name,
    normalize_target_branch_ref,
    ref_head_oid,
    remove_attempt_workspace,
)
from ait.workspace_lease import (
    lease_payload,
    update_workspace_lease,
    workspace_lease_path,
)


@dataclass(frozen=True, slots=True)
class CheckoutSnapshot:
    branch: str | None
    head_oid: str
    dirty_tracked_files: tuple[str, ...]
    untracked_files: tuple[str, ...]

    @property
    def dirty(self) -> bool:
        return bool(self.dirty_tracked_files or self.untracked_files)


@dataclass(frozen=True, slots=True)
class LandingPlan:
    kind: str
    target_ref: str
    target_is_current_branch: bool
    root_dirty: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ApplyResult:
    attempt_id: str
    status: str
    landing_plan: LandingPlan
    branch: str | None
    promotion_ref: str | None
    commit_oid: str | None
    changed_files: tuple[str, ...]
    worktree_cleaned: bool
    cleanup_reason: str | None
    message: str
    reason: str | None = None
    workspace_ref: str | None = None
    lease: dict[str, object] | None = None
    decision_report: DecisionReport | None = None
    patch_artifact_ref: str | None = None
    result_artifact_ref: str | None = None
    debug: dict[str, object] = field(default_factory=dict)


class ApplyError(RuntimeError):
    """Raised when AIT cannot evaluate an apply request safely."""


def apply_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
    target_ref: str | None = None,
    mode: str = "auto",
) -> ApplyResult:
    if mode not in {"auto", "current", "branch", "none"}:
        raise ApplyError(f"unsupported apply mode: {mode}")
    init_result = init_repo(repo_root)
    root = init_result.repo_root
    attempt_id, attempt, changed_files = _load_attempt_for_apply(root, attempt_selector)
    workspace_ref = attempt.workspace_ref
    workspace = Path(workspace_ref)

    if attempt.verified_status == "promoted":
        plan = LandingPlan(
            kind="already_applied",
            target_ref=attempt.result_promotion_ref or "",
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="attempt result is already recorded as applied",
        )
        cleaned, cleanup_reason = _cleanup_applied_workspace(
            workspace_ref,
            durable_result=True,
            cleanup_after_apply=apply_cleanup_after_apply(root),
        )
        return _result(
            attempt_id=attempt_id,
            status="already_applied",
            plan=plan,
            branch=_branch_name(attempt.result_promotion_ref),
            promotion_ref=attempt.result_promotion_ref,
            commit_oid=None,
            changed_files=changed_files,
            worktree_cleaned=cleaned,
            cleanup_reason=cleanup_reason,
            message="AIT already applied this result.",
            workspace_ref=workspace_ref,
        )

    if mode == "none":
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref="",
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="apply mode is none",
        )
        update_workspace_lease(workspace_ref, state="succeeded", cleanup_policy="hold")
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery.",
            "apply mode is none",
            reason_code=ApplyCode.MODE_NONE,
        )

    if not workspace.exists():
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref="",
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="result workspace is missing",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT cannot apply this result because its recoverable state is missing.",
            "missing workspace",
            reason_code=ApplyCode.MISSING_RECOVERY_STATE,
        )

    if attempt.verified_status != "succeeded":
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref="",
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason=f"attempt is {attempt.verified_status}",
        )
        lease_state = "failed" if attempt.verified_status == "failed" else "active"
        update_workspace_lease(
            workspace_ref,
            state=lease_state,
            cleanup_policy="hold",
            preserve_reason=f"attempt is {attempt.verified_status}",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery because the attempt is not marked successful.",
            f"attempt is {attempt.verified_status}",
            status="held",
            reason_code=ApplyCode.ATTEMPT_NOT_SUCCESSFUL,
        )

    if not changed_files:
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref="",
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="attempt has no committed file changes",
        )
        update_workspace_lease(workspace_ref, state="succeeded", cleanup_policy="hold")
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT found no committed result to apply.",
            "no committed changes",
            reason_code=ApplyCode.EMPTY_RESULT,
        )

    snapshot = checkout_snapshot(root)
    ref_name = _target_ref_for_apply(root, attempt.base_ref_name, target_ref, mode)
    target_is_current = _target_is_current(snapshot, ref_name)
    if mode == "branch" and target_is_current:
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref=ref_name,
            target_is_current_branch=True,
            root_dirty=snapshot.dirty,
            reason="branch mode would update the currently checked-out branch",
        )
        update_workspace_lease(workspace_ref, state="succeeded", cleanup_policy="hold")
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT held the result because branch mode cannot move your current checkout.",
            "target branch is currently checked out",
            reason_code=ApplyCode.TARGET_CURRENT_BRANCH,
        )

    if not target_is_current:
        return _apply_to_non_current_branch(
            root,
            attempt_id=attempt_id,
            target_ref=ref_name,
            workspace_ref=workspace_ref,
            base_ref_oid=attempt.base_ref_oid,
            changed_files=changed_files,
            root_dirty=snapshot.dirty,
        )

    if not snapshot.dirty:
        return _apply_to_clean_current_branch(
            root,
            attempt_id=attempt_id,
            target_ref=ref_name,
            workspace_ref=workspace_ref,
            base_ref_oid=attempt.base_ref_oid,
            changed_files=changed_files,
        )

    return _apply_patch_to_dirty_current_branch(
        root,
        attempt_id=attempt_id,
        target_ref=ref_name,
        workspace_ref=workspace_ref,
        base_ref_oid=attempt.base_ref_oid,
        snapshot=snapshot,
        changed_files=changed_files,
    )


def checkout_snapshot(repo_root: str | Path) -> CheckoutSnapshot:
    root = Path(repo_root).resolve()
    return CheckoutSnapshot(
        branch=_git_stdout(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True) or None,
        head_oid=_git_stdout(root, "rev-parse", "--verify", "HEAD"),
        dirty_tracked_files=tuple(sorted(_dirty_tracked_files(root))),
        untracked_files=tuple(sorted(_untracked_files(root))),
    )


def _load_attempt_for_apply(root: Path, selector: str):
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        attempt_id = _resolve_attempt_selector(conn, selector)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ApplyError(f"Unknown attempt: {attempt_id}")
        if Path(attempt.workspace_ref).exists():
            verify_attempt_with_connection(conn, root, attempt_id)
            attempt = get_attempt(conn, attempt_id)
            if attempt is None:
                raise ApplyError(f"Unknown attempt after verification: {attempt_id}")
        commits = list_attempt_commits(conn, attempt_id)
    finally:
        conn.close()
    changed_files = tuple(sorted({path for commit in commits for path in commit.touched_files}))
    return attempt_id, attempt, changed_files


def _resolve_attempt_selector(conn, selector: str) -> str:
    if selector == "latest":
        attempts = list_attempts(conn)
        if not attempts:
            raise ApplyError("no attempts found")
        return attempts[-1].id
    return resolve_attempt_id(conn, selector)


def _target_ref_for_apply(
    repo_root: Path,
    base_ref_name: str | None,
    explicit_target_ref: str | None,
    mode: str,
) -> str:
    if mode == "current":
        return normalize_target_branch_ref(current_branch_name(repo_root))
    target = explicit_target_ref or base_ref_name or current_branch_name(repo_root)
    return normalize_target_branch_ref(target)


def _target_is_current(snapshot: CheckoutSnapshot, ref_name: str) -> bool:
    if snapshot.branch is None:
        return False
    return normalize_target_branch_ref(snapshot.branch) == ref_name


def _apply_to_non_current_branch(
    root: Path,
    *,
    attempt_id: str,
    target_ref: str,
    workspace_ref: str,
    base_ref_oid: str,
    changed_files: tuple[str, ...],
    root_dirty: bool,
) -> ApplyResult:
    plan = LandingPlan(
        kind="update_non_checked_out_branch",
        target_ref=target_ref,
        target_is_current_branch=False,
        root_dirty=root_dirty,
        reason="target branch is not currently checked out",
    )
    rebased = _rebase_if_target_advanced(
        root,
        attempt_id=attempt_id,
        target_ref=target_ref,
        workspace_ref=workspace_ref,
        base_ref_oid=base_ref_oid,
    )
    if isinstance(rebased, ApplyResult):
        return rebased
    try:
        promoted = promote_attempt(root, attempt_id=attempt_id, target_ref=target_ref)
    except (ValueError, WorkspaceError) as exc:
        update_workspace_lease(workspace_ref, state="conflict", cleanup_policy="hold", preserve_reason=str(exc))
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT could not update the target branch safely.",
            _human_apply_error(str(exc)),
            reason_code=ApplyCode.TARGET_BRANCH_UPDATE_FAILED,
        )
    cleaned, cleanup_reason = _cleanup_applied_workspace(
        workspace_ref,
        durable_result=True,
        cleanup_after_apply=apply_cleanup_after_apply(root),
    )
    commit_oid = promoted.commits[-1]["commit_oid"] if promoted.commits else None
    return _result(
        attempt_id=attempt_id,
        status="applied",
        plan=plan,
        branch=target_ref.removeprefix("refs/heads/"),
        promotion_ref=target_ref,
        commit_oid=commit_oid,
        changed_files=changed_files,
        worktree_cleaned=cleaned,
        cleanup_reason=cleanup_reason,
        message="AIT applied the result to the target branch.",
        workspace_ref=workspace_ref,
    )


def _apply_to_clean_current_branch(
    root: Path,
    *,
    attempt_id: str,
    target_ref: str,
    workspace_ref: str,
    base_ref_oid: str,
    changed_files: tuple[str, ...],
) -> ApplyResult:
    plan = LandingPlan(
        kind="fast_forward_current_branch",
        target_ref=target_ref,
        target_is_current_branch=True,
        root_dirty=False,
        reason="current checkout is clean",
    )
    rebased = _rebase_if_target_advanced(
        root,
        attempt_id=attempt_id,
        target_ref=target_ref,
        workspace_ref=workspace_ref,
        base_ref_oid=base_ref_oid,
    )
    if isinstance(rebased, ApplyResult):
        return rebased
    try:
        landed = land_attempt(root, attempt_id=attempt_id, target_ref=target_ref)
    except (ValueError, WorkspaceError) as exc:
        update_workspace_lease(workspace_ref, state="conflict", cleanup_policy="hold", preserve_reason=str(exc))
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT could not apply directly to your checkout.",
            _human_apply_error(str(exc)),
            reason_code=ApplyCode.CURRENT_BRANCH_UPDATE_FAILED,
        )
    return _result(
        attempt_id=attempt_id,
        status="applied",
        plan=plan,
        branch=landed.branch,
        promotion_ref=landed.promotion_ref,
        commit_oid=landed.commit_oid,
        changed_files=changed_files,
        worktree_cleaned=landed.worktree_cleaned,
        cleanup_reason=None if landed.worktree_cleaned else "local artifacts require review before cleanup",
        message="AIT applied the result to your checkout.",
        workspace_ref=workspace_ref,
    )


def _rebase_if_target_advanced(
    root: Path,
    *,
    attempt_id: str,
    target_ref: str,
    workspace_ref: str,
    base_ref_oid: str,
) -> ApplyResult | None:
    target_oid = ref_head_oid(root, target_ref)
    if not target_oid or target_oid == base_ref_oid:
        return None
    if _worktree_has_uncommitted_tracked_changes(Path(workspace_ref)):
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref=target_ref,
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="target branch moved and result workspace has uncommitted changes",
        )
        update_workspace_lease(
            workspace_ref,
            state="succeeded",
            cleanup_policy="hold",
            preserve_reason="target branch moved and result workspace has uncommitted changes",
        )
        return _held(
            attempt_id,
            plan,
            _attempt_touched_files(workspace_ref, base_ref_oid),
            workspace_ref,
            "AIT held the result because the target branch moved.",
            "result workspace has uncommitted changes",
            reason_code=ApplyCode.TARGET_MOVED_UNCOMMITTED_RESULT,
        )
    try:
        rebase_attempt(root, attempt_id=attempt_id, onto_ref=target_ref)
    except (ValueError, WorkspaceError) as exc:
        update_workspace_lease(workspace_ref, state="conflict", cleanup_policy="hold", preserve_reason=str(exc))
        plan = LandingPlan(
            kind="hold_for_review",
            target_ref=target_ref,
            target_is_current_branch=False,
            root_dirty=checkout_snapshot(root).dirty,
            reason="automatic rebase did not apply cleanly",
        )
        return _held(
            attempt_id,
            plan,
            _attempt_touched_files(workspace_ref, base_ref_oid),
            workspace_ref,
            "AIT could not integrate the result with the updated target branch.",
            _human_apply_error(str(exc)),
            reason_code=ApplyCode.TARGET_MOVED,
        )
    return None


def _apply_patch_to_dirty_current_branch(
    root: Path,
    *,
    attempt_id: str,
    target_ref: str,
    workspace_ref: str,
    base_ref_oid: str,
    snapshot: CheckoutSnapshot,
    changed_files: tuple[str, ...],
) -> ApplyResult:
    plan = LandingPlan(
        kind="patch_apply_clean_overlap",
        target_ref=target_ref,
        target_is_current_branch=True,
        root_dirty=True,
        reason="current checkout has local edits",
    )
    if apply_dirty_strategy(root) == "hold":
        update_workspace_lease(
            workspace_ref,
            state="succeeded",
            cleanup_policy="hold",
            preserve_reason="dirty checkout policy is hold",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery because this repo is configured to hold on local edits.",
            "dirty checkout policy is hold",
            reason_code=ApplyCode.DIRTY_POLICY_HOLD,
        )
    touched = set(_attempt_touched_files(workspace_ref, base_ref_oid))
    unsafe = _unsafe_patch_statuses(workspace_ref, base_ref_oid)
    if unsafe:
        update_workspace_lease(
            workspace_ref,
            state="succeeded",
            cleanup_policy="hold",
            preserve_reason="result includes changes that need review before dirty checkout apply",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery because this patch needs review before applying to your edited checkout.",
            "result includes deletes, renames, type changes, or unresolved paths",
            debug={"unsafe_statuses": tuple(unsafe)},
            reason_code=ApplyCode.UNSAFE_PATCH_STATUS,
        )
    overlap = tuple(sorted(set(snapshot.dirty_tracked_files) & touched))
    integration_artifact = _integration_artifact_payload(root, attempt_id)
    if overlap and not integration_artifact:
        update_workspace_lease(
            workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason="local edits overlap with result",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT could not apply directly because your local edits overlap with the result.",
            "overlapping local edits: " + ", ".join(overlap),
            status="conflict",
            debug={"overlap": overlap},
            reason_code=ApplyCode.DIRTY_OVERLAP,
        )
    untracked_conflicts = tuple(sorted(set(snapshot.untracked_files) & touched))
    if untracked_conflicts:
        update_workspace_lease(
            workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason="untracked files would be overwritten",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT held the result because applying it would overwrite untracked files.",
            "untracked files would be overwritten: " + ", ".join(untracked_conflicts),
            status="conflict",
            debug={"untracked_conflicts": untracked_conflicts},
            reason_code=ApplyCode.UNTRACKED_OVERWRITE,
        )
    head_oid = _git_stdout(Path(workspace_ref), "rev-parse", "--verify", "HEAD")
    patch = _git(Path(workspace_ref), "diff", "--binary", f"{base_ref_oid}..{head_oid}").stdout
    if not patch.strip():
        update_workspace_lease(workspace_ref, state="succeeded", cleanup_policy="hold")
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT found no patch to apply.",
            "empty patch",
            reason_code=ApplyCode.EMPTY_RESULT,
        )
    check = _git(
        root,
        "apply",
        "--3way",
        "--check",
        "--whitespace=nowarn",
        input_text=patch,
        allow_failure=True,
    )
    if check.returncode != 0:
        update_workspace_lease(
            workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason=check.stderr.strip() or "patch check failed",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery because the patch did not apply cleanly.",
            _human_apply_error(check.stderr.strip() or "patch check failed"),
            status="conflict",
            reason_code=ApplyCode.PATCH_CHECK_FAILED,
        )
    applied = _git(
        root,
        "apply",
        "--3way",
        "--whitespace=nowarn",
        input_text=patch,
        allow_failure=True,
    )
    if applied.returncode != 0:
        update_workspace_lease(
            workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason=applied.stderr.strip() or "patch apply failed",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT kept the result for recovery because applying it created a conflict.",
            _human_apply_error(applied.stderr.strip() or "patch apply failed"),
            status="conflict",
            reason_code=ApplyCode.CONFLICT,
        )
    _unstage_paths(root, tuple(sorted(touched)))
    conflict_markers = _paths_with_conflict_markers(root, tuple(sorted(touched)))
    if conflict_markers:
        update_workspace_lease(
            workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason="applied files contain conflict markers",
        )
        return _held(
            attempt_id,
            plan,
            changed_files,
            workspace_ref,
            "AIT stopped because applied files still contain conflict markers.",
            "conflict markers in: " + ", ".join(conflict_markers),
            status="conflict",
            debug={"conflict_markers": conflict_markers},
            reason_code=ApplyCode.CONFLICT_MARKERS,
        )
    patch_ref, result_ref = _write_result_artifacts(
        root,
        attempt_id=attempt_id,
        workspace_ref=workspace_ref,
        target_ref=target_ref,
        base_ref_oid=base_ref_oid,
        commit_oid=head_oid,
        changed_files=changed_files,
        patch=patch,
        landing_kind=plan.kind,
    )
    update_workspace_lease(workspace_ref, state="applied", cleanup_policy="auto", clear_preserve_reason=True)
    cleaned, cleanup_reason = _cleanup_applied_workspace(
        workspace_ref,
        durable_result=True,
        cleanup_after_apply=apply_cleanup_after_apply(root),
    )
    return _result(
        attempt_id=attempt_id,
        status="applied",
        plan=plan,
        branch=snapshot.branch,
        promotion_ref=None,
        commit_oid=head_oid,
        changed_files=changed_files,
        worktree_cleaned=cleaned,
        cleanup_reason=cleanup_reason,
        message="AIT applied the result without touching your existing edits.",
        reason=None,
        workspace_ref=workspace_ref,
        patch_artifact_ref=patch_ref,
        result_artifact_ref=result_ref,
        debug={
            "preserved_dirty_files": snapshot.dirty_tracked_files,
            "preserved_untracked_files": snapshot.untracked_files,
            "integration_artifact": integration_artifact or {},
        },
    )


def _cleanup_applied_workspace(
    workspace_ref: str,
    *,
    durable_result: bool,
    cleanup_after_apply: bool = True,
) -> tuple[bool, str | None]:
    workspace = Path(workspace_ref)
    if not workspace.exists():
        return False, "workspace already removed"
    if not cleanup_after_apply:
        update_workspace_lease(
            workspace_ref,
            state="applied",
            cleanup_policy="hold",
            preserve_reason="cleanup after apply is disabled by repo policy",
        )
        return False, "kept because cleanup after apply is disabled"
    if not durable_result:
        update_workspace_lease(
            workspace_ref,
            state="applied",
            cleanup_policy="hold",
            preserve_reason="applied result has no durable branch or ref",
        )
        return False, "kept because the result has no durable branch or ref"
    if _worktree_has_uncommitted_tracked_changes(workspace):
        update_workspace_lease(
            workspace_ref,
            state="applied",
            cleanup_policy="hold",
            preserve_reason="workspace has uncommitted tracked changes",
        )
        return False, "workspace has uncommitted tracked changes"
    artifacts = scan_local_artifacts(workspace)
    review_artifacts = tuple(
        artifact.path
        for artifact in artifacts
        if not _artifact_is_generated(artifact.path)
    )
    if review_artifacts:
        update_workspace_lease(
            workspace_ref,
            state="applied",
            cleanup_policy="hold",
            preserve_reason="workspace has local artifacts that require review",
        )
        return False, "workspace has local artifacts that require review"
    remove_attempt_workspace(workspace_ref)
    return True, None


def _dirty_tracked_files(root: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
    ):
        output = _git_stdout(root, *args, allow_failure=True)
        paths.update(line.strip() for line in output.splitlines() if line.strip())
    return paths


def _untracked_files(root: Path) -> set[str]:
    output = _git_stdout(root, "ls-files", "--others", "--exclude-standard", allow_failure=True)
    return {line.strip() for line in output.splitlines() if line.strip()}


def _attempt_touched_files(workspace_ref: str | Path, base_ref_oid: str) -> tuple[str, ...]:
    output = _git_stdout(Path(workspace_ref), "diff", "--name-only", f"{base_ref_oid}..HEAD", allow_failure=True)
    return tuple(sorted(line.strip() for line in output.splitlines() if line.strip()))


def _unsafe_patch_statuses(workspace_ref: str | Path, base_ref_oid: str) -> tuple[str, ...]:
    output = _git_stdout(Path(workspace_ref), "diff", "--name-status", f"{base_ref_oid}..HEAD", allow_failure=True)
    unsafe: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        status = line.split("\t", 1)[0]
        if not status or status[0] not in {"A", "M"}:
            unsafe.append(line)
    return tuple(unsafe)


def _worktree_has_uncommitted_tracked_changes(workspace: Path) -> bool:
    output = _git_stdout(workspace, "status", "--porcelain", "--untracked-files=no", allow_failure=True)
    return bool(output.strip())


def _artifact_is_generated(path: str) -> bool:
    return any(part in {".venv", "node_modules", "dist", "build", ".pytest_cache"} for part in path.split("/"))


def _write_result_artifacts(
    root: Path,
    *,
    attempt_id: str,
    workspace_ref: str,
    target_ref: str,
    base_ref_oid: str,
    commit_oid: str,
    changed_files: tuple[str, ...],
    patch: str,
    landing_kind: str,
) -> tuple[str, str]:
    results_dir = root / ".ait" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_attempt_filename(attempt_id)
    patch_path = results_dir / f"{filename}.patch"
    result_path = results_dir / f"{filename}.json"
    patch_path.write_text(patch, encoding="utf-8")
    result_payload = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "workspace_ref": workspace_ref,
        "target_ref": target_ref,
        "base_ref_oid": base_ref_oid,
        "commit_oid": commit_oid,
        "changed_files": list(changed_files),
        "landing_kind": landing_kind,
        "created_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "patch_ref": str(patch_path),
    }
    result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(patch_path), str(result_path)


def _safe_attempt_filename(attempt_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in attempt_id.rsplit(":", 1)[-1])


def _integration_artifact_payload(root: Path, attempt_id: str) -> dict[str, object] | None:
    path = root / ".ait" / "results" / f"{_safe_attempt_filename(attempt_id)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "integration":
        return None
    return payload


def _unstage_paths(root: Path, paths: tuple[str, ...]) -> None:
    if not paths:
        return
    _git(root, "reset", "-q", "--", *paths, allow_failure=True)


def _paths_with_conflict_markers(root: Path, paths: tuple[str, ...]) -> tuple[str, ...]:
    conflicted: list[str] = []
    for path_text in paths:
        path = root / path_text
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()[:1024 * 1024]
        except OSError:
            continue
        if b"\0" in data:
            continue
        if b"<<<<<<< " in data or b"=======\n" in data or b">>>>>>> " in data:
            conflicted.append(path_text)
    return tuple(conflicted)


def _branch_name(ref_name: str | None) -> str | None:
    if ref_name is None:
        return None
    return ref_name.removeprefix("refs/heads/")


def _human_apply_error(message: str) -> str:
    text = message.strip()
    if "uncommitted" in text or "Commit or stash" in text:
        return (
            "your local edits make a direct branch update unsafe; AIT kept the result "
            "recoverable instead of stashing or overwriting your work"
        )
    if "not possible" in text or "non-fast-forward" in text:
        return "the target branch moved and the result could not be integrated automatically"
    return text or "apply did not complete safely"


def _held(
    attempt_id: str,
    plan: LandingPlan,
    changed_files: tuple[str, ...],
    workspace_ref: str,
    message: str,
    reason: str,
    *,
    status: str = "held",
    debug: dict[str, object] | None = None,
    reason_code: str | None = None,
) -> ApplyResult:
    return _result(
        attempt_id=attempt_id,
        status=status,
        plan=plan,
        branch=_branch_name(plan.target_ref),
        promotion_ref=None,
        commit_oid=None,
        changed_files=changed_files,
        worktree_cleaned=False,
        cleanup_reason="kept for recovery",
        message=message,
        reason=reason,
        reason_code=reason_code,
        workspace_ref=workspace_ref,
        debug=debug or {},
    )


def _result(
    *,
    attempt_id: str,
    status: str,
    plan: LandingPlan,
    branch: str | None,
    promotion_ref: str | None,
    commit_oid: str | None,
    changed_files: tuple[str, ...],
    worktree_cleaned: bool,
    cleanup_reason: str | None,
    message: str,
    workspace_ref: str,
    reason: str | None = None,
    reason_code: str | None = None,
    patch_artifact_ref: str | None = None,
    result_artifact_ref: str | None = None,
    debug: dict[str, object] | None = None,
) -> ApplyResult:
    debug_payload = {
        "lease_path": str(workspace_lease_path(workspace_ref)),
        **(debug or {}),
    }
    report = decision_report(
        subject="apply",
        subject_id=attempt_id,
        decision=status,
        safety_level=_safety_level_for_apply(status),
        reason_code=reason_code or _reason_code_for_apply(status, plan, reason, cleanup_reason),
        reason_message=reason or plan.reason,
        paths=_reason_paths_for_apply(debug_payload, changed_files),
        debug=debug_payload,
        next_steps=() if status in {"applied", "already_applied"} else (daily_step(f"ait recover {attempt_id}", "review the recoverable result"),),
        metadata={
            "landing_plan": asdict(plan),
            "changed_files_count": len(changed_files),
            "worktree_cleaned": worktree_cleaned,
            "cleanup_reason": cleanup_reason,
        },
    )
    return ApplyResult(
        attempt_id=attempt_id,
        status=status,
        landing_plan=plan,
        branch=branch,
        promotion_ref=promotion_ref,
        commit_oid=commit_oid,
        changed_files=changed_files,
        worktree_cleaned=worktree_cleaned,
        cleanup_reason=cleanup_reason,
        message=message,
        reason=reason,
        workspace_ref=workspace_ref,
        lease=lease_payload(workspace_ref),
        decision_report=report,
        patch_artifact_ref=patch_artifact_ref,
        result_artifact_ref=result_artifact_ref,
        debug=debug_payload,
    )


def apply_result_payload(result: ApplyResult, *, debug: bool = False) -> dict[str, object]:
    payload = asdict(result)
    if not debug:
        payload.pop("debug", None)
    return payload


def _safety_level_for_apply(status: str) -> str:
    if status in {"applied", "already_applied"}:
        return "automated"
    if status == "conflict":
        return "held-conflict"
    return "held"


def _reason_code_for_apply(
    status: str,
    plan: LandingPlan,
    reason: str | None,
    cleanup_reason: str | None,
) -> str:
    text = " ".join(item for item in (status, plan.kind, plan.reason, reason or "", cleanup_reason or "") if item)
    lower = text.lower()
    if status == "already_applied":
        return ApplyCode.ALREADY_APPLIED
    if status == "applied" and plan.kind == "patch_apply_clean_overlap":
        return ApplyCode.DIRTY_PATCH_APPLIED
    if status == "applied":
        return ApplyCode.APPLIED
    if "apply mode is none" in lower:
        return ApplyCode.MODE_NONE
    if "missing workspace" in lower:
        return ApplyCode.MISSING_RECOVERY_STATE
    if "no committed" in lower or "empty patch" in lower:
        return ApplyCode.EMPTY_RESULT
    if "currently checked out" in lower:
        return ApplyCode.TARGET_CURRENT_BRANCH
    if "untracked" in lower:
        return ApplyCode.UNTRACKED_OVERWRITE
    if "overlap" in lower:
        return ApplyCode.DIRTY_OVERLAP
    if "moved" in lower or "rebase" in lower:
        return ApplyCode.TARGET_MOVED
    if "conflict" in lower:
        return ApplyCode.CONFLICT
    return ApplyCode.HELD


def _reason_paths_for_apply(debug: dict[str, object], changed_files: tuple[str, ...]) -> tuple[str, ...]:
    for key in ("overlap", "untracked_conflicts", "conflict_markers"):
        value = debug.get(key)
        if isinstance(value, tuple | list):
            return tuple(sorted(str(item) for item in value if str(item)))
    return tuple(changed_files)


def _git_stdout(
    cwd: Path,
    *args: str,
    allow_failure: bool = False,
) -> str:
    completed = _git(cwd, *args, allow_failure=allow_failure)
    if completed.returncode != 0 and allow_failure:
        return ""
    return completed.stdout.strip()


def _git(
    cwd: Path,
    *args: str,
    input_text: str | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not allow_failure:
        raise ApplyError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed
