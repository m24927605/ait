from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
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
    if parser is not None:
        parser.print_help()
    return 1
