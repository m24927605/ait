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
    enable_available_adapters,
    get_adapter,
    list_adapters,
    setup_adapter,
)
from ait.brain import (
    build_auto_briefing_query,
    build_auto_repo_brain_briefing,
    build_repo_brain_briefing,
    build_repo_brain,
    query_repo_brain,
    render_repo_brain_briefing,
    render_brain_query_results,
    render_repo_brain_text,
    write_repo_brain,
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
    agent_memory_status,
    build_relevant_memory_recall,
    build_repo_memory,
    ensure_agent_memory_imported,
    import_agent_memory,
    lint_memory_notes,
    list_memory_notes,
    memory_health_from_lint,
    remove_memory_note,
    render_repo_memory_text,
    render_relevant_memory_recall,
    render_memory_search_results,
    render_memory_lint_result,
    search_repo_memory,
)
from ait.memory_policy import init_memory_policy, load_memory_policy
from ait.query import blame_path, execute_query, list_shortcut_expression, parse_blame_target
from ait.reconcile import reconcile_repo
from ait.repo import resolve_repo_root
from ait.runner import run_agent_command
from ait.shell_integration import (
    ShellIntegrationError,
    install_shell_integration,
    shell_snippet,
    uninstall_shell_integration,
)
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

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument(
        "--adapter",
        choices=tuple(name for name in sorted(ADAPTERS) if name != "shell"),
        action="append",
        dest="init_adapters",
    )
    init_parser.add_argument("--format", choices=("text", "json"), default="text")
    init_parser.add_argument("--shell", action="store_true")
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
    run_parser.add_argument("--no-auto-commit", action="store_true")
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
    memory_recall = memory_subparsers.add_parser("recall")
    memory_recall.add_argument("query", nargs="?")
    memory_recall.add_argument("--auto", action="store_true")
    memory_recall.add_argument("--agent")
    memory_recall.add_argument("--kind")
    memory_recall.add_argument("--description")
    memory_recall.add_argument("--command-text")
    memory_recall.add_argument("--limit", type=int, default=6)
    memory_recall.add_argument("--budget-chars", type=int, default=4000)
    memory_recall.add_argument("--include-unhealthy", action="store_true")
    memory_recall.add_argument("--format", choices=("text", "json"), default="text")
    memory_lint = memory_subparsers.add_parser("lint")
    memory_lint.add_argument("--fix", action="store_true")
    memory_lint.add_argument("--max-chars", type=int, default=6000)
    memory_lint.add_argument("--format", choices=("text", "json"), default="text")
    memory_import = memory_subparsers.add_parser("import")
    memory_import.add_argument("--source", default="auto")
    memory_import.add_argument("--path", action="append", dest="import_paths")
    memory_import.add_argument("--topic", default="agent-memory")
    memory_import.add_argument("--max-chars", type=int, default=6000)
    memory_import.add_argument("--format", choices=("text", "json"), default="text")
    memory_graph = memory_subparsers.add_parser("graph")
    memory_graph_subparsers = memory_graph.add_subparsers(dest="memory_graph_command")
    memory_graph_build = memory_graph_subparsers.add_parser("build")
    memory_graph_build.add_argument("--format", choices=("text", "json"), default="text")
    memory_graph_show = memory_graph_subparsers.add_parser("show")
    memory_graph_show.add_argument("--format", choices=("text", "json"), default="text")
    memory_graph_show.add_argument("--budget-chars", type=int)
    memory_graph_query = memory_graph_subparsers.add_parser("query")
    memory_graph_query.add_argument("query")
    memory_graph_query.add_argument("--limit", type=int, default=8)
    memory_graph_query.add_argument("--format", choices=("text", "json"), default="text")
    memory_graph_brief = memory_graph_subparsers.add_parser("brief")
    memory_graph_brief.add_argument("query", nargs="?")
    memory_graph_brief.add_argument("--auto", action="store_true")
    memory_graph_brief.add_argument("--explain", action="store_true")
    memory_graph_brief.add_argument("--agent")
    memory_graph_brief.add_argument("--kind")
    memory_graph_brief.add_argument("--description")
    memory_graph_brief.add_argument("--command-text")
    memory_graph_brief.add_argument("--limit", type=int, default=6)
    memory_graph_brief.add_argument("--budget-chars", type=int, default=5000)
    memory_graph_brief.add_argument("--format", choices=("text", "json"), default="text")
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
    doctor_parser.add_argument("name", choices=tuple(sorted(ADAPTERS)), nargs="?")
    doctor_parser.add_argument("--format", choices=("text", "json"), default="text")
    doctor_parser.add_argument("--fix", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("name", choices=tuple(sorted(ADAPTERS)), nargs="?", default="claude-code")
    status_parser.add_argument("--format", choices=("text", "json"), default="text")
    status_parser.add_argument("--all", action="store_true", dest="all_adapters")

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument(
        "name",
        choices=tuple(name for name in sorted(ADAPTERS) if name != "shell"),
        nargs="?",
    )
    repair_parser.add_argument("--format", choices=("text", "json"), default="text")

    enable_parser = subparsers.add_parser("enable")
    enable_parser.add_argument(
        "--adapter",
        choices=tuple(name for name in sorted(ADAPTERS) if name != "shell"),
        action="append",
        dest="enable_adapters",
    )
    enable_parser.add_argument("--format", choices=("text", "json"), default="text")
    enable_parser.add_argument("--shell", action="store_true")

    shell_parser = subparsers.add_parser("shell")
    shell_subparsers = shell_parser.add_subparsers(dest="shell_command")
    shell_show = shell_subparsers.add_parser("show")
    shell_show.add_argument("--shell", choices=("zsh", "bash"), default="zsh")
    shell_install = shell_subparsers.add_parser("install")
    shell_install.add_argument("--shell", choices=("zsh", "bash"))
    shell_install.add_argument("--rc-path")
    shell_install.add_argument("--format", choices=("text", "json"), default="text")
    shell_uninstall = shell_subparsers.add_parser("uninstall")
    shell_uninstall.add_argument("--shell", choices=("zsh", "bash"))
    shell_uninstall.add_argument("--rc-path")
    shell_uninstall.add_argument("--format", choices=("text", "json"), default="text")

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
        try:
            automation = enable_available_adapters(
                result.repo_root,
                names=tuple(args.init_adapters) if args.init_adapters else None,
            )
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.shell:
            if automation.shell_snippet:
                print(automation.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        memory_import = ensure_agent_memory_imported(result.repo_root)
        memory_policy = init_memory_policy(result.repo_root)
        statuses = tuple(
            doctor_automation(item.adapter.name, result.repo_root)
            for item in automation.installed
        )
        payload = _init_payload(result, automation, statuses, memory_import, memory_policy)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_init(payload))
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
                auto_commit=not args.no_auto_commit,
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
        if args.memory_command == "graph":
            if args.memory_graph_command == "build":
                brain = write_repo_brain(repo_root)
                if args.format == "json":
                    print(json.dumps(brain.to_dict(), indent=2))
                else:
                    print(f"wrote {Path(brain.repo_root) / '.ait' / 'brain' / 'graph.json'}")
                    print(f"wrote {Path(brain.repo_root) / '.ait' / 'brain' / 'REPORT.md'}")
                return 0
            if args.memory_graph_command == "show":
                brain = build_repo_brain(repo_root)
                if args.format == "json":
                    print(json.dumps(brain.to_dict(), indent=2))
                else:
                    print(render_repo_brain_text(brain, budget_chars=args.budget_chars), end="")
                return 0
            if args.memory_graph_command == "query":
                try:
                    results = query_repo_brain(repo_root, args.query, limit=args.limit)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                if args.format == "json":
                    print(json.dumps([result.to_dict() for result in results], indent=2))
                else:
                    print(render_brain_query_results(results), end="")
                return 0
            if args.memory_graph_command == "brief":
                try:
                    if args.auto:
                        briefing = build_auto_repo_brain_briefing(
                            repo_root,
                            intent_title=args.query,
                            description=args.description,
                            kind=args.kind,
                            command=tuple(args.command_text.split()) if args.command_text else (),
                            agent_id=args.agent,
                            limit=args.limit,
                        )
                    elif args.query:
                        briefing = build_repo_brain_briefing(repo_root, args.query, limit=args.limit)
                    else:
                        print("error: memory graph brief requires a query or --auto", file=sys.stderr)
                        return 2
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                if args.format == "json":
                    print(json.dumps(briefing.to_dict(), indent=2))
                else:
                    print(render_repo_brain_briefing(briefing, budget_chars=args.budget_chars), end="")
                    if args.explain and not args.auto:
                        print("Briefing query used manual query input.")
                return 0
            print("error: memory graph requires a subcommand: build, show, query, or brief", file=sys.stderr)
            return 2
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
        if args.memory_command == "recall":
            if args.auto:
                auto_query = build_auto_briefing_query(
                    repo_root,
                    intent_title=args.query or "",
                    description=args.description,
                    kind=args.kind,
                    command=tuple(args.command_text.split()) if args.command_text else (),
                    agent_id=args.agent,
                )
                query = auto_query.query
                sources = [asdict(source) for source in auto_query.sources]
            elif args.query:
                query = args.query
                sources = ["manual query input"]
            else:
                print("error: memory recall requires a query or --auto", file=sys.stderr)
                return 2
            recall = build_relevant_memory_recall(
                repo_root,
                query,
                limit=args.limit,
                budget_chars=args.budget_chars,
                include_unhealthy=args.include_unhealthy,
            )
            payload = recall.to_dict()
            payload["query_sources"] = sources
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(render_relevant_memory_recall(recall), end="")
            return 0
        if args.memory_command == "lint":
            result = lint_memory_notes(
                repo_root,
                fix=args.fix,
                max_chars=args.max_chars,
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(render_memory_lint_result(result), end="")
            return 0 if not result.issues else 2
        if args.memory_command == "import":
            result = import_agent_memory(
                repo_root,
                source=args.source,
                paths=tuple(args.import_paths) if args.import_paths else (),
                topic=args.topic,
                max_chars=args.max_chars,
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(_format_memory_import(result))
            return 0 if result.imported else 2
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
                    print("Recall allowed sources:")
                    for pattern in policy.recall_source_allow:
                        print(f"- {pattern}")
                    print("Recall blocked sources:")
                    if policy.recall_source_block:
                        for pattern in policy.recall_source_block:
                            print(f"- {pattern}")
                    else:
                        print("- none")
                    print("Recall blocked lint severities:")
                    for severity in policy.recall_lint_block_severities:
                        print(f"- {severity}")
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
                init_result = init_repo(repo_root)
                result = enable_available_adapters(
                    init_result.repo_root,
                    names=(args.name,) if args.name else None,
                )
                memory_import = ensure_agent_memory_imported(init_result.repo_root)
                memory_policy = init_memory_policy(init_result.repo_root)
            except ValueError as exc:
                if args.format == "json":
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                try:
                    result = enable_available_adapters(
                        repo_root,
                        names=(args.name,) if args.name else None,
                    )
                    init_memory_policy(repo_root)
                except AdapterError as adapter_exc:
                    print(f"error: {adapter_exc}", file=sys.stderr)
                    return 2
                if result.shell_snippet:
                    print(result.shell_snippet)
                    return 0
                print("error: no supported agent binaries found on PATH", file=sys.stderr)
                return 2
            except AdapterError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            statuses = tuple(
                doctor_automation(item.adapter.name, init_result.repo_root)
                for item in result.installed
            )
            if args.format == "json":
                payload = _init_payload(init_result, result, statuses, memory_import, memory_policy)
                print(json.dumps(payload, indent=2))
                return 0 if result.installed else 2
            if result.shell_snippet:
                print(result.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        result = doctor_automation(args.name or "claude-code", repo_root)
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_adapter_doctor(result))
        return 0 if result.ok else 2
    if args.command == "status":
        if args.all_adapters:
            results = tuple(
                doctor_automation(name, repo_root)
                for name in sorted(ADAPTERS)
                if name != "shell"
            )
            memory_status = _memory_status_payload(repo_root)
            payload = [_status_payload(result, memory_status=memory_status) for result in results]
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(_format_status_all(payload))
                _maybe_emit_status_all_hint(args, repo_root, results)
            return 0
        result = doctor_automation(args.name, repo_root)
        payload = _status_payload(result, memory_status=_memory_status_payload(repo_root))
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_status(payload))
            _maybe_emit_automation_hint(args, repo_root, result)
        return 0
    if args.command == "repair":
        names = (args.name,) if args.name else tuple(name for name in sorted(ADAPTERS) if name != "shell")
        before = tuple(doctor_automation(name, repo_root) for name in names)
        try:
            init_result = init_repo(repo_root)
            result = enable_available_adapters(init_result.repo_root, names=names)
            memory_import = ensure_agent_memory_imported(init_result.repo_root)
            memory_lint = lint_memory_notes(init_result.repo_root, fix=True)
            memory_health_lint = lint_memory_notes(init_result.repo_root)
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        after = tuple(doctor_automation(name, init_result.repo_root) for name in names)
        payload = _repair_payload(before, result, after, memory_import, memory_lint, memory_health_lint)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_repair(payload))
        return 0 if result.installed or memory_lint.fixes else 2
    if args.command == "enable":
        try:
            result = enable_available_adapters(
                repo_root,
                names=tuple(args.enable_adapters) if args.enable_adapters else None,
            )
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.shell:
            if result.shell_snippet:
                print(result.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_auto_enable(result))
        return 0 if result.ok else 2
    if args.command == "shell":
        try:
            if args.shell_command == "show":
                print(shell_snippet(args.shell), end="")
                return 0
            if args.shell_command == "install":
                result = install_shell_integration(shell=args.shell, rc_path=args.rc_path)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_shell_integration("installed", result))
                return 0
            if args.shell_command == "uninstall":
                result = uninstall_shell_integration(shell=args.shell, rc_path=args.rc_path)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_shell_integration("removed", result))
                return 0
        except ShellIntegrationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
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


