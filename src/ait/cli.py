from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib import metadata
import json
from pathlib import Path
import sys
import tomllib

from ait.adapters import (
    ADAPTERS,
    AdapterError,
    bootstrap_adapter,
    bootstrap_shell_snippet,
    doctor_adapter,
    doctor_automation,
    get_adapter,
    list_adapters,
    setup_adapter,
)
from ait.context import build_agent_context, render_agent_context_text
from ait.app import (
    abandon_intent,
    create_commit_for_attempt,
    create_attempt,
    create_intent,
    discard_attempt,
    init_repo,
    promote_attempt,
    rebase_attempt,
    show_attempt,
    show_intent,
    supersede_intent,
    verify_attempt,
)
from ait.daemon import daemon_status, serve_daemon, start_daemon, stop_daemon
from ait.db import connect_db
from ait.memory import (
    add_memory_note,
    build_repo_memory,
    list_memory_notes,
    remove_memory_note,
    render_repo_memory_text,
    render_memory_search_results,
    search_repo_memory,
)
from ait.memory_policy import init_memory_policy, load_memory_policy
from ait.query import blame_path, execute_query, list_shortcut_expression, parse_blame_target
from ait.reconcile import reconcile_repo
from ait.repo import resolve_repo_root
from ait.runner import run_agent_command
from ait.workspace import WorkspaceError


