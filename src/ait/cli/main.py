from __future__ import annotations

from pathlib import Path
import sys

from ait.cli_parser import build_parser

from . import (
    adapter,
    apply,
    attempt,
    bug_report,
    cleanup,
    config,
    console,
    continue_cmd,
    daemon,
    demo,
    dev,
    graph,
    init,
    intent,
    memory,
    merge,
    metadata,
    next,
    policy,
    query,
    reconcile,
    recover,
    resume,
    review,
    run,
    session,
    shell,
    upgrade,
    whereami,
)

_HANDLERS = {
    "adapter": adapter.handle,
    "agent-continue": continue_cmd.handle,
    "bug-report": bug_report.handle,
    "apply": apply.handle,
    "attempt": attempt.handle,
    "bootstrap": init.handle,
    "context": run.handle,
    "daemon": daemon.handle,
    "demo": demo.handle,
    "dev": dev.handle,
    "doctor": init.handle,
    "enable": init.handle,
    "graph": graph.handle,
    "init": init.handle,
    "intent": intent.handle,
    "memory": memory.handle,
    "merge": merge.handle,
    "metadata": metadata.handle,
    "next": next.handle,
    "policy": policy.handle,
    "query": query.handle,
    "blame": query.handle,
    "cleanup": cleanup.handle,
    "console": console.handle,
    "config": config.handle,
    "continue": continue_cmd.handle,
    "reconcile": reconcile.handle,
    "recover": recover.handle,
    "resume": resume.handle,
    "review": review.handle,
    "repair": init.handle,
    "run": run.handle,
    "session": session.handle,
    "shell": shell.handle,
    "status": init.handle,
    "upgrade": upgrade.handle,
    "whereami": whereami.handle,
}


def main() -> int:
    try:
        parser = build_parser()
        args = parser.parse_args()
        if getattr(args, "json", False) or "--json" in sys.argv[1:]:
            args.format = "json"
        handler = _HANDLERS.get(args.command)
        if handler is None:
            parser.print_help()
            return 1
        return handler(args, Path.cwd(), parser)
    except KeyboardInterrupt:
        return 130
