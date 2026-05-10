from __future__ import annotations

from ._shared import *

from ait.merge import MergeError, format_merge_text, merge_result


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        result = merge_result(
            repo_root,
            target_branch=args.to,
            mode=args.mode,
            dry_run=args.dry_run,
            push=args.push,
            set_default_branch=args.set_default_branch,
        )
    except MergeError as exc:
        from ait.agent_errors import emit_agent_error

        emit_agent_error(
            args.format,
            error_code="MERGE_FAILED",
            message=str(exc),
            recommended_commands=["ait merge --dry-run --json", "git status --short"],
            docs_reference="docs/safe-merge-workflow.md",
        )
        return 2
    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_merge_text(result))
    if result.status == "merged":
        return 0
    if result.status == "planned":
        return 0
    return 1