def package_version() -> str:
    try:
        return metadata.version("ait-vcs")
    except metadata.PackageNotFoundError:
        pyproject = next(
            (
                parent / "pyproject.toml"
                for parent in Path(__file__).resolve().parents
                if (parent / "pyproject.toml").is_file()
            ),
            None,
        )
        if pyproject is None:
            return "0+unknown"
        data = tomllib.loads(pyproject.read_text())
        return str(data.get("project", {}).get("version", "0+unknown"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ait")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    parser.add_argument("--no-hints", action="store_true")
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
    intent_abandon = intent_subparsers.add_parser("abandon")
    intent_abandon.add_argument("intent_id")
    intent_supersede = intent_subparsers.add_parser("supersede")
    intent_supersede.add_argument("intent_id")
    intent_supersede.add_argument("--by", required=True)
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
    attempt_new.add_argument("--agent-id")
    attempt_show = attempt_subparsers.add_parser("show")
    attempt_show.add_argument("attempt_id")
    attempt_commit = attempt_subparsers.add_parser("commit")
    attempt_commit.add_argument("attempt_id")
    attempt_commit.add_argument("-m", "--message", required=True)
    attempt_promote = attempt_subparsers.add_parser("promote")
    attempt_promote.add_argument("attempt_id")
    attempt_promote.add_argument("--to", required=True)
    attempt_rebase = attempt_subparsers.add_parser("rebase")
    attempt_rebase.add_argument("attempt_id")
    attempt_rebase.add_argument("--onto", required=True)
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

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--adapter", choices=tuple(sorted(ADAPTERS)), default="shell")
    run_parser.add_argument("--agent")
    run_parser.add_argument("--intent", required=True)
    run_parser.add_argument("--kind")
    run_parser.add_argument("--description")
    run_parser.add_argument("--commit-message")
    run_parser.add_argument("--with-context", action="store_true")
    run_parser.add_argument("--format", choices=("json", "text"), default="json")
    run_parser.add_argument("run_command", nargs=argparse.REMAINDER)

    context_parser = subparsers.add_parser("context")
    context_parser.add_argument("intent_id")
    context_parser.add_argument("--format", choices=("text", "json"), default="text")

    memory_parser = subparsers.add_parser("memory")
    memory_parser.add_argument("--limit", type=int, default=8)
    memory_parser.add_argument("--path", dest="path_filter")
    memory_parser.add_argument("--topic")
    memory_parser.add_argument("--promoted-only", action="store_true")
    memory_parser.add_argument("--budget-chars", type=int)
    memory_parser.add_argument("--format", choices=("text", "json"), default="text")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    memory_note = memory_subparsers.add_parser("note")
    memory_note_subparsers = memory_note.add_subparsers(dest="memory_note_command")
    memory_note_add = memory_note_subparsers.add_parser("add")
    memory_note_add.add_argument("body")
    memory_note_add.add_argument("--topic")
    memory_note_add.add_argument("--source", default="manual")
    memory_note_add.add_argument("--format", choices=("text", "json"), default="json")
    memory_note_list = memory_note_subparsers.add_parser("list")
    memory_note_list.add_argument("--topic")
    memory_note_list.add_argument("--limit", type=int, default=100)
    memory_note_list.add_argument("--format", choices=("text", "json"), default="text")
    memory_note_remove = memory_note_subparsers.add_parser("remove")
    memory_note_remove.add_argument("note_id")
    memory_note_remove.add_argument("--format", choices=("text", "json"), default="json")
    memory_search = memory_subparsers.add_parser("search")
    memory_search.add_argument("query")
    memory_search.add_argument("--limit", type=int, default=8)
    memory_search.add_argument("--ranker", choices=("vector", "lexical"), default="vector")
    memory_search.add_argument("--format", choices=("text", "json"), default="text")
    memory_policy = memory_subparsers.add_parser("policy")
    memory_policy_subparsers = memory_policy.add_subparsers(dest="memory_policy_command")
    memory_policy_init = memory_policy_subparsers.add_parser("init")
    memory_policy_init.add_argument("--force", action="store_true")
    memory_policy_init.add_argument("--format", choices=("text", "json"), default="json")
    memory_policy_show = memory_policy_subparsers.add_parser("show")
    memory_policy_show.add_argument("--format", choices=("text", "json"), default="json")

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("name", choices=tuple(sorted(ADAPTERS)), nargs="?", default="claude-code")
    bootstrap_parser.add_argument("--format", choices=("text", "json"), default="json")
    bootstrap_parser.add_argument("--shell", action="store_true")
    bootstrap_parser.add_argument("--check", action="store_true")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("name", choices=tuple(sorted(ADAPTERS)), nargs="?", default="claude-code")
    doctor_parser.add_argument("--format", choices=("text", "json"), default="text")
    doctor_parser.add_argument("--fix", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("name", choices=tuple(sorted(ADAPTERS)), nargs="?", default="claude-code")
    status_parser.add_argument("--format", choices=("text", "json"), default="text")

    adapter_parser = subparsers.add_parser("adapter")
    adapter_subparsers = adapter_parser.add_subparsers(dest="adapter_command")
    adapter_list = adapter_subparsers.add_parser("list")
    adapter_list.add_argument("--format", choices=("table", "json"), default="table")
    adapter_show = adapter_subparsers.add_parser("show")
    adapter_show.add_argument("name", choices=tuple(sorted(ADAPTERS)))
    adapter_show.add_argument("--format", choices=("text", "json"), default="text")
    adapter_doctor = adapter_subparsers.add_parser("doctor")
    adapter_doctor.add_argument("name", choices=tuple(sorted(ADAPTERS)))
    adapter_doctor.add_argument("--format", choices=("text", "json"), default="text")
    adapter_setup = adapter_subparsers.add_parser("setup")
    adapter_setup.add_argument("name", choices=tuple(sorted(ADAPTERS)))
    adapter_setup.add_argument("--target", default=".claude/settings.json")
    adapter_setup.add_argument("--print", action="store_true", dest="print_only")
    adapter_setup.add_argument("--install-wrapper", action="store_true")
    adapter_setup.add_argument("--install-direnv", action="store_true")

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
    if args.command == "intent" and args.intent_command == "abandon":
        result = abandon_intent(repo_root, intent_id=args.intent_id)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.command == "intent" and args.intent_command == "supersede":
        result = supersede_intent(repo_root, intent_id=args.intent_id, by_intent_id=args.by)
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
    if args.command == "run":
        command = args.run_command
        if command and command[0] == "--":
            command = command[1:]
        try:
            result = run_agent_command(
                repo_root,
                intent_title=args.intent,
                agent_id=args.agent,
                command=command,
                adapter_name=args.adapter,
                kind=args.kind,
                description=args.description,
                commit_message=args.commit_message,
                with_context=args.with_context,
                capture_command_output=args.format == "json",
            )
        except (AdapterError, WorkspaceError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(result), indent=2))
        return result.exit_code
    if args.command == "context":
        context = build_agent_context(repo_root, intent_id=args.intent_id)
        if args.format == "json":
            print(json.dumps(asdict(context), indent=2))
        else:
            print(render_agent_context_text(context), end="")
        return 0
    if args.command == "memory":
        if args.memory_command == "note":
            if args.memory_note_command == "add":
                note = add_memory_note(
                    repo_root,
                    body=args.body,
                    topic=args.topic,
                    source=args.source,
                )
                if args.format == "json":
                    print(json.dumps(asdict(note), indent=2))
                else:
                    print(f"added {note.id}")
                return 0
            if args.memory_note_command == "list":
                notes = list_memory_notes(repo_root, topic=args.topic, limit=args.limit)
                if args.format == "json":
                    print(json.dumps([asdict(note) for note in notes], indent=2))
                else:
                    if not notes:
                        print("No memory notes.")
                    for note in notes:
                        topic = note.topic if note.topic else "general"
                        print(f"{note.id}\ttopic={topic}\tsource={note.source}\t{note.body}")
                return 0
            if args.memory_note_command == "remove":
                removed = remove_memory_note(repo_root, note_id=args.note_id)
                if args.format == "json":
                    print(json.dumps({"note_id": args.note_id, "removed": removed}, indent=2))
                else:
                    print(f"removed {args.note_id}" if removed else f"not found {args.note_id}")
                return 0 if removed else 2
        if args.memory_command == "search":
            results = search_repo_memory(
                repo_root,
                args.query,
                limit=args.limit,
                ranker=args.ranker,
            )
            if args.format == "json":
                print(json.dumps([asdict(result) for result in results], indent=2))
            else:
                print(render_memory_search_results(results), end="")
            return 0
        if args.memory_command == "policy":
            if args.memory_policy_command == "init":
                result = init_memory_policy(repo_root, overwrite=args.force)
                if args.format == "json":
                    print(json.dumps(result.to_dict(), indent=2))
                else:
                    print(("created " if result.created else "exists ") + result.path)
                return 0
            if args.memory_policy_command == "show":
                policy = load_memory_policy(repo_root)
                if args.format == "json":
                    print(json.dumps(policy.to_dict(), indent=2))
                else:
                    print("Memory policy")
                    print("Excluded paths:")
                    for path in policy.exclude_paths:
                        print(f"- {path}")
                    print("Excluded transcript patterns:")
                    for pattern in policy.exclude_transcript_patterns:
                        print(f"- {pattern}")
                return 0
        memory = build_repo_memory(
            repo_root,
            limit=args.limit,
            path_filter=args.path_filter,
            topic=args.topic,
            promoted_only=args.promoted_only,
        )
        if args.format == "json":
            print(json.dumps(memory.to_dict(), indent=2))
        else:
            print(render_repo_memory_text(memory, budget_chars=args.budget_chars), end="")
        return 0
    if args.command == "bootstrap":
        try:
            if args.shell:
                print(bootstrap_shell_snippet(args.name, repo_root))
                return 0
            if args.check:
                result = doctor_automation(args.name, repo_root)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_adapter_doctor(result))
                return 0 if result.ok else 2
            result = bootstrap_adapter(args.name, repo_root)
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_bootstrap(result))
        return 0 if result.ok else 2
    if args.command == "doctor":
        if args.fix:
            try:
                print(bootstrap_shell_snippet(args.name, repo_root))
            except AdapterError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            return 0
        result = doctor_automation(args.name, repo_root)
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_adapter_doctor(result))
        return 0 if result.ok else 2
    if args.command == "status":
        result = doctor_automation(args.name, repo_root)
        payload = _status_payload(result)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_status(payload))
            _maybe_emit_automation_hint(args, repo_root, result)
        return 0
    if args.command == "adapter":
        if args.adapter_command == "list":
            adapters = [asdict(adapter) for adapter in list_adapters()]
            if args.format == "json":
                print(json.dumps(adapters, indent=2))
            else:
                print(_format_rows(adapters, "table"))
            return 0
        if args.adapter_command == "show":
            adapter = get_adapter(args.name)
            if args.format == "json":
                print(json.dumps(asdict(adapter), indent=2))
            else:
                print(_format_adapter(adapter))
            return 0
        if args.adapter_command == "doctor":
            result = doctor_adapter(args.name, repo_root)
            if args.format == "json":
                print(json.dumps(asdict(result), indent=2))
            else:
                print(_format_adapter_doctor(result))
            return 0 if result.ok else 2
        if args.adapter_command == "setup":
            try:
                result = setup_adapter(
                    args.name,
                    repo_root,
                    target=args.target,
                    print_only=args.print_only,
                    install_wrapper=args.install_wrapper,
                    install_direnv=args.install_direnv,
                )
            except AdapterError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if args.print_only:
                print(json.dumps(result.settings, indent=2, sort_keys=True))
            else:
                print(json.dumps(asdict(result), indent=2))
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


