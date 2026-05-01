from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
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
    if parser is not None:
        parser.print_help()
    return 1
