from __future__ import annotations

import os
import shlex
import subprocess

from ._shared import *

from ait.app import create_commit_for_attempt, init_repo, verify_attempt
from ait.continue_flow import ContinueResult, build_continue_result
from ait.db import AttemptRecord, connect_db, get_attempt, update_attempt, utc_now
from ait.resume import ResumeResult, launch_resume_shell, resume_env, resume_shell_script
from ait.session_room import SessionError, SessionStore
from ait.session_terminal import run_foreground_attach
from ait.workspace_lease import update_workspace_lease


AGENT_CONTINUE_NO_TARGET = 75
_AUTO_CONTINUE_STATUSES = {"active", "failed", "conflict", "stale", "orphan"}


def handle(args, repo_root: Path, parser=None) -> int:
    del parser
    if args.command == "agent-continue":
        return _handle_agent_continue(args, repo_root)
    try:
        result = build_continue_result(repo_root, selector=args.selector)
    except (SessionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "shell_hook", False):
        if result.target_type == "attempt_resume" and result.resume is not None:
            print(resume_shell_script(result.resume), end="")
            return 0
        return 1
    if getattr(args, "shell_reminder", False):
        text = _format_shell_reminder(result)
        if not text:
            return 1
        print(text)
        return 0
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
            run_foreground_attach(SessionStore(Path(result.repo_root or repo_root)), session_id, render=True)
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
            command_text = _human_agent_hint_command(hint.command, result.resume)
            command = f" -> {command_text}" if command_text else ""
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
        label = _attempt_label(result.resume)
        lines.append(f"Attempt: {label}")
        if result.resume.attempt_description:
            lines.append(f"Description: {result.resume.attempt_description}")
        lines.extend(
            [
                "Finish from this shell:",
                f"  ait resume {shlex.quote(label)} --finish",
            ]
        )
    return "\n".join(lines)


def _format_shell_reminder(result: ContinueResult) -> str:
    if result.target_type == "attempt_resume" and result.resume is not None:
        attempt = _attempt_label(result.resume)
        return "\n".join(
            [
                f"AIT: interrupted attempt {attempt} is recoverable.",
                "Run: ait continue",
            ]
        )
    if result.target_type == "session_attach" and result.session is not None:
        session_id = str(result.session.get("session_id") or "latest")
        return "\n".join(
            [
                f"AIT: session {session_id} has an active turn.",
                "Run: ait continue",
            ]
        )
    return ""


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
    label = _attempt_label(resume)
    lines = [
        f"Attempt: {label}",
    ]
    if resume.attempt_description:
        lines.append(f"Description: {resume.attempt_description}")
    lines.extend([
        f"Resume command: ait resume {shlex.quote(label)}",
        f"Finish command: ait resume {shlex.quote(label)} --finish",
    ])
    return lines


def _human_agent_hint_command(command: str | None, resume: ResumeResult | None) -> str | None:
    if not command:
        return None
    if " && " in command:
        return command.split(" && ", 1)[1]
    if resume is not None and command == f"cd {shlex.quote(resume.workspace_ref)}":
        return f"ait resume {shlex.quote(_attempt_label(resume))}"
    return command


def _handle_agent_continue(args, repo_root: Path) -> int:
    agent_args = list(getattr(args, "agent_args", []) or [])
    if agent_args and agent_args[0] == "--":
        agent_args = agent_args[1:]
    try:
        result = build_continue_result(repo_root, selector="latest")
    except (SessionError, ValueError):
        return AGENT_CONTINUE_NO_TARGET
    if result.target_type != "attempt_resume" or result.resume is None:
        return AGENT_CONTINUE_NO_TARGET
    if result.resume.status not in _AUTO_CONTINUE_STATUSES:
        return AGENT_CONTINUE_NO_TARGET
    return _launch_agent_in_resume_workspace(
        repo_root,
        resume=result.resume,
        adapter_name=str(args.adapter),
        real_binary=str(args.real_binary),
        agent_args=tuple(agent_args),
    )