def _format_adapter(adapter) -> str:
    env_lines = [f"  {key}={value}" for key, value in sorted(adapter.env.items())]
    if not env_lines:
        env_lines = ["  none"]
    lines = [
        f"Adapter: {adapter.name}",
        f"Description: {adapter.description}",
        f"Default agent: {adapter.default_agent_id}",
        f"Default context: {adapter.default_with_context}",
        f"Native hooks: {adapter.native_hooks}",
        "Environment:",
        *env_lines,
        f"Setup: {adapter.setup_hint}",
    ]
    return "\n".join(lines)


def _format_adapter_doctor(result) -> str:
    lines = [
        f"Adapter: {result.adapter.name}",
        f"OK: {result.ok}",
        "Checks:",
    ]
    for check in result.checks:
        status = "ok" if check.ok else "fail"
        lines.append(f"- {check.name}: {status} ({check.detail})")
    next_steps = _doctor_next_steps(result)
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(lines)


def _doctor_next_steps(result) -> list[str]:
    checks = {check.name: check.ok for check in result.checks}
    if result.ok:
        return []
    if "automation" in checks and not checks["automation"]:
        return []
    if not checks.get("wrapper_file", True):
        return [f"ait bootstrap {result.adapter.name}"]
    real_binary_ok = checks.get("real_claude_binary", checks.get("real_agent_binary", True))
    if not real_binary_ok:
        binary = result.adapter.command_name or result.adapter.name
        return [f"install {binary} or put the real {binary} binary on PATH"]
    if not checks.get("path_wrapper_active", True):
        if checks.get("envrc_path", False) and checks.get("direnv_binary", False):
            return ["direnv allow", f'eval "$(ait bootstrap {result.adapter.name} --shell)"']
        return [f'eval "$(ait bootstrap {result.adapter.name} --shell)"']
    return []