def _format_auto_enable(result) -> str:
    lines = ["AIT Agent Automation"]
    if result.installed:
        lines.append("Enabled:")
        for item in result.installed:
            wrapper_path = item.setup.wrapper_path or ""
            lines.append(f"- {item.adapter.name}: {wrapper_path}")
    else:
        lines.append("Enabled: none")
    if result.skipped:
        lines.append("Skipped:")
        for item in result.skipped:
            lines.append(f"- {item.name}: {item.detail}")
    if result.shell_snippet:
        lines.append("Current shell:")
        lines.append(f'- eval "$(ait enable --shell)"')
        lines.append("Next:")
        for item in result.installed:
            command = item.adapter.command_name
            if command:
                lines.append(f"- {command} ...")
    return "\n".join(lines)


def _format_memory_import(result) -> str:
    lines = ["AIT memory import"]
    if result.imported:
        lines.append("Imported:")
        for note in result.imported:
            lines.append(f"- {note.id} topic={note.topic or 'general'} source={note.source}")
    else:
        lines.append("Imported: none")
    if result.skipped:
        lines.append("Skipped:")
        for item in result.skipped:
            lines.append(f"- {item.get('path')}: {item.get('reason')} ({item.get('source')})")
    return "\n".join(lines)


def _init_payload(init_result, automation, statuses, memory_import=None, memory_policy=None) -> dict[str, object]:
    status_payloads = [_status_payload(status) for status in statuses]
    payload = {
        "repo_root": str(init_result.repo_root),
        "ait_dir": str(init_result.ait_dir),
        "db_path": str(init_result.db_path),
        "repo_id": init_result.repo_id,
        "socket_path": str(init_result.socket_path),
        "installed_adapters": [item.adapter.name for item in automation.installed],
        "skipped_adapters": [asdict(item) for item in automation.skipped],
        "shell_snippet": automation.shell_snippet,
        "ready_adapters": [item["adapter"] for item in status_payloads if item["ok"]],
        "status": status_payloads,
    }
    if memory_import is not None:
        payload["memory_import"] = memory_import.to_dict()
    if memory_policy is not None:
        payload["memory_policy"] = memory_policy.to_dict()
    return payload


