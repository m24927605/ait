from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from ait.app import create_attempt, create_commit_for_attempt, create_intent, init_repo
from ait.db import connect_db, get_attempt, list_attempt_commits, list_attempts
from ait.decision_codes import IntegrationCode
from ait.decision_report import DecisionReport, daily_step, decision_payload, decision_report
from ait.idresolver import resolve_attempt_id
from ait.policy import (
    integration_allow_binary_merge,
    integration_allow_delete_merge,
    integration_allow_untracked_replay,
    integration_auto_test_command,
    integration_auto_test_shell,
    integration_semantic_adapter,
)
from ait.workspace_lease import lease_payload, update_workspace_lease


@dataclass(frozen=True, slots=True)
class DirtyPath:
    path: str
    status: str
    mode: str | None
    blob_oid: str | None
    worktree_sha256: str | None
    binary: bool


@dataclass(frozen=True, slots=True)
class DirtySnapshot:
    branch: str | None
    head_oid: str
    tracked: tuple[DirtyPath, ...]
    untracked: tuple[DirtyPath, ...]
    index_dirty: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class IntegrationPlan:
    attempt_id: str
    base_attempt_id: str
    strategy: str
    classification: str
    root_modified: bool
    safe_to_auto_run: bool
    user_paths: tuple[str, ...]
    agent_paths: tuple[str, ...]
    overlap_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    reason_code: str
    reason: str


@dataclass(frozen=True, slots=True)
class IntegrationResult:
    attempt_id: str
    base_attempt_id: str
    status: str
    plan: IntegrationPlan
    changed_files: tuple[str, ...]
    commit_oid: str | None
    workspace_ref: str | None
    result_artifact_ref: str | None
    patch_artifact_ref: str | None
    decision_report: DecisionReport
    debug: dict[str, object] = field(default_factory=dict)


class IntegrationError(RuntimeError):
    """Raised when an integration attempt cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class _AgentPatch:
    patch: str
    source: str
    paths: tuple[str, ...]
    statuses: dict[str, str]
    binary_paths: tuple[str, ...]


def dirty_snapshot(repo_root: str | Path) -> DirtySnapshot:
    root = Path(repo_root).resolve()
    branch = _git_stdout(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True) or None
    head_oid = _git_stdout(root, "rev-parse", "--verify", "HEAD")
    porcelain = _git(root, "status", "--porcelain=v1", "-z", allow_failure=True).stdout
    status_by_path = _parse_porcelain_z(porcelain)
    untracked_paths = set(_git_stdout(root, "ls-files", "--others", "--exclude-standard", allow_failure=True).splitlines())
    tracked_paths = sorted(path for path in status_by_path if path not in untracked_paths)
    tracked = tuple(_dirty_path(root, path, status_by_path.get(path, "  ")) for path in tracked_paths)
    untracked = tuple(
        _dirty_path(root, path, "??", tracked=False)
        for path in sorted(path for path in untracked_paths if path)
    )
    index_dirty = any(path.status[:1].strip() for path in tracked)
    return DirtySnapshot(
        branch=branch,
        head_oid=head_oid,
        tracked=tracked,
        untracked=untracked,
        index_dirty=index_dirty,
        created_at=_utc_now(),
    )


def classify_paths(
    snapshot: DirtySnapshot,
    *,
    agent_paths: tuple[str, ...],
    agent_statuses: dict[str, str] | None = None,
    agent_binary_paths: tuple[str, ...] = (),
    allow_binary_merge: bool = False,
    allow_delete_merge: bool = False,
) -> IntegrationPlan:
    statuses = agent_statuses or {}
    user_paths = tuple(sorted(path.path for path in snapshot.tracked))
    user_path_set = set(user_paths)
    agent_path_set = set(agent_paths)
    overlap = tuple(sorted(user_path_set & agent_path_set))
    untracked_conflicts = tuple(sorted({path.path for path in snapshot.untracked} & agent_path_set))
    blocked: list[str] = []
    classification = "safe_non_overlap"
    reason_code = IntegrationCode.SAFE_NON_OVERLAP
    reason = "Local tracked edits do not overlap with the AIT result."
    safe_to_auto_run = True

    if not agent_paths:
        classification = "no_agent_patch"
        reason_code = IntegrationCode.NO_AGENT_PATCH
        reason = "AIT could not find a patch for the result."
        safe_to_auto_run = False
    elif untracked_conflicts:
        classification = "untracked_conflict"
        reason_code = IntegrationCode.UNTRACKED_CONFLICT
        reason = "The AIT result would conflict with untracked files in your checkout."
        blocked.extend(untracked_conflicts)
        safe_to_auto_run = False
    elif overlap:
        overlap_statuses = {path: statuses.get(path, "M") for path in overlap}
        user_by_path = {path.path: path for path in snapshot.tracked}
        if any(status.startswith("R") for status in overlap_statuses.values()):
            classification = "rename_overlap"
            reason_code = IntegrationCode.RENAME_OVERLAP
            reason = "Overlapping rename changes need manual review."
            blocked.extend(overlap)
            safe_to_auto_run = False
        elif any("D" in (status + user_by_path[path].status) for path, status in overlap_statuses.items()):
            classification = "delete_overlap"
            reason_code = IntegrationCode.DELETE_OVERLAP
            reason = "Overlapping delete/edit changes need manual review."
            blocked.extend(overlap)
            safe_to_auto_run = allow_delete_merge
        elif any(path in set(agent_binary_paths) or user_by_path[path].binary for path in overlap):
            classification = "binary_overlap"
            reason_code = IntegrationCode.BINARY_OVERLAP
            reason = "Overlapping binary changes need manual review."
            blocked.extend(overlap)
            safe_to_auto_run = allow_binary_merge
        elif any(_unsupported_status(status) or _unsupported_status(user_by_path[path].status) for path, status in overlap_statuses.items()):
            classification = "unsafe_status"
            reason_code = IntegrationCode.UNSAFE_STATUS
            reason = "One or more overlapping paths have unsupported Git status."
            blocked.extend(overlap)
            safe_to_auto_run = False
        else:
            classification = "text_overlap"
            reason_code = IntegrationCode.TEXT_OVERLAP
            reason = "AIT can create an integration attempt for overlapping tracked text edits."
            safe_to_auto_run = True
    elif any(_unsupported_status(status) for status in statuses.values()):
        classification = "unsafe_status"
        reason_code = IntegrationCode.UNSAFE_STATUS
        reason = "The AIT result contains unsupported Git status."
        blocked.extend(path for path, status in statuses.items() if _unsupported_status(status))
        safe_to_auto_run = False

    return IntegrationPlan(
        attempt_id="",
        base_attempt_id="",
        strategy=_strategy_for_classification(classification),
        classification=classification,
        root_modified=False,
        safe_to_auto_run=safe_to_auto_run,
        user_paths=user_paths,
        agent_paths=tuple(sorted(agent_paths)),
        overlap_paths=overlap,
        blocked_paths=tuple(sorted(set(blocked))),
        reason_code=reason_code,
        reason=reason,
    )


def create_integration_attempt(
    repo_root: str | Path,
    *,
    attempt_selector: str = "latest",
    auto_integrate: bool = False,
    test_command: str | None = None,
) -> IntegrationResult:
    init_result = init_repo(repo_root)
    root = init_result.repo_root
    base_attempt_id, base_attempt = _load_base_attempt(root, attempt_selector)
    snapshot = dirty_snapshot(root)
    agent_patch = _load_agent_patch(root, base_attempt_id, base_attempt.workspace_ref, base_attempt.base_ref_oid)
    plan = classify_paths(
        snapshot,
        agent_paths=agent_patch.paths,
        agent_statuses=agent_patch.statuses,
        agent_binary_paths=agent_patch.binary_paths,
        allow_binary_merge=integration_allow_binary_merge(root),
        allow_delete_merge=integration_allow_delete_merge(root),
    )
    if plan.classification == "no_agent_patch":
        return _result(
            root,
            attempt_id=base_attempt_id,
            base_attempt_id=base_attempt_id,
            status="held",
            plan=_with_plan_ids(plan, attempt_id=base_attempt_id, base_attempt_id=base_attempt_id),
            changed_files=(),
            workspace_ref=base_attempt.workspace_ref,
            reason_code=IntegrationCode.NO_AGENT_PATCH,
            message=plan.reason,
            debug={"patch_source": agent_patch.source},
        )
    if not plan.safe_to_auto_run:
        update_workspace_lease(
            base_attempt.workspace_ref,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason=plan.reason_code,
        )
        return _result(
            root,
            attempt_id=base_attempt_id,
            base_attempt_id=base_attempt_id,
            status="held",
            plan=_with_plan_ids(plan, attempt_id=base_attempt_id, base_attempt_id=base_attempt_id),
            changed_files=agent_patch.paths,
            workspace_ref=base_attempt.workspace_ref,
            reason_code=plan.reason_code,
            message=plan.reason,
            debug={"classification": plan.classification, "blocked_paths": plan.blocked_paths},
        )
    if snapshot.untracked and not integration_allow_untracked_replay(root):
        # Untracked files are not replayed, but they only block when they collide with agent paths.
        pass

    intent = create_intent(
        root,
        title=f"Integrate {base_attempt_id.rsplit(':', 1)[-1]}",
        description="AIT integration attempt for a recoverable result and local checkout edits.",
        kind="integration",
    )
    attempt = create_attempt(root, intent_id=intent.intent_id, agent_id="integration:ait")
    workspace = Path(attempt.workspace_ref)
    plan = _with_plan_ids(plan, attempt_id=attempt.attempt_id, base_attempt_id=base_attempt_id)
    update_workspace_lease(
        workspace,
        state="active",
        cleanup_policy="hold",
        preserve_reason="integration in progress",
    )
    replay = _replay_tracked_dirty(root, workspace, snapshot)
    if replay.returncode != 0:
        update_workspace_lease(
            workspace,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason=replay.stderr.strip() or "tracked dirty replay failed",
        )
        return _result(
            root,
            attempt_id=attempt.attempt_id,
            base_attempt_id=base_attempt_id,
            status="held",
            plan=plan,
            changed_files=agent_patch.paths,
            workspace_ref=attempt.workspace_ref,
            reason_code=IntegrationCode.REPLAY_USER_FAILED,
            message="AIT could not replay your tracked local edits into an integration attempt.",
            debug={"replay_user": replay.stderr.strip()},
        )

    merge = _run_merge_ladder(
        root,
        workspace,
        base_workspace=Path(base_attempt.workspace_ref),
        snapshot=snapshot,
        agent_patch=agent_patch,
        plan=plan,
    )
    if merge.returncode != 0:
        _write_conflict_bundle(root, attempt.attempt_id, base_workspace=Path(base_attempt.workspace_ref), snapshot=snapshot, paths=plan.overlap_paths)
        update_workspace_lease(
            workspace,
            state="conflict",
            cleanup_policy="hold",
            preserve_reason=merge.reason_code,
        )
        semantic = _maybe_semantic_merge(
            root,
            workspace,
            attempt_id=attempt.attempt_id,
            auto_integrate=auto_integrate,
            test_command=test_command,
        )
        if semantic.returncode != 0:
            return _result(
                root,
                attempt_id=attempt.attempt_id,
                base_attempt_id=base_attempt_id,
                status="conflict",
                plan=plan,
                changed_files=agent_patch.paths,
                workspace_ref=attempt.workspace_ref,
                reason_code=semantic.reason_code or merge.reason_code,
                message=semantic.message or "AIT created an integration attempt, but the merge needs recovery.",
                debug={"merge": merge.debug, "semantic": semantic.debug},
            )

    _drop_user_only_paths(workspace, plan)
    _git(workspace, "add", "--all")
    if not _git_stdout(workspace, "diff", "--cached", "--name-only", allow_failure=True).strip():
        update_workspace_lease(workspace, state="conflict", cleanup_policy="hold", preserve_reason="empty integration result")
        return _result(
            root,
            attempt_id=attempt.attempt_id,
            base_attempt_id=base_attempt_id,
            status="held",
            plan=plan,
            changed_files=(),
            workspace_ref=attempt.workspace_ref,
            reason_code=IntegrationCode.REPLAY_AGENT_FAILED,
            message="AIT found no integration changes to record.",
        )
    test = _run_validation(
        workspace,
        test_command or integration_auto_test_command(root),
        shell=integration_auto_test_shell(root),
    )
    if test.returncode != 0:
        update_workspace_lease(workspace, state="conflict", cleanup_policy="hold", preserve_reason="integration validation failed")
        return _result(
            root,
            attempt_id=attempt.attempt_id,
            base_attempt_id=base_attempt_id,
            status="conflict",
            plan=plan,
            changed_files=agent_patch.paths,
            workspace_ref=attempt.workspace_ref,
            reason_code=IntegrationCode.SEMANTIC_MERGE_FAILED if auto_integrate else IntegrationCode.REPLAY_AGENT_FAILED,
            message="AIT created an integration attempt, but validation failed.",
            debug={"validation": test.stderr.strip() or test.stdout.strip()},
        )

    create_commit_for_attempt(root, attempt_id=attempt.attempt_id, message="AIT integration result")
    commit_oid = _git_stdout(workspace, "rev-parse", "--verify", "HEAD")
    changed = tuple(sorted(_git_stdout(workspace, "diff", "--name-only", f"{attempt.base_ref_oid}..HEAD").splitlines()))
    final_patch = _git(workspace, "diff", "--binary", f"{attempt.base_ref_oid}..HEAD").stdout
    result = _result(
        root,
        attempt_id=attempt.attempt_id,
        base_attempt_id=base_attempt_id,
        status="integration_created",
        plan=plan,
        changed_files=changed,
        workspace_ref=attempt.workspace_ref,
        commit_oid=commit_oid,
        reason_code=IntegrationCode.SUCCEEDED,
        message="AIT created an integration attempt.",
        debug={
            "patch_source": agent_patch.source,
            "classification": plan.classification,
            "strategy": plan.strategy,
        },
    )
    patch_ref, result_ref = _write_result_artifacts(root, result, patch=final_patch)
    update_workspace_lease(workspace, state="succeeded", cleanup_policy="auto", clear_preserve_reason=True)
    return IntegrationResult(
        attempt_id=result.attempt_id,
        base_attempt_id=result.base_attempt_id,
        status=result.status,
        plan=result.plan,
        changed_files=result.changed_files,
        commit_oid=result.commit_oid,
        workspace_ref=result.workspace_ref,
        result_artifact_ref=result_ref,
        patch_artifact_ref=patch_ref,
        decision_report=result.decision_report,
        debug=result.debug,
    )


@dataclass(frozen=True, slots=True)
class _MergeOutcome:
    returncode: int
    reason_code: str
    message: str = ""
    debug: dict[str, object] = field(default_factory=dict)


def _run_merge_ladder(
    root: Path,
    workspace: Path,
    *,
    base_workspace: Path,
    snapshot: DirtySnapshot,
    agent_patch: _AgentPatch,
    plan: IntegrationPlan,
) -> _MergeOutcome:
    if plan.classification == "safe_non_overlap":
        applied = _apply_patch(workspace, agent_patch.patch)
        if applied.returncode != 0:
            return _MergeOutcome(1, IntegrationCode.REPLAY_AGENT_FAILED, applied.stderr.strip(), {"git_apply": applied.stderr.strip()})
        return _marker_check(workspace, agent_patch.paths, IntegrationCode.SUCCEEDED)
    if plan.classification != "text_overlap":
        return _MergeOutcome(1, plan.reason_code, plan.reason)

    non_overlap = tuple(path for path in agent_patch.paths if path not in set(plan.overlap_paths))
    if non_overlap:
        applied = _apply_patch(workspace, agent_patch.patch, exclude=plan.overlap_paths)
        if applied.returncode != 0:
            return _MergeOutcome(1, IntegrationCode.REPLAY_AGENT_FAILED, applied.stderr.strip(), {"git_apply": applied.stderr.strip()})
    for rel_path in plan.overlap_paths:
        merged = _merge_text_path(root, workspace, base_workspace, snapshot, rel_path)
        if merged.returncode != 0:
            return merged
    return _marker_check(workspace, tuple(sorted(set(non_overlap) | set(plan.overlap_paths))), IntegrationCode.SUCCEEDED)


def _merge_text_path(root: Path, workspace: Path, base_workspace: Path, snapshot: DirtySnapshot, rel_path: str) -> _MergeOutcome:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        base = tmp_path / "base"
        user = tmp_path / "user"
        agent = tmp_path / "agent"
        _write_git_file(root, snapshot.head_oid, rel_path, base)
        source = root / rel_path
        if not source.exists():
            return _MergeOutcome(1, IntegrationCode.DELETE_OVERLAP, "local path was deleted")
        shutil.copy2(source, user)
        _write_git_file(base_workspace, "HEAD", rel_path, agent)
        completed = subprocess.run(
            ["git", "merge-file", "-p", str(user), str(base), str(agent)],
            cwd=workspace,
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0 or _contains_conflict_markers(completed.stdout.encode("utf-8", errors="replace")):
            return _MergeOutcome(
                1,
                IntegrationCode.MERGE_FILE_CONFLICT,
                completed.stderr.strip() or "file-level three-way merge conflict",
                {"path": rel_path, "merge_file_stderr": completed.stderr.strip()},
            )
        target = workspace / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(completed.stdout, encoding="utf-8")
    return _MergeOutcome(0, IntegrationCode.SUCCEEDED)


def _replay_tracked_dirty(root: Path, workspace: Path, snapshot: DirtySnapshot) -> subprocess.CompletedProcess[str]:
    for item in snapshot.tracked:
        source = root / item.path
        target = workspace / item.path
        try:
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()
        except OSError as exc:
            return subprocess.CompletedProcess(["replay"], 1, "", str(exc))
    return subprocess.CompletedProcess(["replay"], 0, "", "")


def _drop_user_only_paths(workspace: Path, plan: IntegrationPlan) -> None:
    user_only = tuple(sorted(set(plan.user_paths) - set(plan.agent_paths)))
    for rel_path in user_only:
        if _git(workspace, "cat-file", "-e", f"HEAD:{rel_path}", allow_failure=True).returncode == 0:
            _git(workspace, "checkout", "-q", "HEAD", "--", rel_path, allow_failure=True)
        else:
            target = workspace / rel_path
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()


def _apply_patch(workspace: Path, patch: str, *, exclude: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    args = ["apply", "--3way", "--whitespace=nowarn", *(f"--exclude={path}" for path in exclude)]
    return _git(workspace, *args, input_text=patch, allow_failure=True)


def _marker_check(workspace: Path, paths: tuple[str, ...], success_code: str) -> _MergeOutcome:
    markers = _paths_with_conflict_markers(workspace, paths)
    if markers:
        return _MergeOutcome(1, IntegrationCode.MERGE_FILE_CONFLICT, "conflict markers detected", {"conflict_markers": markers})
    return _MergeOutcome(0, success_code)


def _maybe_semantic_merge(
    root: Path,
    workspace: Path,
    *,
    attempt_id: str,
    auto_integrate: bool,
    test_command: str | None,
) -> _MergeOutcome:
    del test_command
    adapter = integration_semantic_adapter(root)
    if not auto_integrate or not adapter:
        return _MergeOutcome(
            1,
            IntegrationCode.MERGE_FILE_CONFLICT,
            "AIT held this integration because semantic merge is not enabled.",
            {"semantic_enabled": False},
        )
    return _MergeOutcome(
        1,
        IntegrationCode.SEMANTIC_MERGE_FAILED,
        "AIT held this integration because the semantic merge adapter scaffold is not configured for automatic writes.",
        {"adapter": adapter, "attempt_id": attempt_id, "workspace": str(workspace)},
    )


def _run_validation(
    workspace: Path,
    command: str | None,
    *,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the integration-validation command.

    P1 fix: the previous form passed the user-supplied ``command`` to
    ``subprocess.run`` with ``shell=True``. On a shared CI runner that
    let a hostile ``policy.json`` execute arbitrary shell via the
    ``integration.auto_test_command`` key. We now parse the command via
    :func:`shlex.split` and run it without a shell by default. Setting
    ``integration.auto_test_shell: true`` in policy opts back into
    shell semantics, but does so via the explicit ``/bin/sh -lc`` argv
    form so the choice is visible to static analyzers and reviewers.
    """
    if not command:
        return subprocess.CompletedProcess(["validation"], 0, "", "")
    if shell:
        argv: list[str] = ["/bin/sh", "-lc", command]
    else:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return subprocess.CompletedProcess(
                ["validation"],
                2,
                "",
                (
                    f"ait: invalid validation command ({exc}). "
                    "Set integration.auto_test_shell=true in policy "
                    "to run the command through /bin/sh.\n"
                ),
            )
        if not argv:
            return subprocess.CompletedProcess(["validation"], 0, "", "")
    return subprocess.run(
        argv,
        cwd=workspace,
        shell=False,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_conflict_bundle(
    root: Path,
    attempt_id: str,
    *,
    base_workspace: Path,
    snapshot: DirtySnapshot,
    paths: tuple[str, ...],
) -> None:
    bundle_root = root / ".ait" / "integration" / _safe_attempt_filename(attempt_id)
    files_root = bundle_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    conflicts = {"schema_version": 1, "attempt_id": attempt_id, "paths": list(paths), "created_at": _utc_now()}
    for rel_path in paths:
        safe_name = _safe_path_filename(rel_path)
        _write_git_file(root, snapshot.head_oid, rel_path, files_root / f"{safe_name}.base", allow_missing=True)
        source = root / rel_path
        if source.exists():
            shutil.copy2(source, files_root / f"{safe_name}.user")
        _write_git_file(base_workspace, "HEAD", rel_path, files_root / f"{safe_name}.agent", allow_missing=True)
    (bundle_root / "conflicts.json").write_text(json.dumps(conflicts, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_result_artifacts(root: Path, result: IntegrationResult, *, patch: str) -> tuple[str, str]:
    results_dir = root / ".ait" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_attempt_filename(result.attempt_id)
    patch_path = results_dir / f"{filename}.patch"
    result_path = results_dir / f"{filename}.json"
    patch_path.write_text(patch, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "attempt_id": result.attempt_id,
        "base_attempt_id": result.base_attempt_id,
        "kind": "integration",
        "strategy": result.plan.strategy,
        "classification": result.plan.classification,
        "root_modified": False,
        "commit_oid": result.commit_oid,
        "changed_files": list(result.changed_files),
        "decision_report": decision_payload(result.decision_report),
        "created_at": _utc_now(),
        "patch_ref": str(patch_path),
        "workspace_ref": result.workspace_ref,
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(patch_path), str(result_path)


def _load_base_attempt(root: Path, selector: str):
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        if selector == "latest":
            attempts = [
                attempt
                for attempt in reversed(list_attempts(conn))
                if attempt.verified_status not in {"discarded", "promoted"}
            ]
            if not attempts:
                attempts = list(reversed(list_attempts(conn)))
            if not attempts:
                raise IntegrationError("no attempts found")
            attempt_id = attempts[0].id
        else:
            attempt_id = resolve_attempt_id(conn, selector)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise IntegrationError(f"Unknown attempt: {attempt_id}")
    finally:
        conn.close()
    return attempt_id, attempt


def _load_agent_patch(root: Path, attempt_id: str, workspace_ref: str, base_ref_oid: str) -> _AgentPatch:
    artifact = root / ".ait" / "results" / f"{_safe_attempt_filename(attempt_id)}.patch"
    if artifact.exists():
        patch = artifact.read_text(encoding="utf-8")
        source = str(artifact)
    else:
        workspace = Path(workspace_ref)
        if not workspace.exists():
            return _AgentPatch("", "missing", (), {}, ())
        patch = _git(workspace, "diff", "--binary", f"{base_ref_oid}..HEAD", allow_failure=True).stdout
        source = "workspace_diff"
    if not patch.strip():
        return _AgentPatch("", source, (), {}, ())
    statuses, binary_paths = _agent_patch_status(root, workspace_ref, base_ref_oid)
    return _AgentPatch(patch, source, tuple(sorted(statuses)), statuses, binary_paths)


def _agent_patch_status(root: Path, workspace_ref: str, base_ref_oid: str) -> tuple[dict[str, str], tuple[str, ...]]:
    workspace = Path(workspace_ref)
    if not workspace.exists():
        return {}, ()
    statuses: dict[str, str] = {}
    output = _git_stdout(workspace, "diff", "--name-status", f"{base_ref_oid}..HEAD", allow_failure=True)
    for line in output.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        paths = parts[1:]
        if status.startswith("R") and len(paths) >= 2:
            statuses[paths[-1]] = "R"
            statuses[paths[0]] = "R"
        elif paths:
            statuses[paths[0]] = status
    binary: list[str] = []
    numstat = _git_stdout(workspace, "diff", "--numstat", f"{base_ref_oid}..HEAD", allow_failure=True)
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] == "-" and parts[1] == "-":
            binary.append(parts[2])
    return statuses, tuple(sorted(binary))


def _dirty_path(root: Path, path: str, status: str, *, tracked: bool = True) -> DirtyPath:
    mode = None
    blob_oid = None
    if tracked:
        ls = _git_stdout(root, "ls-files", "-s", "--", path, allow_failure=True)
        if ls:
            parts = ls.split()
            if len(parts) >= 2:
                mode = parts[0]
                blob_oid = parts[1]
    file_path = root / path
    sha = _sha256_file(file_path) if file_path.is_file() else None
    return DirtyPath(
        path=path,
        status=status,
        mode=mode,
        blob_oid=blob_oid,
        worktree_sha256=sha,
        binary=_is_binary_file(file_path),
    )


def _parse_porcelain_z(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    entries = [entry for entry in output.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        path = entry[3:]
        if status.startswith("R") or status.startswith("C"):
            old_path = entries[index + 1] if index + 1 < len(entries) else ""
            result[path] = status
            if old_path:
                result[old_path] = status
            index += 2
        else:
            result[path] = status
            index += 1
    return result


def _unsupported_status(status: str) -> bool:
    if not status:
        return False
    if "U" in status or status in {"DD", "AA"}:
        return True
    return status[:1] in {"T"} or status[1:2] in {"T"}


def _strategy_for_classification(classification: str) -> str:
    return {
        "safe_non_overlap": "safe-non-overlap",
        "text_overlap": "merge-file",
        "binary_overlap": "hold",
        "delete_overlap": "hold",
        "rename_overlap": "hold",
        "untracked_conflict": "hold",
        "unsafe_status": "hold",
        "no_agent_patch": "hold",
    }.get(classification, "hold")


def _with_plan_ids(plan: IntegrationPlan, *, attempt_id: str, base_attempt_id: str) -> IntegrationPlan:
    return IntegrationPlan(
        attempt_id=attempt_id,
        base_attempt_id=base_attempt_id,
        strategy=plan.strategy,
        classification=plan.classification,
        root_modified=False,
        safe_to_auto_run=plan.safe_to_auto_run,
        user_paths=plan.user_paths,
        agent_paths=plan.agent_paths,
        overlap_paths=plan.overlap_paths,
        blocked_paths=plan.blocked_paths,
        reason_code=plan.reason_code,
        reason=plan.reason,
    )


def _result(
    root: Path,
    *,
    attempt_id: str,
    base_attempt_id: str,
    status: str,
    plan: IntegrationPlan,
    changed_files: tuple[str, ...],
    workspace_ref: str | None,
    reason_code: str,
    message: str,
    commit_oid: str | None = None,
    debug: dict[str, object] | None = None,
) -> IntegrationResult:
    report = decision_report(
        subject="integration",
        subject_id=attempt_id,
        decision=status,
        safety_level="recoverable" if status in {"held", "conflict"} else "automated",
        reason_code=reason_code,
        reason_message=message,
        paths=tuple(sorted(set(plan.overlap_paths) | set(plan.blocked_paths))),
        debug={
            "base_attempt_id": base_attempt_id,
            "strategy": plan.strategy,
            "classification": plan.classification,
            **(debug or {}),
        },
        next_steps=(daily_step(f"ait apply {attempt_id}", "apply the integrated result"),)
        if status == "integration_created"
        else (daily_step(f"ait recover {attempt_id} --debug", "inspect integration details"),),
        metadata={
            "base_attempt_id": base_attempt_id,
            "strategy": plan.strategy,
            "classification": plan.classification,
            "root_modified": False,
            "overlap_paths": list(plan.overlap_paths),
            "blocked_paths": list(plan.blocked_paths),
            "workspace_ref": workspace_ref,
        },
    )
    del root
    return IntegrationResult(
        attempt_id=attempt_id,
        base_attempt_id=base_attempt_id,
        status=status,
        plan=plan,
        changed_files=changed_files,
        commit_oid=commit_oid,
        workspace_ref=workspace_ref,
        result_artifact_ref=None,
        patch_artifact_ref=None,
        decision_report=report,
        debug={
            "workspace_ref": workspace_ref,
            "lease": lease_payload(workspace_ref) if workspace_ref else None,
            "plan": asdict(plan),
            **(debug or {}),
        },
    )


def integration_result_payload(result: IntegrationResult, *, debug: bool = False) -> dict[str, object]:
    payload = asdict(result)
    if not debug:
        payload.pop("debug", None)
    return payload


def _write_git_file(repo: Path, ref: str, rel_path: str, target: Path, *, allow_missing: bool = False) -> None:
    completed = _git(repo, "show", f"{ref}:{rel_path}", allow_failure=True)
    if completed.returncode != 0:
        if allow_missing:
            return
        raise IntegrationError(completed.stderr.strip() or f"missing file at {ref}:{rel_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(completed.stdout.encode("utf-8", errors="surrogateescape"))


def _paths_with_conflict_markers(root: Path, paths: tuple[str, ...]) -> tuple[str, ...]:
    conflicted: list[str] = []
    for rel_path in paths:
        path = root / rel_path
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()[:1024 * 1024]
        except OSError:
            continue
        if b"\0" in data:
            continue
        if _contains_conflict_markers(data):
            conflicted.append(rel_path)
    return tuple(conflicted)


def _contains_conflict_markers(data: bytes) -> bool:
    return b"<<<<<<< " in data or b"=======\n" in data or b">>>>>>> " in data


def _is_binary_file(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return b"\0" in path.read_bytes()[:8192]
    except OSError:
        return False


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _safe_attempt_filename(attempt_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in attempt_id.rsplit(":", 1)[-1])


def _safe_path_filename(path: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in path)


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
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
        raise IntegrationError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed
