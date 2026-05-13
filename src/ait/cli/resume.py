from __future__ import annotations

import shlex

from ._shared import *

from ait.resume import ResumeError, build_resume_result, launch_resume_shell


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        result = build_resume_result(repo_root, attempt_selector=args.attempt_id)
    except (RecoverError, ResumeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    if args.print:
        print(result.workspace_ref)
        return 0
    if args.no_interactive or not sys.stdin.isatty() or not sys.stdout.isatty():
        print(_format_resume_result(result))
        return 0

    print(_format_resume_entry(result), file=sys.stderr)
    return launch_resume_shell(result)


def _format_resume_result(result) -> str:
    lines = [
        "AIT resume workspace",
        f"Attempt: {result.attempt_id.rsplit(':', 1)[-1]}",
        f"Workspace: {result.workspace_ref}",
        "Next:",
        f"- export AIT_RESUME_ATTEMPT_ID={shlex.quote(result.attempt_id)}",
        f"- export AIT_RESUME_REPO_ROOT={shlex.quote(result.repo_root)}",
        f"- cd {shlex.quote(result.workspace_ref)}",
        "- continue editing",
        '- ait attempt commit "$AIT_RESUME_ATTEMPT_ID" -m "continue interrupted work"',
        '- cd "$AIT_RESUME_REPO_ROOT"',
        '- ait apply "$AIT_RESUME_ATTEMPT_ID"',
    ]
    return "\n".join(lines)


def _format_resume_entry(result) -> str:
    lines = [
        f"Entering AIT workspace for attempt {result.attempt_id.rsplit(':', 1)[-1]}",
        f"Workspace: {result.workspace_ref}",
        "",
        "Finish from this shell:",
        '  ait attempt commit "$AIT_RESUME_ATTEMPT_ID" -m "continue interrupted work"',
        '  cd "$AIT_RESUME_REPO_ROOT"',
        '  ait apply "$AIT_RESUME_ATTEMPT_ID"',
        "",
        "Exit this shell when you are done.",
    ]
    return "\n".join(lines)
