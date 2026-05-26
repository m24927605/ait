from __future__ import annotations

import shlex

from ._shared import *

from ait.resume import (
    ResumeError,
    build_resume_result,
    finish_resume_attempt,
    launch_resume_shell,
)


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    if args.finish or args.finish_plan:
        try:
            if args.finish_plan:
                result = build_resume_result(repo_root, attempt_selector=args.attempt_id)
                text = _format_resume_finish_plan(result, debug=args.debug)
                if args.format == "json":
                    payload = result.to_dict()
                    payload["finish_steps"] = list(result.finish_steps)
                    print(json.dumps(payload, indent=2))
                else:
                    print(text)
                return 0
            result = finish_resume_attempt(
                repo_root,
                attempt_selector=args.attempt_id,
                message=args.message,
            )
        except (RecoverError, ResumeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(result.to_dict(debug=args.debug), indent=2))
        else:
            print(_format_resume_finish_result(result, debug=args.debug))
        return 0 if result.status in {"applied", "already_applied"} else 1

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
        print(_format_resume_result(result, debug=args.debug))
        return 0

    print(_format_resume_entry(result), file=sys.stderr)
    return launch_resume_shell(result)


def _format_resume_result(result, *, debug: bool = False) -> str:
    label = _attempt_label(result)
    lines = [
        "AIT resume",
        f"Attempt: {label}",
        f"Status: {result.status}",
    ]
    if result.attempt_description:
        lines.append(f"Description: {result.attempt_description}")
    lines.extend(
        [
            f"Next: ait resume {shlex.quote(label)} --finish",
            f"Debug: ait resume {shlex.quote(label)} --debug",
        ]
    )
    if debug:
        lines.extend(
            [
                "Debug details:",
                f"  Canonical ID: {result.attempt_id}",
                f"  Workspace: {result.workspace_ref}",
                f"  Repo root: {result.repo_root}",
            ]
        )
    return "\n".join(lines)


def _format_resume_entry(result) -> str:
    label = _attempt_label(result)
    lines = [
        f"Entering AIT workspace for attempt {label}",
    ]
    if result.attempt_description:
        lines.append(f"Description: {result.attempt_description}")
    lines.extend(
        [
            "Finish from this shell:",
            f"  ait resume {shlex.quote(label)} --finish",
            "",
            "Exit this shell when you are done.",
        ]
    )
    return "\n".join(lines)


def _format_resume_finish_plan(result, *, debug: bool = False) -> str:
    label = _attempt_label(result)
    lines = [
        "AIT resume finish plan",
        f"Attempt: {label}",
        f"Next: ait resume {shlex.quote(label)} --finish",
    ]
    if debug:
        lines.extend(
            [
                "Debug details:",
                f"  Canonical ID: {result.attempt_id}",
                f"  Workspace: {result.workspace_ref}",
            ]
        )
    return "\n".join(lines)


def _format_resume_finish_result(result, *, debug: bool = False) -> str:
    label = result.attempt_handle or result.attempt_id.rsplit(":", 1)[-1]
    lines = [
        "AIT resume finish",
        f"Status: {result.status}",
        f"Attempt: {label}",
        result.message,
        f"Commit: {'created' if result.commit_created else 'not created'}",
    ]
    if result.attempt_description:
        lines.append(f"Description: {result.attempt_description}")
    if result.apply_result is not None:
        lines.append(f"Apply status: {result.apply_result.status}")
    if result.next_steps:
        lines.append(f"Next: {result.next_steps[0]}")
    if debug:
        lines.extend(
            [
                "Debug details:",
                f"  Canonical ID: {result.attempt_id}",
                f"  Workspace: {result.workspace_ref}",
            ]
        )
        if result.debug:
            reason = result.debug.get("reason")
            if reason:
                lines.append(f"  Reason: {reason}")
    return "\n".join(lines)


def _attempt_label(result) -> str:
    return result.attempt_handle or result.attempt_id.rsplit(":", 1)[-1]
