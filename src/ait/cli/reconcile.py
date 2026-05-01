from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "reconcile":
        result = reconcile_repo(repo_root)
        print(json.dumps(asdict(result), indent=2))
        return 0
    if parser is not None:
        parser.print_help()
    return 1
