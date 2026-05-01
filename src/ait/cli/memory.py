from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
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
    if parser is not None:
        parser.print_help()
    return 1