def _format_init(payload: dict[str, object]) -> str:
    installed = [str(item) for item in payload.get("installed_adapters", [])]
    skipped = payload.get("skipped_adapters", [])
    ready = [str(item) for item in payload.get("ready_adapters", [])]
    statuses = [item for item in payload.get("status", []) if isinstance(item, dict)]
    lines = [
        "AIT initialized",
        f"Repo: {payload['repo_root']}",
        f"State: {payload['ait_dir']}",
    ]
    if installed:
        lines.append("Agent wrappers:")
        lines.extend(f"- {name}" for name in installed)
    else:
        lines.append("Agent wrappers: none")
    if skipped:
        lines.append("Skipped:")
        for item in skipped:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}: {item.get('detail')}")
    memory_import = payload.get("memory_import")
    if isinstance(memory_import, dict):
        imported = memory_import.get("imported", [])
        memory_skipped = memory_import.get("skipped", [])
        if imported:
            lines.append("Imported memory:")
            for item in imported:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('source')}")
        elif memory_skipped:
            lines.append("Imported memory: none")
    memory_policy = payload.get("memory_policy")
    if isinstance(memory_policy, dict):
        state = "created" if memory_policy.get("created") else "already current"
        lines.append(f"Memory policy: {state}")
    if ready:
        lines.append("Ready now:")
        lines.extend(f"- {name}" for name in ready)
    elif payload.get("shell_snippet"):
        if any(item.get("direnv_available") and not item.get("direnv_loaded") for item in statuses):
            lines.extend(
                [
                    "Current shell:",
                    "- direnv allow",
                    "After that:",
                ]
            )
        else:
            lines.extend(
                [
                    "Current shell:",
                    '- eval "$(ait init --shell)"',
                    "After that:",
                ]
            )
        lines.extend(f"- {name.split('-')[0] if name == 'claude-code' else name} ..." for name in installed)
    else:
        lines.extend(
            [
                "Current shell: no supported agent CLI found on PATH",
                "Next:",
                "- install claude, codex, aider, gemini, or cursor, then run ait init",
            ]
        )
    return "\n".join(lines)


