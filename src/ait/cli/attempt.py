from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "attempt" and args.attempt_command == "new":
        result = create_attempt(
            repo_root,
            intent_id=args.intent_id,
            agent_id=args.agent_id,
        )
        print(
            json.dumps(
                {
                    "attempt_id": result.attempt_id,
                    "workspace_ref": result.workspace_ref,
                    "base_ref_oid": result.base_ref_oid,
                    "ownership_token": result.ownership_token,
                },
                indent=2,
            )
        )
        return 0
    if args.command == "attempt" and args.attempt_command == "show":
        result = show_attempt(repo_root, attempt_id=args.attempt_id)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "commit":
        result = create_commit_for_attempt(
            repo_root,
            attempt_id=args.attempt_id,
            message=args.message,
        )
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "promote":
        try:
            result = promote_attempt(repo_root, attempt_id=args.attempt_id, target_ref=args.to)
        except WorkspaceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "rebase":
        try:
            result = rebase_attempt(repo_root, attempt_id=args.attempt_id, onto_ref=args.onto)
        except WorkspaceError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "discard":
        result = discard_attempt(repo_root, attempt_id=args.attempt_id)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "verify":
        result = verify_attempt(repo_root, attempt_id=args.attempt_id)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "list":
        return _run_query_command(
            repo_root,
            subject="attempt",
            expression=list_shortcut_expression(
                "attempt",
                intent=args.intent,
                reported_status=args.reported_status,
                verified_status=args.verified_status,
                agent=args.agent,
            ),
            limit=args.limit,
            offset=args.offset,
            output_format=args.format,
        )
    if parser is not None:
        parser.print_help()
    return 1
