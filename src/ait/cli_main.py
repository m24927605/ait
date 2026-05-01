from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

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
from ait.daemon import daemon_status, prune_daemon, serve_daemon, start_daemon, stop_daemon
from ait.db import (
    connect_db,
    get_memory_fact,
    list_memory_facts,
    list_memory_retrieval_events,
    run_migrations,
)
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
from ait.memory_eval import evaluate_memory_retrievals, render_memory_eval_report
from ait.memory_policy import init_memory_policy, load_memory_policy
from ait.query import QueryError, blame_path, execute_query, list_shortcut_expression, parse_blame_target
from ait.reconcile import reconcile_repo
from ait.report import build_work_graph, render_work_graph_text, write_work_graph_html
from ait.repo import resolve_repo_root
from ait.runner import run_agent_command
from ait.shell_integration import (
    ShellIntegrationError,
    install_shell_integration,
    shell_snippet,
    uninstall_shell_integration,
)
from ait.workspace import WorkspaceError
from ait.cli_parser import build_parser
from ait.cli_installation import (
    _classify_ait_source,
    _format_installation_alert_lines,
    _format_installation_lines,
    _format_upgrade,
    _installation_next_steps,
    _installation_payload,
    package_version,
)
from ait.cli_helpers import (
    _agent_cli_message,
    _agent_cli_summary,
    _agent_command_name,
    _ait_health_payload,
    _daemon_status_payload,
    _doctor_next_steps,
    _format_adapter,
    _format_adapter_doctor,
    _format_auto_enable,
    _format_bootstrap,
    _format_daemon_lines,
    _format_init,
    _format_memory_facts,
    _format_memory_import,
    _format_memory_retrievals,
    _format_rows,
    _format_repair,
    _format_run_result,
    _format_shell_integration,
    _format_status,
    _format_status_all,
    _init_payload,
    _maybe_emit_automation_hint,
    _maybe_emit_status_all_hint,
    _memory_eval_next_steps,
    _memory_status_payload,
    _read_hints,
    _repair_payload,
    _report_status_payload,
    _run_query_command,
    _status_payload,
    _write_hints,
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path.cwd()

    if args.command == "init":
        result = init_repo(repo_root, auto_git_init=True)
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
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_run_result(result), file=sys.stderr)
        return result.exit_code
    if args.command == "context":
        context = build_agent_context(repo_root, intent_id=args.intent_id)
        if args.format == "json":
            print(json.dumps(asdict(context), indent=2))
        else:
            print(render_agent_context_text(context), end="")
        return 0
    if args.command == "memory":
        if args.memory_command == "facts":
            root = resolve_repo_root(repo_root)
            conn = connect_db(root / ".ait" / "state.sqlite3")
            try:
                run_migrations(conn)
                facts = list_memory_facts(
                    conn,
                    status=args.status,
                    kind=args.kind,
                    topic=args.topic,
                    include_superseded=args.include_superseded,
                    limit=args.limit,
                )
            finally:
                conn.close()
            if args.format == "json":
                print(json.dumps([asdict(fact) for fact in facts], indent=2))
            else:
                print(_format_memory_facts(facts), end="")
            return 0
        if args.memory_command == "retrievals":
            if args.limit < 0:
                print("error: limit must be non-negative", file=sys.stderr)
                return 2
            root = resolve_repo_root(repo_root)
            conn = connect_db(root / ".ait" / "state.sqlite3")
            try:
                run_migrations(conn)
                events = list_memory_retrieval_events(
                    conn,
                    attempt_id=args.attempt,
                    limit=args.limit,
                )
                facts_by_id = {
                    fact_id: fact
                    for event in events
                    for fact_id in event.selected_fact_ids
                    for fact in [get_memory_fact(conn, fact_id)]
                    if fact is not None
                }
            finally:
                conn.close()
            if args.format == "json":
                print(
                    json.dumps(
                        [
                            {
                                **asdict(event),
                                "selected_facts": [
                                    asdict(facts_by_id[fact_id])
                                    for fact_id in event.selected_fact_ids
                                    if fact_id in facts_by_id
                                ],
                            }
                            for event in events
                        ],
                        indent=2,
                    )
                )
            else:
                print(_format_memory_retrievals(events, facts_by_id), end="")
            return 0
        if args.memory_command == "eval":
            try:
                report = evaluate_memory_retrievals(
                    repo_root,
                    attempt_id=args.attempt,
                    limit=args.limit,
                )
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if args.format == "json":
                print(json.dumps(report.to_dict(), indent=2))
            else:
                print(render_memory_eval_report(report), end="")
            return 1 if report.status == "fail" else 0
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
                init_result = init_repo(repo_root, auto_git_init=True)
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
        payload = asdict(result)
        payload["installation"] = _installation_payload()
        payload["daemon"] = _daemon_status_payload(repo_root)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_adapter_doctor(result, installation=payload["installation"], daemon=payload["daemon"]))
        return 0 if result.ok else 2
    if args.command == "status":
        if args.all_adapters:
            results = tuple(
                doctor_automation(name, repo_root)
                for name in sorted(ADAPTERS)
                if name != "shell"
            )
            memory_status = _memory_status_payload(repo_root)
            installation = _installation_payload()
            daemon = _daemon_status_payload(repo_root)
            payload = [
                _status_payload(
                    result,
                    memory_status=memory_status,
                    installation=installation,
                    daemon=daemon,
                )
                for result in results
            ]
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(_format_status_all(payload))
                _maybe_emit_status_all_hint(args, repo_root, results)
            return 0
        result = doctor_automation(args.name, repo_root)
        payload = _status_payload(
            result,
            memory_status=_memory_status_payload(repo_root),
            installation=_installation_payload(),
            daemon=_daemon_status_payload(repo_root),
        )
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_status(payload))
            _maybe_emit_automation_hint(args, repo_root, result)
        return 0
    if args.command == "upgrade":
        try:
            payload = _upgrade_payload(dry_run=args.dry_run, output_format=args.format)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_upgrade(payload))
        return int(payload.get("exit_code", 1))
    if args.command == "graph":
        try:
            graph = build_work_graph(
                repo_root,
                limit=args.limit,
                agent=args.agent,
                status=args.status,
                file_path=args.file_path,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.html:
            output_path = Path(args.output) if args.output else Path(graph["repo_root"]) / ".ait" / "report" / "graph.html"
            path = write_work_graph_html(graph, output_path)
            if args.format == "json":
                payload = dict(graph)
                payload["html_path"] = str(path)
                print(json.dumps(payload, indent=2))
            else:
                print(f"wrote {path}")
            return 0
        if args.format == "json":
            print(json.dumps(graph, indent=2))
        else:
            print(render_work_graph_text(graph))
        return 0
    if args.command == "repair":
        names = (args.name,) if args.name else tuple(name for name in sorted(ADAPTERS) if name != "shell")
        before = tuple(doctor_automation(name, repo_root) for name in names)
        try:
            init_result = init_repo(repo_root, auto_git_init=True)
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
        if args.daemon_command == "prune":
            status = prune_daemon(repo_root)
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


def _upgrade_payload(*, dry_run: bool, output_format: str) -> dict[str, object]:
    installation = _installation_payload()
    command = _upgrade_command(installation)
    payload: dict[str, object] = {
        "dry_run": dry_run,
        "source": installation.get("source", "unknown"),
        "current_version": installation.get("current_version", "unknown"),
        "command": command,
        "installation": installation,
    }
    if dry_run:
        payload.update({"exit_code": 0, "ran": False})
        return payload
    if output_format == "json":
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        payload.update(
            {
                "ran": True,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        return payload
    completed = subprocess.run(command, check=False)
    payload.update({"ran": True, "exit_code": completed.returncode})
    return payload


def _upgrade_command(installation: dict[str, object]) -> list[str]:
    source = str(installation.get("source") or "unknown")
    if source == "pipx":
        if shutil.which("pipx") is None:
            raise ValueError("pipx install detected, but pipx is not on PATH")
        return ["pipx", "upgrade", "ait-vcs"]
    if source == "npm":
        if shutil.which("npm") is None:
            raise ValueError("npm install detected, but npm is not on PATH")
        return ["npm", "install", "-g", "ait-vcs"]
    if source in {"venv", "python", "path"}:
        return [sys.executable, "-m", "pip", "install", "-U", "ait-vcs"]
    raise ValueError(
        f"unsupported ait install source for automatic upgrade: {source}; "
        "use pipx upgrade ait-vcs or python -m pip install -U ait-vcs"
    )


if __name__ == "__main__":
    raise SystemExit(main())
