from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess

from ait.agent_errors import agent_error_payload
from ait.agent_state import AgentState, detected_context_payload, inspect_agent_state
from ait.landing import apply_attempt, apply_result_payload
from ait.reconcile import reconcile_repo


MERGE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class MergeOperation:
    kind: str
    command: tuple[str, ...]
    cwd: str
    will_execute: bool


@dataclass(frozen=True, slots=True)
class MergeResult:
    schema_version: int
    status: str
    mode: str
    dry_run: bool
    target_branch: str | None
    target_ref: str | None
    source_ref: str | None
    current_state: str
    detected_context: dict[str, object]
    operations: tuple[MergeOperation, ...]
    blocking_reasons: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    message: str
    apply: dict[str, object] | None = None
    pushed: bool = False
    error: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["operations"] = [asdict(operation) for operation in self.operations]
        return payload


class MergeError(RuntimeError):
    pass


def merge_result(
    cwd: str | Path,
    *,
    target_branch: str | None = None,
    mode: str = "auto",
    dry_run: bool = False,
    push: bool = False,
    set_default_branch: bool = False,
) -> MergeResult:
    if mode not in {"auto", "apply", "ff-only", "merge"}:
        raise MergeError(f"unsupported merge mode: {mode}")
    state = inspect_agent_state(cwd, target_branch=target_branch)
    if state.repo_root is None or state.worktree is None:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target_branch,
            source_ref=None,
            operations=(),
            error_code="NOT_GIT_REPOSITORY",
            message="AIT merge must run inside a Git repository.",
            recommended=("git status",),
        )
    target = target_branch or state.target_branch
    if not target:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=None,
            source_ref=None,
            operations=(),
            error_code="NO_TARGET_BRANCH",
            message="No target branch could be inferred.",
            recommended=("ait merge --to main --dry-run --json",),
        )
    source_ref = state.worktree.current_branch or state.worktree.head_oid
    operations: list[MergeOperation] = []

    if state.blocking_reasons:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target,
            source_ref=source_ref,
            operations=tuple(operations),
            error_code="DIRTY_WORKTREE",
            message="AIT merge is blocked because a worktree has uncommitted or untracked changes.",
            blocking_reasons=state.blocking_reasons,
            recommended=("git status --short", "ait merge --dry-run --json"),
        )

    if mode in {"auto", "apply"} and state.attempt.attempt_id:
        return _merge_attempt_result(
            state,
            target_branch=target,
            mode=mode,
            dry_run=dry_run,
            push=push,
            set_default_branch=set_default_branch,
            operations=operations,
        )
    if mode == "apply":
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target,
            source_ref=source_ref,
            operations=tuple(operations),
            error_code="NO_ATTEMPT_RESULT",
            message="Apply mode requires an AIT attempt result in the current context.",
            recommended=("ait whereami --json", "ait next --json"),
        )

    return _merge_branch_result(
        state,
        target_branch=target,
        mode="ff-only" if mode == "auto" else mode,
        dry_run=dry_run,
        push=push,
        set_default_branch=set_default_branch,
        operations=operations,
    )


