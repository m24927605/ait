from __future__ import annotations

from ._shared import *

from ait.next_action import format_next_action_text, plan_next_action


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    result = plan_next_action(repo_root, target_branch=getattr(args, "to", None))
    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_next_action_text(result, explain=args.explain))
    return 0 if not result.blocking_reasons else 1
