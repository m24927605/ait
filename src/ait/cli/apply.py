from __future__ import annotations

from ._shared import *

from ait.app import init_repo
from ait.db import connect_db, list_attempts
from ait.idresolver import resolve_attempt_id
from ait.landing import ApplyError, apply_attempt, apply_result_payload
from ait.review import latest_review_summary
from ait.team_policy import TeamPolicyEnforcementError, enforce_team_policy


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        _enforce_apply_policy(repo_root, str(args.attempt_id))
    except TeamPolicyEnforcementError as exc:
        if args.format == "json":
            print(json.dumps(exc.payload, indent=2, sort_keys=True))
        else:
            print(f"error: team policy blocked apply: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "dry_run", False):
        from ait.merge import merge_result

        result = merge_result(
            repo_root,
            target_branch=args.to,
            mode="apply",
            dry_run=True,
            push=False,
            set_default_branch=False,
        )
        if args.format == "json":
            print(json.dumps(result.to_dict(), indent=2))
        else:
            from ait.merge import format_merge_text

            print(format_merge_text(result))
        return 0 if result.status == "planned" else 1
    try:
        result = apply_attempt(
            repo_root,
            attempt_selector=args.attempt_id,
            target_ref=args.to,
            mode=args.mode,
        )
    except (ApplyError, ValueError, WorkspaceError) as exc:
        if args.format == "json":
            from ait.agent_errors import emit_agent_error
            from ait.agent_state import inspect_agent_state

            emit_agent_error(
                "json",
                error_code="APPLY_FAILED",
                message=_human_apply_error(str(exc)),
                detected_state=inspect_agent_state(repo_root, target_branch=args.to).to_dict().get("detected_context", {}),
                recommended_commands=["ait next --json", "ait recover --json"],
                docs_reference="docs/agent-command-contract.md",
            )
        else:
            print(f"error: {_human_apply_error(str(exc))}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(apply_result_payload(result, debug=args.debug), indent=2))
    else:
        print(_format_apply_result(result, debug=args.debug))
    return 0 if result.status in {"applied", "already_applied"} else 1


def _enforce_apply_policy(repo_root: Path, attempt_selector: str) -> None:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        attempt_id = _resolve_attempt_selector_for_policy(conn, attempt_selector)
        review = latest_review_summary(conn, attempt_id, repo_root=init_result.repo_root)
    finally:
        conn.close()
    enforce_team_policy(
        init_result.repo_root,
        operation="apply",
        attempt_id=attempt_id,
        review_summary=review,
    )


def _resolve_attempt_selector_for_policy(conn, selector: str) -> str:
    if selector == "latest":
        attempts = list_attempts(conn)
        if not attempts:
            return selector
        return attempts[-1].id
    return resolve_attempt_id(conn, selector)


def _format_apply_result(result, *, debug: bool = False) -> str:
    lines = [
        result.message,
        f"Status: {result.status}",
    ]
    if result.changed_files:
        lines.append(f"Changed: {len(result.changed_files)} files")
    if result.branch:
        lines.append(f"Branch: {result.branch}")
    if result.reason:
        lines.append(f"Reason: {result.reason}")
    if result.cleanup_reason:
        lines.append(f"Cleanup: {result.cleanup_reason}")
    elif result.worktree_cleaned:
        lines.append("Cleanup: internal workspace removed")
    if result.status not in {"applied", "already_applied"}:
        lines.append(f"Recover: ait recover {result.attempt_id}")
    if debug:
        lines.extend(
            [
                "Debug:",
                f"  Attempt: {result.attempt_id}",
                f"  Workspace: {result.workspace_ref}",
                f"  Plan: {result.landing_plan.kind}",
            ]
        )
        if result.lease:
            lines.append(f"  Lease: {result.lease.get('lease_path')}")
    else:
        lines.append(f"Attempt: {result.attempt_id.rsplit(':', 1)[-1]}")
    return "\n".join(lines)


def _human_apply_error(message: str) -> str:
    if "Commit or stash" in message or "uncommitted" in message:
        return (
            "AIT could not apply directly because your local edits make that unsafe. "
            "The result was left recoverable; run `ait recover latest --debug` for details."
        )
    return message