def _launch_agent_in_resume_workspace(
    repo_root: Path,
    *,
    resume: ResumeResult,
    adapter_name: str,
    real_binary: str,
    agent_args: tuple[str, ...],
) -> int:
    binary = Path(real_binary)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        print(
            f"ait wrapper failed: real {adapter_name} binary not executable: {real_binary}",
            file=sys.stderr,
        )
        return 127
    workspace = Path(resume.workspace_ref)
    if not workspace.exists():
        return AGENT_CONTINUE_NO_TARGET

    command = _agent_continue_command(
        adapter_name=adapter_name,
        real_binary=real_binary,
        repo_root=Path(resume.repo_root),
        resume=resume,
        agent_args=agent_args,
    )
    env = resume_env(resume)
    env["AIT_AGENT_CONTINUE_ADAPTER"] = adapter_name
    env["AIT_AGENT_CONTINUE_ATTEMPT_ID"] = resume.attempt_id
    _mark_agent_continue_running(resume, adapter_name=adapter_name)
    label = _attempt_label(resume)
    print(
        "AIT: continuing interrupted attempt "
        f"{label} in {resume.workspace_ref}",
        file=sys.stderr,
    )
    try:
        completed = subprocess.run(command, cwd=workspace, env=env, check=False)
        exit_code = int(completed.returncode)
    except KeyboardInterrupt:
        exit_code = 130
    return _finish_agent_continue(repo_root, resume=resume, adapter_name=adapter_name, exit_code=exit_code)


def _attempt_label(resume: ResumeResult) -> str:
    return resume.attempt_handle or resume.attempt_id.rsplit(":", 1)[-1]


def _agent_continue_command(
    *,
    adapter_name: str,
    real_binary: str,
    repo_root: Path,
    resume: ResumeResult,
    agent_args: tuple[str, ...],
) -> list[str]:
    if agent_args:
        return [real_binary, *agent_args]
    attempt_harness = _attempt_harness(repo_root, resume.attempt_id)
    if adapter_name == "claude-code" and attempt_harness == "claude-code":
        return [real_binary, "--continue"]
    if adapter_name == "codex" and attempt_harness == "codex":
        resume_id = _codex_resume_id(repo_root, resume.attempt_id)
        if resume_id:
            return [real_binary, "resume", resume_id]
    return [real_binary]


def _attempt_harness(repo_root: Path, attempt_id: str) -> str | None:
    attempt = _load_attempt(repo_root, attempt_id)
    if attempt is None:
        return None
    if attempt.agent_harness:
        return attempt.agent_harness
    return attempt.agent_id.split(":", 1)[0]


def _load_attempt(repo_root: Path, attempt_id: str) -> AttemptRecord | None:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        return get_attempt(conn, attempt_id)
    finally:
        conn.close()


def _codex_resume_id(repo_root: Path, attempt_id: str) -> str | None:
    init_result = init_repo(repo_root)
    attempt = _load_attempt(init_result.repo_root, attempt_id)
    if attempt is None or not attempt.raw_trace_ref:
        return None
    from ait.continue_flow import _codex_resume_id as trace_codex_resume_id

    return trace_codex_resume_id(init_result.repo_root, attempt.raw_trace_ref)


def _mark_agent_continue_running(resume: ResumeResult, *, adapter_name: str) -> None:
    root = Path(resume.repo_root)
    init_result = init_repo(root)
    conn = connect_db(init_result.db_path)
    try:
        update_attempt(
            conn,
            resume.attempt_id,
            reported_status="running",
            heartbeat_at=utc_now(),
        )
    finally:
        conn.close()
    update_workspace_lease(
        resume.workspace_ref,
        owner_pid=os.getpid(),
        owner_command=f"ait agent-continue {adapter_name}",
        state="active",
        clear_preserve_reason=True,
    )


def _finish_agent_continue(
    repo_root: Path,
    *,
    resume: ResumeResult,
    adapter_name: str,
    exit_code: int,
) -> int:
    workspace = Path(resume.workspace_ref)
    committed = False
    if exit_code == 0 and _git_status(workspace):
        _git(workspace, "add", "-A")
        if _has_staged_changes(workspace):
            create_commit_for_attempt(
                repo_root,
                attempt_id=resume.attempt_id,
                message=f"{adapter_name}: continue interrupted work",
            )
            committed = True
    if not committed:
        init_result = init_repo(repo_root)
        conn = connect_db(init_result.db_path)
        try:
            update_attempt(
                conn,
                resume.attempt_id,
                reported_status="finished",
                ended_at=utc_now(),
                heartbeat_at=utc_now(),
                result_exit_code=exit_code,
            )
        finally:
            conn.close()
        try:
            verify_attempt(repo_root, attempt_id=resume.attempt_id)
        except Exception:
            pass
    update_workspace_lease(
        resume.workspace_ref,
        state="succeeded" if exit_code == 0 else "failed",
        cleanup_policy="auto",
        clear_preserve_reason=True,
    )
    return exit_code


def _git_status(cwd: Path) -> str:
    return _git(cwd, "status", "--porcelain").stdout.strip()


def _has_staged_changes(cwd: Path) -> bool:
    completed = _git(cwd, "diff", "--cached", "--quiet", check=False)
    return completed.returncode == 1


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return completed