def _repair_payload(
    before,
    result,
    after,
    memory_import=None,
    memory_lint=None,
    memory_health_lint=None,
) -> dict[str, object]:
    before_payload = [_status_payload(item) for item in before]
    after_payload = [_status_payload(item) for item in after]
    before_by_adapter = {str(item["adapter"]): item for item in before_payload}
    changes: list[dict[str, object]] = []
    for item in after_payload:
        adapter = str(item["adapter"])
        previous = before_by_adapter.get(adapter, {})
        changed_fields = {
            key: {"before": previous.get(key), "after": item.get(key)}
            for key in (
                "ok",
                "wrapper_installed",
                "path_wrapper_active",
                "real_agent_binary",
                "direnv_loaded",
            )
            if previous.get(key) != item.get(key)
        }
        changes.append({"adapter": adapter, "changed": changed_fields})
    payload = {
        "before": before_payload,
        "after": after_payload,
        "installed_adapters": [item.adapter.name for item in result.installed],
        "skipped_adapters": [asdict(item) for item in result.skipped],
        "shell_snippet": result.shell_snippet,
        "changes": changes,
    }
    if memory_import is not None:
        payload["memory_import"] = memory_import.to_dict()
    if memory_lint is not None:
        payload["memory_lint"] = memory_lint.to_dict()
        payload["memory_health"] = memory_health_from_lint(memory_health_lint or memory_lint).to_dict()
    return payload


