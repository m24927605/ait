from __future__ import annotations

from ._shared import *

from ait.landing import ApplyError, apply_attempt, apply_result_payload


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        result = apply_attempt(
            repo_root,
            attempt_selector=args.attempt_id,
            target_ref=args.to,
            mode=args.mode,
        )
    except (ApplyError, ValueError, WorkspaceError) as exc:
        print(f"error: {_human_apply_error(str(exc))}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(apply_result_payload(result, debug=args.debug), indent=2))
    else:
        print(_format_apply_result(result, debug=args.debug))
    return 0 if result.status in {"applied", "already_applied"} else 1


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
