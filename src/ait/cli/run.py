from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
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
    if parser is not None:
        parser.print_help()
    return 1
