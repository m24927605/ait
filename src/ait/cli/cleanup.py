from __future__ import annotations

from ._shared import *

from ait.cleanup import CleanupError, cleanup_policy_from_config, cleanup_repo
from ait.cli.cleanup_helpers import _cleanup_payload, _format_cleanup


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        policy = cleanup_policy_from_config(
            repo_root,
            apply=args.apply,
            force=args.force,
            older_than_days=args.older_than,
            include_orphans=True if args.include_orphans else None,
            worktrees=args.worktrees,
            artifacts=args.artifacts,
        )
        report = cleanup_repo(repo_root, policy)
    except CleanupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = _cleanup_payload(report)
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_cleanup(report))

    return 1 if any(item.error for item in report.items) else 0
