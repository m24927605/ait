from __future__ import annotations

from ._shared import *

from ait.landing import ApplyError, apply_attempt, apply_result_payload
from ait.recovery import (
    RecoverError,
    create_integration_attempt,
    discard_recoverable_attempt,
    recover_attempt,
    recover_result_payload,
)
from ait.cli.apply import _format_apply_result


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        if args.retry_apply:
            applied = apply_attempt(repo_root, attempt_selector=args.attempt_id)
            if args.format == "json":
                print(json.dumps(apply_result_payload(applied, debug=args.debug), indent=2))
            else:
                print(_format_apply_result(applied, debug=args.debug))
            return 0 if applied.status in {"applied", "already_applied"} else 1
        if args.create_integration or args.auto_integrate:
            result = create_integration_attempt(
                repo_root,
                attempt_selector=args.attempt_id,
                auto_integrate=args.auto_integrate,
                test_command=args.integration_test_command,
            )
        elif args.discard:
            result = discard_recoverable_attempt(repo_root, attempt_selector=args.attempt_id)
        else:
            result = recover_attempt(repo_root, attempt_selector=args.attempt_id)
    except (ApplyError, RecoverError, ValueError, WorkspaceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(recover_result_payload(result, debug=args.debug), indent=2))
    else:
        print(_format_recover_result(result, debug=args.debug))
    return 0 if result.recoverable or result.status in {"applied", "discarded"} else 1


def _format_recover_result(result, *, debug: bool = False) -> str:
    lines = [
        result.message,
        f"Status: {result.status}",
    ]
    if result.changed_files:
        lines.append(f"Changed: {len(result.changed_files)} files")
    if result.next_steps:
        lines.append("Next:")
        lines.extend(f"- {step}" for step in result.next_steps)
    if debug:
        lines.extend(
            [
                "Debug:",
                f"  Attempt: {result.attempt_id}",
                f"  Workspace: {result.workspace_ref}",
            ]
        )
        if result.lease:
            lines.append(f"  Lease: {result.lease.get('lease_path')}")
        if result.debug:
            if result.debug.get("base_attempt_id"):
                lines.append(f"  Base attempt: {result.debug.get('base_attempt_id')}")
            if result.debug.get("integration_attempt_id"):
                lines.append(f"  Integration attempt: {result.debug.get('integration_attempt_id')}")
            if result.debug.get("strategy"):
                lines.append(f"  Strategy: {result.debug.get('strategy')}")
            if result.debug.get("classification"):
                lines.append(f"  Classification: {result.debug.get('classification')}")
            if result.debug.get("reason_code"):
                lines.append(f"  Reason code: {result.debug.get('reason_code')}")
    else:
        lines.append(f"Attempt: {result.attempt_id.rsplit(':', 1)[-1]}")
    return "\n".join(lines)
