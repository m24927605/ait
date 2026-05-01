from __future__ import annotations

from pathlib import Path

from ait.cli_parser import build_parser

from . import adapter, attempt, daemon, graph, init, intent, memory, query, reconcile, run, shell, upgrade

_HANDLERS = {
    "adapter": adapter.handle,
    "attempt": attempt.handle,
    "bootstrap": init.handle,
    "context": run.handle,
    "daemon": daemon.handle,
    "doctor": init.handle,
    "enable": init.handle,
    "graph": graph.handle,
    "init": init.handle,
    "intent": intent.handle,
    "memory": memory.handle,
    "query": query.handle,
    "blame": query.handle,
    "reconcile": reconcile.handle,
    "repair": init.handle,
    "run": run.handle,
    "shell": shell.handle,
    "status": init.handle,
    "upgrade": upgrade.handle,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, Path.cwd(), parser)