def _format_repair(payload: dict[str, object]) -> str:
    lines = ["AIT repair"]
    installed = [str(item) for item in payload.get("installed_adapters", [])]
    if installed:
        lines.append("Repaired:")
        lines.extend(f"- {name}" for name in installed)
    else:
        lines.append("Repaired: none")
    skipped = payload.get("skipped_adapters", [])
    if skipped:
        lines.append("Skipped:")
        for item in skipped:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}: {item.get('detail')}")
    memory_import = payload.get("memory_import")
    if isinstance(memory_import, dict):
        imported = memory_import.get("imported", [])
        if imported:
            lines.append("Imported memory:")
            for item in imported:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('source')}")
        else:
            lines.append("Imported memory: already current")
    memory_lint = payload.get("memory_lint")
    memory_health = payload.get("memory_health")
    if isinstance(memory_lint, dict):
        health_status = memory_health.get("status") if isinstance(memory_health, dict) else "unknown"
        lines.append(f"Memory health: {health_status}")
        lines.append(
            "Memory lint: "
            f"issues={memory_lint.get('issue_count', 0)} fixes={memory_lint.get('fix_count', 0)}"
        )
        fixes = memory_lint.get("fixes", [])
        if fixes:
            lines.append("Memory lint fixes:")
            for item in fixes:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('action')} note={item.get('note_id')}: {item.get('detail')}")
    changes = payload.get("changes", [])
    if changes:
        lines.append("Status changes:")
        for item in changes:
            if not isinstance(item, dict):
                continue
            changed = item.get("changed", {})
            if not changed:
                lines.append(f"- {item.get('adapter')}: no status change")
                continue
            parts = []
            if isinstance(changed, dict):
                for key, values in changed.items():
                    if isinstance(values, dict):
                        parts.append(f"{key}: {values.get('before')} -> {values.get('after')}")
            lines.append(f"- {item.get('adapter')}: " + ", ".join(parts))
    if payload.get("shell_snippet"):
        lines.extend(
            [
                "Current shell:",
                '- eval "$(ait init --shell)"',
            ]
        )
    return "\n".join(lines)