def _status_payload(result) -> dict[str, object]:
    checks = {check.name: check.ok for check in result.checks}
    return {
        "adapter": result.adapter.name,
        "ok": result.ok,
        "git_repo": checks.get("git_repo", False),
        "wrapper_installed": checks.get("wrapper_file", False),
        "path_wrapper_active": checks.get("path_wrapper_active", False),
        "real_claude_binary": checks.get("real_claude_binary", False),
        "real_agent_binary": checks.get("real_agent_binary", checks.get("real_claude_binary", False)),
        "direnv_available": checks.get("direnv_binary", False),
        "direnv_loaded": checks.get("direnv_env_loaded", False),
        "next_steps": _doctor_next_steps(result),
    }


def _format_status(payload: dict[str, object]) -> str:
    binary_label = "Real Claude binary" if payload["adapter"] == "claude-code" else "Real agent binary"
    lines = [
        f"Adapter: {payload['adapter']}",
        f"OK: {payload['ok']}",
        f"Git repo: {payload['git_repo']}",
        f"Wrapper installed: {payload['wrapper_installed']}",
        f"PATH uses wrapper: {payload['path_wrapper_active']}",
        f"{binary_label}: {payload['real_agent_binary']}",
        f"direnv available: {payload['direnv_available']}",
        f"direnv loaded: {payload['direnv_loaded']}",
    ]
    next_steps = payload.get("next_steps", [])
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(lines)


def _maybe_emit_automation_hint(args, repo_root: Path, result) -> None:
    if args.no_hints or result.ok:
        return
    hint_key = (
        "claude_code_automation_hint_v1"
        if result.adapter.name == "claude-code"
        else f"{result.adapter.name}_automation_hint_v1"
    )
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        return
    hints_path = root / ".ait" / "hints.json"
    hints = _read_hints(hints_path)
    if hints.get(hint_key):
        return
    next_steps = _doctor_next_steps(result)
    install_step = next((step for step in next_steps if step.startswith("install ")), None)
    if install_step is not None:
        hint = f"ait hint: {install_step}."
    elif result.adapter.name == "claude-code":
        hint = 'ait hint: run eval "$(ait doctor --fix)" to enable Claude Code automation in this repo.'
    else:
        hint = f'ait hint: run eval "$(ait doctor {result.adapter.name} --fix)" to enable automation in this repo.'
    print(hint, file=sys.stderr)
    hints[hint_key] = True
    _write_hints(hints_path, hints)


def _read_hints(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_hints(path: Path, hints: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hints, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _format_bootstrap(result) -> str:
    lines = [
        f"Adapter: {result.adapter.name}",
        f"OK: {result.ok}",
        "Wrote:",
    ]
    lines.extend(f"- {path}" for path in result.setup.wrote_files)
    if result.next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in result.next_steps)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
