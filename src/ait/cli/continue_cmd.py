from __future__ import annotations

import shlex

from ._shared import *

from ait.continue_flow import ContinueResult, build_continue_result
from ait.resume import launch_resume_shell
from ait.session_room import SessionError, SessionStore
from ait.session_terminal import run_foreground_attach


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    try:
        result = build_continue_result(repo_root, selector=args.selector)
    except (SessionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    if args.no_interactive or not sys.stdin.isatty() or not sys.stdout.isatty():
        print(_format_continue_result(result))
        return 0
    if result.target_type == "session_attach" and result.session is not None:
        session_id = str(result.session["session_id"])
        print(_format_continue_entry(result), file=sys.stderr)
        try:
            run_foreground_attach(SessionStore(repo_root), session_id, render=True)
        except SessionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if result.target_type == "attempt_resume" and result.resume is not None:
        print(_format_continue_entry(result), file=sys.stderr)
        return launch_resume_shell(result.resume)

    print(_format_continue_result(result))
    return 0


def _format_continue_result(result: ContinueResult) -> str:
    lines = [
        "AIT continue",
        f"Target: {_target_label(result)}",
        f"Reason: {result.reason}",
    ]
    if result.session is not None:
        lines.extend(_session_lines(result))
    if result.resume is not None:
        lines.extend(_resume_lines(result))
    if result.command:
        lines.extend(["Next:", f"- {result.command}"])
    if result.agent_hints:
        lines.append("Agent hints:")
        for hint in result.agent_hints:
            command = f" -> {hint.command}" if hint.command else ""
            lines.append(f"- {hint.agent_id}: {hint.note}{command}")
    if result.blocking_reasons:
        lines.append("Blocking reasons:")
        lines.extend(f"- {reason}" for reason in result.blocking_reasons)
    if result.limitations:
        lines.append("Limits:")
        lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines)


def _format_continue_entry(result: ContinueResult) -> str:
    lines = [
        f"Continuing with {_target_label(result)}",
        f"Reason: {result.reason}",
    ]
    if result.command:
        lines.append(f"Command: {result.command}")
    if result.resume is not None:
        lines.extend(
            [
                f"Workspace: {result.resume.workspace_ref}",
                "",
                "Finish from this shell:",
                '  ait attempt commit "$AIT_RESUME_ATTEMPT_ID" -m "continue interrupted work"',
                '  cd "$AIT_RESUME_REPO_ROOT"',
                '  ait apply "$AIT_RESUME_ATTEMPT_ID"',
            ]
        )
    return "\n".join(lines)


def _target_label(result: ContinueResult) -> str:
    return {
        "session_attach": "AIT session attach",
        "session": "AIT session",
        "attempt_resume": "AIT attempt worktree",
        "none": "none",
    }.get(result.target_type, result.target_type)


def _session_lines(result: ContinueResult) -> list[str]:
    session = result.session or {}
    lines = [
        f"Session: {session.get('session_id')}",
        f"State: {session.get('state')}",
    ]
    turn_id = session.get("current_turn_id")
    if turn_id:
        lines.append(f"Turn: {turn_id}")
    participants = session.get("participants")
    if isinstance(participants, list) and participants:
        agents = ", ".join(
            str(item.get("agent_id"))
            for item in participants
            if isinstance(item, dict) and item.get("agent_id")
        )
        if agents:
            lines.append(f"Agents: {agents}")
    return lines


def _resume_lines(result: ContinueResult) -> list[str]:
    resume = result.resume
    if resume is None:
        return []
    return [
        f"Attempt: {resume.attempt_id.rsplit(':', 1)[-1]}",
        f"Workspace: {resume.workspace_ref}",
        f"Workspace command: cd {shlex.quote(resume.workspace_ref)}",
        f"Resume command: ait resume {shlex.quote(resume.attempt_id)}",
    ]
