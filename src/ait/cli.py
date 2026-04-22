from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from ait.app import (
    create_attempt,
    create_intent,
    discard_attempt,
    init_repo,
    promote_attempt,
    show_attempt,
    show_intent,
    verify_attempt,
)
from ait.daemon import daemon_status, serve_daemon, start_daemon, stop_daemon
from ait.db import connect_db
from ait.query import blame_path, execute_query, list_shortcut_expression, parse_blame_target
from ait.reconcile import reconcile_repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ait")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init")
    intent_parser = subparsers.add_parser("intent")
    intent_subparsers = intent_parser.add_subparsers(dest="intent_command")
    intent_new = intent_subparsers.add_parser("new")
    intent_new.add_argument("title")
    intent_new.add_argument("--description")
    intent_new.add_argument("--kind")
    intent_show = intent_subparsers.add_parser("show")
    intent_show.add_argument("intent_id")
    intent_list = intent_subparsers.add_parser("list")
    intent_list.add_argument("--status")
    intent_list.add_argument("--kind")
    intent_list.add_argument("--tag")
    intent_list.add_argument("--limit", type=int, default=100)
    intent_list.add_argument("--offset", type=int, default=0)
    intent_list.add_argument("--format", choices=("table", "jsonl"), default="table")

    attempt_parser = subparsers.add_parser("attempt")
    attempt_subparsers = attempt_parser.add_subparsers(dest="attempt_command")
    attempt_new = attempt_subparsers.add_parser("new")
    attempt_new.add_argument("intent_id")
    attempt_show = attempt_subparsers.add_parser("show")
    attempt_show.add_argument("attempt_id")
    attempt_promote = attempt_subparsers.add_parser("promote")
    attempt_promote.add_argument("attempt_id")
    attempt_promote.add_argument("--to", required=True)
    attempt_discard = attempt_subparsers.add_parser("discard")
    attempt_discard.add_argument("attempt_id")
    attempt_verify = attempt_subparsers.add_parser("verify")
    attempt_verify.add_argument("attempt_id")
    attempt_list = attempt_subparsers.add_parser("list")
    attempt_list.add_argument("--intent")
    attempt_list.add_argument("--reported-status")
    attempt_list.add_argument("--verified-status")
    attempt_list.add_argument("--agent")
    attempt_list.add_argument("--limit", type=int, default=100)
    attempt_list.add_argument("--offset", type=int, default=0)
    attempt_list.add_argument("--format", choices=("table", "jsonl"), default="table")

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--on", choices=("intent", "attempt"), default="attempt")
    query_parser.add_argument("expression", nargs="?")
    query_parser.add_argument("--limit", type=int, default=100)
    query_parser.add_argument("--offset", type=int, default=0)
    query_parser.add_argument("--format", choices=("table", "jsonl"), default="table")

    blame_parser = subparsers.add_parser("blame")
    blame_parser.add_argument("target")

    subparsers.add_parser("reconcile")

    daemon_parser = subparsers.add_parser("daemon")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command")
    daemon_subparsers.add_parser("start")
    daemon_subparsers.add_parser("stop")
    daemon_subparsers.add_parser("status")
    daemon_subparsers.add_parser("serve")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path.cwd()

    if args.command == "init":
        result = init_repo(repo_root)
        print(
            json.dumps(
                {
                    "repo_root": str(result.repo_root),
                    "ait_dir": str(result.ait_dir),
                    "db_path": str(result.db_path),
                    "repo_id": result.repo_id,
                    "socket_path": str(result.socket_path),
                },
                indent=2,
            )
        )
        return 0
    if args.command == "intent" and args.intent_command == "new":
        result = create_intent(
            repo_root,
            title=args.title,
            description=args.description,
            kind=args.kind,
        )
        print(json.dumps({"intent_id": result.intent_id, "repo_id": result.repo_id}, indent=2))
        return 0
    if args.command == "intent" and args.intent_command == "show":
        result = show_intent(repo_root, intent_id=args.intent_id)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "intent" and args.intent_command == "list":
        return _run_query_command(
            repo_root,
            subject="intent",
            expression=list_shortcut_expression(
                "intent",
                status=args.status,
                kind=args.kind,
                tag=args.tag,
            ),
            limit=args.limit,
            offset=args.offset,
            output_format=args.format,
        )
    if args.command == "attempt" and args.attempt_command == "new":
        result = create_attempt(repo_root, intent_id=args.intent_id)
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
    if args.command == "attempt" and args.attempt_command == "promote":
        result = promote_attempt(repo_root, attempt_id=args.attempt_id, target_ref=args.to)
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
    if args.command == "query":
        return _run_query_command(
            repo_root,
            subject=args.on,
            expression=args.expression,
            limit=args.limit,
            offset=args.offset,
            output_format=args.format,
        )
    if args.command == "blame":
        init_result = init_repo(repo_root)
        conn = connect_db(init_result.db_path)
        try:
            target = parse_blame_target(args.target)
            rows = blame_path(conn, target.path)
        finally:
            conn.close()
        print(_format_rows([row.__dict__ for row in rows], "table"))
        return 0
    if args.command == "reconcile":
        result = reconcile_repo(repo_root)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "daemon":
        if args.daemon_command == "start":
            status = start_daemon(repo_root)
            print(json.dumps(asdict(status), default=str, indent=2))
            return 0
        if args.daemon_command == "stop":
            status = stop_daemon(repo_root)
            print(json.dumps(asdict(status), default=str, indent=2))
            return 0
        if args.daemon_command == "status":
            status = daemon_status(repo_root)
            print(json.dumps(asdict(status), default=str, indent=2))
            return 0
        if args.daemon_command == "serve":
            serve_daemon(repo_root)
            return 0
    parser.print_help()
    return 1


def _run_query_command(
    repo_root: Path,
    *,
    subject: str,
    expression: str | None,
    limit: int,
    offset: int,
    output_format: str,
) -> int:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        rows = execute_query(
            conn,
            subject,
            expression,
            limit=limit,
            offset=offset,
        )
    finally:
        conn.close()
    print(_format_rows([dict(row) for row in rows], output_format))
    return 0


def _format_rows(rows: list[dict[str, object]], output_format: str) -> str:
    if output_format == "jsonl":
        return "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    if not rows:
        return ""
    columns = list(rows[0].keys())
    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = max(widths[column], len(str(row.get(column, ""))))
    header = " ".join(column.ljust(widths[column]) for column in columns)
    body = [
        " ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        for row in rows
    ]
    return "\n".join([header, *body])


if __name__ == "__main__":
    raise SystemExit(main())