def _format_shell_integration(action: str, result) -> str:
    state = "changed" if result.changed else "already current"
    lines = [
        f"Shell: {result.shell}",
        f"RC file: {result.rc_path}",
        f"Action: {action}",
        f"State: {state}",
    ]
    if action == "installed":
        lines.extend(
            [
                "Next:",
                f"- reload {result.rc_path} or open a new terminal",
                "- run ait doctor --fix once in each repo that should get wrappers",
            ]
        )
    return "\n".join(lines)


def _doctor_next_steps(result) -> list[str]:
    checks = {check.name: check.ok for check in result.checks}
    if result.ok:
        return []
    if "automation" in checks and not checks["automation"]:
        return []
    if not checks.get("wrapper_file", True):
        return [f"ait init --adapter {result.adapter.name}"]
    real_binary_ok = checks.get("real_claude_binary", checks.get("real_agent_binary", True))
    if not real_binary_ok:
        binary = result.adapter.command_name or result.adapter.name
        return [f"install {binary} or put the real {binary} binary on PATH"]
    if not checks.get("path_wrapper_active", True):
        if checks.get("envrc_path", False) and checks.get("direnv_binary", False):
            return ["direnv allow", 'eval "$(ait init --shell)"']
        return ['eval "$(ait init --shell)"']
    return []


def _agent_cli_message(payload: dict[str, object]) -> str:
    adapter = str(payload["adapter"])
    command = _agent_command_name(adapter)
    if payload["ok"]:
        return f"ready: run {command} ..."
    if not payload["real_agent_binary"]:
        return f"not ready: install {command} or put the real {command} binary on PATH"
    if not payload["wrapper_installed"]:
        return f"not ready: run ait init --adapter {adapter}"
    if not payload["path_wrapper_active"]:
        if payload["direnv_available"]:
            return f"not ready in this shell: run direnv allow once, then run {command} ..."
        return f"not ready in this shell: run eval \"$(ait init --shell)\", then run {command} ..."
    return "not ready: inspect next_steps"


def _memory_status_payload(repo_root: Path) -> dict[str, object]:
    try:
        status = agent_memory_status(repo_root).to_dict()
        state_db_path = repo_root / ".ait" / "state.sqlite3"
        if state_db_path.exists():
            lint_result = lint_memory_notes(repo_root)
            health = memory_health_from_lint(lint_result)
            status.update(
                {
                    "health": health.status,
                    "lint_checked": health.checked,
                    "lint_issue_count": health.issue_count,
                    "lint_error_count": health.error_count,
                    "lint_warning_count": health.warning_count,
                    "lint_info_count": health.info_count,
                }
            )
        else:
            health = "ok" if status.get("initialized") else "uninitialized"
            status.update(
                {
                    "health": health,
                    "lint_checked": 0,
                    "lint_issue_count": 0,
                    "lint_error_count": 0,
                    "lint_warning_count": 0,
                    "lint_info_count": 0,
                }
            )
        return status
    except ValueError:
        return {
            "initialized": False,
            "imported_sources": [],
            "candidate_paths": [],
            "pending_paths": [],
            "state_path": "",
            "health": "unavailable",
            "lint_checked": 0,
            "lint_issue_count": 0,
            "lint_error_count": 0,
            "lint_warning_count": 0,
            "lint_info_count": 0,
        }


def _status_payload(result, *, memory_status: dict[str, object] | None = None) -> dict[str, object]:
    checks = {check.name: check.ok for check in result.checks}
    payload = {
        "adapter": result.adapter.name,
        "ok": result.ok,
        "git_repo": checks.get("git_repo", False),
        "wrapper_installed": checks.get("wrapper_file", False),
        "path_wrapper_active": checks.get("path_wrapper_active", False),
        "real_claude_binary": checks.get("real_claude_binary", False),
        "real_agent_binary": checks.get("real_agent_binary", checks.get("real_claude_binary", False)),
        "direnv_available": checks.get("direnv_binary", False),
        "direnv_loaded": checks.get("direnv_env_loaded", False),
        "memory": memory_status or {},
        "next_steps": _doctor_next_steps(result),
    }
    payload["agent_cli_ready"] = payload["ok"]
    payload["agent_cli_message"] = _agent_cli_message(payload)
    return payload