def _merge_attempt_result(
    state: AgentState,
    *,
    target_branch: str,
    mode: str,
    dry_run: bool,
    push: bool,
    set_default_branch: bool,
    operations: list[MergeOperation],
) -> MergeResult:
    assert state.repo_root is not None
    assert state.worktree is not None
    assert state.attempt.attempt_id is not None
    repo_root = Path(state.repo_root)
    attempt_id = state.attempt.attempt_id
    if state.attempt.manual_commits_can_be_synthetic:
        operations.append(
            MergeOperation(
                kind="ait",
                command=("ait", "reconcile", "--json"),
                cwd=state.worktree.path,
                will_execute=not dry_run,
            )
        )
        if not dry_run:
            reconciled = reconcile_repo(state.worktree.path)
            if not reconciled.synthetic_result_created:
                refreshed = inspect_agent_state(state.worktree.path, target_branch=target_branch)
                return _blocked(
                    refreshed,
                    mode=mode,
                    dry_run=dry_run,
                    target_branch=target_branch,
                    source_ref=state.worktree.head_oid,
                    operations=tuple(operations),
                    error_code="RECONCILE_REQUIRED",
                    message="AIT could not synthesize a result from the current manual commits.",
                    blocking_reasons=(reconciled.blocking_reason or "reconcile did not create a synthetic result",),
                    recommended=("ait reconcile --json", f"ait merge --to {target_branch} --dry-run --json"),
                )
            state = inspect_agent_state(state.worktree.path, target_branch=target_branch)

    if not state.attempt.result_metadata_exists:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target_branch,
            source_ref=state.worktree.head_oid if state.worktree else None,
            operations=tuple(operations),
            error_code="NO_RECORDED_RESULT",
            message="No recorded AIT result was found for this attempt.",
            recommended=("ait reconcile --json", f"ait merge --to {target_branch} --dry-run --json"),
        )

    operations.append(
        MergeOperation(
            kind="ait",
            command=("ait", "apply", attempt_id, "--to", target_branch, "--format", "json"),
            cwd=str(repo_root),
            will_execute=not dry_run,
        )
    )
    if push:
        operations.append(
            MergeOperation(
                kind="git",
                command=("git", "push", "origin", target_branch),
                cwd=str(repo_root),
                will_execute=not dry_run,
            )
        )
    if set_default_branch:
        operations.append(
            MergeOperation(
                kind="git",
                command=("git", "config", "ait.defaultBranch", target_branch),
                cwd=str(repo_root),
                will_execute=not dry_run,
            )
        )

    if dry_run:
        return _result(
            state,
            status="planned",
            mode=mode,
            dry_run=True,
            target_branch=target_branch,
            source_ref=state.worktree.head_oid if state.worktree else None,
            operations=tuple(operations),
            message="Dry run: AIT would apply the recorded attempt result.",
        )

    applied = apply_attempt(repo_root, attempt_selector=attempt_id, target_ref=target_branch, mode="auto")
    pushed = False
    if applied.status in {"applied", "already_applied"}:
        if push:
            _git(repo_root, "push", "origin", target_branch)
            pushed = True
        if set_default_branch:
            _git(repo_root, "config", "ait.defaultBranch", target_branch)
    status = "merged" if applied.status in {"applied", "already_applied"} else "blocked"
    return _result(
        inspect_agent_state(repo_root, target_branch=target_branch),
        status=status,
        mode=mode,
        dry_run=False,
        target_branch=target_branch,
        source_ref=state.worktree.head_oid if state.worktree else None,
        operations=tuple(operations),
        message="AIT applied the recorded result." if status == "merged" else applied.message,
        apply=apply_result_payload(applied, debug=True),
        pushed=pushed,
        blocking_reasons=() if status == "merged" else (applied.reason or applied.message,),
    )


def _merge_branch_result(
    state: AgentState,
    *,
    target_branch: str,
    mode: str,
    dry_run: bool,
    push: bool,
    set_default_branch: bool,
    operations: list[MergeOperation],
) -> MergeResult:
    assert state.repo_root is not None
    assert state.worktree is not None
    repo_root = Path(state.repo_root)
    source_ref = state.worktree.current_branch or state.worktree.head_oid
    source_oid = state.worktree.head_oid
    if not source_ref or not source_oid:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target_branch,
            source_ref=source_ref,
            operations=tuple(operations),
            error_code="NO_SOURCE_REF",
            message="AIT could not determine the source ref to merge.",
            recommended=("git status",),
        )
    target_ref = f"refs/heads/{target_branch}"
    target_oid = _git_stdout(repo_root, "rev-parse", "--verify", target_ref, allow_failure=True)
    if not target_oid:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target_branch,
            source_ref=source_ref,
            operations=tuple(operations),
            error_code="TARGET_BRANCH_NOT_FOUND",
            message=f"Target branch not found: {target_branch}",
            recommended=(f"git branch {target_branch}", f"ait merge --to {target_branch} --dry-run --json"),
        )

    can_ff = _git(repo_root, "merge-base", "--is-ancestor", target_ref, source_oid, allow_failure=True).returncode == 0
    if mode == "ff-only" and not can_ff:
        return _blocked(
            state,
            mode=mode,
            dry_run=dry_run,
            target_branch=target_branch,
            source_ref=source_ref,
            operations=tuple(operations),
            error_code="FAST_FORWARD_NOT_POSSIBLE",
            message="Fast-forward merge is not possible.",
            recommended=(f"ait merge --to {target_branch} --mode merge --dry-run --json",),
        )

    primary_branch = state.primary_worktree.current_branch if state.primary_worktree else None
    if primary_branch != target_branch:
        operations.append(
            MergeOperation(
                kind="git",
                command=("git", "checkout", target_branch),
                cwd=str(repo_root),
                will_execute=not dry_run,
            )
        )
    merge_args = ("merge", "--ff-only", source_oid) if mode == "ff-only" else ("merge", "--no-edit", source_oid)
    operations.append(
        MergeOperation(
            kind="git",
            command=("git", *merge_args),
            cwd=str(repo_root),
            will_execute=not dry_run,
        )
    )
    if push:
        operations.append(
            MergeOperation(
                kind="git",
                command=("git", "push", "origin", target_branch),
                cwd=str(repo_root),
                will_execute=not dry_run,
            )
        )
    if set_default_branch:
        operations.append(
            MergeOperation(
                kind="git",
                command=("git", "config", "ait.defaultBranch", target_branch),
                cwd=str(repo_root),
                will_execute=not dry_run,
            )
        )
    if dry_run:
        return _result(
            state,
            status="planned",
            mode=mode,
            dry_run=True,
            target_branch=target_branch,
            source_ref=source_ref,
            operations=tuple(operations),
            message="Dry run: AIT would merge the current branch into the target branch.",
        )

    if primary_branch != target_branch:
        _git(repo_root, "checkout", target_branch)
    _git(repo_root, *merge_args)
    pushed = False
    if push:
        _git(repo_root, "push", "origin", target_branch)
        pushed = True
    if set_default_branch:
        _git(repo_root, "config", "ait.defaultBranch", target_branch)
    return _result(
        inspect_agent_state(repo_root, target_branch=target_branch),
        status="merged",
        mode=mode,
        dry_run=False,
        target_branch=target_branch,
        source_ref=source_ref,
        operations=tuple(operations),
        message="AIT merged the current branch into the target branch.",
        pushed=pushed,
    )


