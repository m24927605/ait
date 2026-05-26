from __future__ import annotations

from ._shared import *

from ait.db import (
    get_attempt_identity,
    list_attempt_aliases,
    list_attempt_identities,
    set_attempt_alias,
    unset_attempt_alias,
)
from ait.idresolver import resolve_attempt_selector


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
        output_format = _resolve_cli_output_format(getattr(args, "format", None))
        if output_format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_attempt_show(result))
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
        except (ValueError, WorkspaceError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "land":
        try:
            result = land_attempt(repo_root, attempt_id=args.attempt_id, target_ref=args.to)
        except (ValueError, WorkspaceError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "attempt" and args.attempt_command == "rebase":
        try:
            result = rebase_attempt(repo_root, attempt_id=args.attempt_id, onto_ref=args.onto)
        except (ValueError, WorkspaceError) as exc:
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
    if args.command == "attempt" and args.attempt_command == "alias":
        return _handle_attempt_alias(args, repo_root)
    if parser is not None:
        parser.print_help()
    return 1


def _format_attempt_show(result) -> str:
    attempt = result.attempt
    handle = attempt.get("attempt_handle") or str(attempt.get("id", "")).rsplit(":", 1)[-1]
    status = attempt.get("verified_status") or attempt.get("reported_status") or "unknown"
    changed = tuple(result.files.get("changed", ()))
    lines = [
        f"Attempt: {handle}",
        f"Status: {status}",
    ]
    if attempt.get("agent_id"):
        lines.append(f"Agent: {attempt.get('agent_id')}")
    if attempt.get("attempt_description"):
        lines.append(f"Description: {attempt.get('attempt_description')}")
    if changed:
        lines.append("Changed files:")
        lines.extend(f"- {path}" for path in changed)
    else:
        lines.append("Changed: 0 files")
    outcome = result.outcome or {}
    if outcome.get("outcome_class"):
        lines.append(f"Outcome: {outcome.get('outcome_class')}")
    next_steps = _attempt_show_next_steps(status, handle)
    if next_steps:
        lines.append("Next:")
        lines.extend(f"- {step}" for step in next_steps)
    else:
        lines.append("Next: no action")
    return "\n".join(lines)


def _attempt_show_next_steps(status: object, handle: str) -> list[str]:
    if status == "succeeded":
        return [f"ait apply {handle}", f"ait review attempt {handle}"]
    if status in {"failed", "pending"}:
        return [f"ait recover {handle}"]
    return []


def _handle_attempt_alias(args, repo_root: Path) -> int:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        if args.attempt_alias_command == "set":
            attempt_id = resolve_attempt_selector(conn, args.attempt_id)
            record = set_attempt_alias(
                conn,
                attempt_id=attempt_id,
                alias=args.alias,
                force=args.force,
            )
            identity = get_attempt_identity(conn, record.attempt_id)
            handle = identity.handle if identity is not None else record.attempt_id
            print(f"Alias {record.alias} -> {handle}")
            return 0
        if args.attempt_alias_command == "unset":
            removed = unset_attempt_alias(conn, args.alias)
            if not removed:
                print(f"error: unknown alias: {args.alias}", file=sys.stderr)
                return 2
            print(f"Alias {args.alias} removed")
            return 0
        if args.attempt_alias_command == "list":
            print(_format_attempt_aliases(conn))
            return 0
    except (LookupError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    return 1


def _format_attempt_aliases(conn) -> str:
    aliases = list_attempt_aliases(conn)
    if not aliases:
        return "No attempt aliases."
    identities = list_attempt_identities(
        conn,
        tuple(record.attempt_id for record in aliases),
    )
    rows = []
    for record in aliases:
        identity = identities.get(record.attempt_id)
        rows.append(
            {
                "alias": record.alias,
                "handle": "" if identity is None else identity.handle,
                "attempt": record.attempt_id.rsplit(":", 1)[-1],
            }
        )
    return _format_rows(rows, "table")