def _format_status(payload: dict[str, object]) -> str:
    binary_label = "Real Claude binary" if payload["adapter"] == "claude-code" else "Real agent binary"
    lines = [
        f"Agent CLI: {_agent_cli_summary(payload)}",
        f"Adapter: {payload['adapter']}",
        f"OK: {payload['ok']}",
        f"Git repo: {payload['git_repo']}",
        f"Wrapper installed: {payload['wrapper_installed']}",
        f"PATH uses wrapper: {payload['path_wrapper_active']}",
        f"{binary_label}: {payload['real_agent_binary']}",
        f"direnv available: {payload['direnv_available']}",
        f"direnv loaded: {payload['direnv_loaded']}",
        f"Agent CLI ready: {payload['agent_cli_ready']}",
        f"Agent CLI detail: {payload['agent_cli_message']}",
    ]
    memory = payload.get("memory", {})
    if isinstance(memory, dict):
        imported = memory.get("imported_sources", [])
        pending = memory.get("pending_paths", [])
        lines.append(f"Memory initialized: {memory.get('initialized', False)}")
        lines.append(f"Memory health: {memory.get('health', 'unknown')}")
        lines.append(
            "Memory lint issues: "
            f"{memory.get('lint_issue_count', 0)} "
            f"(errors={memory.get('lint_error_count', 0)}, "
            f"warnings={memory.get('lint_warning_count', 0)}, "
            f"info={memory.get('lint_info_count', 0)})"
        )
        lines.append(f"Memory imported sources: {len(imported) if isinstance(imported, list) else 0}")
        if pending:
            lines.append("Memory pending:")
            lines.extend(f"- {path}" for path in pending)
    next_steps = payload.get("next_steps", [])
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(lines)


def _agent_cli_summary(payload: dict[str, object]) -> str:
    adapter = str(payload["adapter"])
    command = _agent_command_name(adapter)
    if payload["agent_cli_ready"]:
        return f"ready, run {command} ..."
    if not payload["real_agent_binary"]:
        return f"install {command}"
    if not payload["wrapper_installed"]:
        return f"run ait init --adapter {adapter}"
    if not payload["path_wrapper_active"]:
        if payload["direnv_available"]:
            return "run direnv allow once"
        return 'run eval "$(ait init --shell)"'
    return "not ready, inspect JSON status"


def _format_status_all(payload: list[dict[str, object]]) -> str:
    lines = ["AIT Agent CLI Readiness"]
    for item in payload:
        command = _agent_command_name(str(item["adapter"]))
        lines.append(
            f"- {command}: {_agent_cli_summary(item)}"
        )
        lines.append(
            "  details: "
            f"adapter={item['adapter']} "
            f"wrapper={item['wrapper_installed']} "
            f"path={item['path_wrapper_active']} "
            f"real_binary={item['real_agent_binary']} "
            f"memory={item.get('memory', {}).get('initialized', False) if isinstance(item.get('memory'), dict) else False} "
            f"memory_health={item.get('memory', {}).get('health', 'unknown') if isinstance(item.get('memory'), dict) else 'unknown'}"
        )
        next_steps = item.get("next_steps", [])
        if next_steps:
            lines.append(f"  next: {', '.join(str(step) for step in next_steps)}")
    return "\n".join(lines)


def _agent_command_name(adapter: str) -> str:
    return "claude" if adapter == "claude-code" else adapter


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
    else:
        hint = "ait hint: run ait init once to enable detected agent automation in this repo."
    print(hint, file=sys.stderr)
    hints[hint_key] = True
    _write_hints(hints_path, hints)


def _maybe_emit_status_all_hint(args, repo_root: Path, results) -> None:
    results = tuple(results)
    if args.no_hints or all(result.ok for result in results):
        return
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        return
    hints_path = root / ".ait" / "hints.json"
    hints = _read_hints(hints_path)
    hint_key = "all_agent_automation_hint_v1"
    if hints.get(hint_key):
        return
    missing_real = [
        result.adapter.command_name
        for result in results
        if result.adapter.command_name
        and not _status_payload(result)["real_agent_binary"]
    ]
    if missing_real and len(missing_real) == len(results):
        hint = "ait hint: install an agent CLI such as claude, codex, aider, gemini, or cursor first."
    else:
        hint = "ait hint: run ait init once to enable detected agent automation in this repo."
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