def _blocked(
    state: AgentState,
    *,
    mode: str,
    dry_run: bool,
    target_branch: str | None,
    source_ref: str | None,
    operations: tuple[MergeOperation, ...],
    error_code: str,
    message: str,
    blocking_reasons: tuple[str, ...] = (),
    recommended: tuple[str, ...] = (),
) -> MergeResult:
    detected = detected_context_payload(state)
    reasons = blocking_reasons or state.blocking_reasons or (message,)
    error = agent_error_payload(
        error_code=error_code,
        message=message,
        detected_state=detected,
        user_data_safe=True,
        blocking_reason=reasons[0] if reasons else message,
        recommended_commands=recommended,
        docs_reference="docs/safe-merge-workflow.md",
    )
    return _result(
        state,
        status="blocked",
        mode=mode,
        dry_run=dry_run,
        target_branch=target_branch,
        source_ref=source_ref,
        operations=operations,
        message=message,
        blocking_reasons=reasons,
        recommended_commands=recommended,
        error=error,
    )


def _result(
    state: AgentState,
    *,
    status: str,
    mode: str,
    dry_run: bool,
    target_branch: str | None,
    source_ref: str | None,
    operations: tuple[MergeOperation, ...],
    message: str,
    blocking_reasons: tuple[str, ...] = (),
    recommended_commands: tuple[str, ...] = (),
    apply: dict[str, object] | None = None,
    pushed: bool = False,
    error: dict[str, object] | None = None,
) -> MergeResult:
    return MergeResult(
        schema_version=MERGE_SCHEMA_VERSION,
        status=status,
        mode=mode,
        dry_run=dry_run,
        target_branch=target_branch,
        target_ref=f"refs/heads/{target_branch}" if target_branch else None,
        source_ref=source_ref,
        current_state=state.current_state,
        detected_context=detected_context_payload(state),
        operations=operations,
        blocking_reasons=blocking_reasons,
        recommended_commands=recommended_commands,
        message=message,
        apply=apply,
        pushed=pushed,
        error=error,
    )


def format_merge_text(result: MergeResult) -> str:
    lines = [
        result.message,
        f"Status: {result.status}",
        f"Mode: {result.mode}",
    ]
    if result.target_branch:
        lines.append(f"Target: {result.target_branch}")
    if result.source_ref:
        lines.append(f"Source: {result.source_ref}")
    if result.blocking_reasons:
        lines.append("Blocking:")
        lines.extend(f"- {reason}" for reason in result.blocking_reasons)
    if result.operations:
        lines.append("Operations:")
        for operation in result.operations:
            prefix = "would run" if result.dry_run else "ran" if operation.will_execute else "plan"
            lines.append(f"- {prefix}: {' '.join(operation.command)}")
    if result.recommended_commands:
        lines.append("Recommended:")
        lines.extend(f"- {command}" for command in result.recommended_commands)
    return "\n".join(lines)


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    completed = _git(cwd, *args, allow_failure=allow_failure)
    if completed.returncode != 0 and allow_failure:
        return ""
    return completed.stdout.strip()


def _git(cwd: Path, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not allow_failure:
        raise MergeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed
