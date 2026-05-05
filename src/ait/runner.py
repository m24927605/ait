from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from ait.adapters import get_adapter
from ait.app import AttemptShowResult, create_attempt, create_intent, show_attempt, verify_attempt
from ait.daemon import start_daemon
from ait.db import connect_db, get_attempt
from ait.db.core import utc_now
from ait.events import process_event
from ait.harness import AitHarness, HarnessError
from ait.ids import new_ulid
from ait.memory import add_attempt_memory_note, ensure_agent_memory_imported
from ait.memory_policy import init_memory_policy
from ait.run_report import refresh_run_reports
from ait.runner_context import AIT_CONTEXT_BUDGET_CHARS, _write_context_file
from ait.runner_pty import _run_command_with_pty_transcript, _stdio_is_tty
from ait.runner_semantics import _semantic_exit_code
from ait.runner_transcript import (
    AIT_TRANSCRIPT_FIELD_BUDGET_CHARS,
    _fit_transcript_field_budget,
    _strip_terminal_control,
    _write_command_transcript,
)
from ait.workspace import WorkspaceError, create_attempt_commit


@dataclass(frozen=True, slots=True)
class RunResult:
    intent_id: str
    attempt_id: str
    workspace_ref: str
    exit_code: int
    command_stdout: str | None
    command_stderr: str | None
    attempt: AttemptShowResult


class _LocalRunHarness:
    def __init__(self, repo_root: Path, attempt_id: str) -> None:
        self._repo_root = repo_root
        self._attempt_id = attempt_id

    def __enter__(self) -> _LocalRunHarness:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def record_tool(self, **kwargs: object) -> None:
        del kwargs

    def finish(self, *, exit_code: int, raw_trace_ref: str | None = None) -> None:
        _finish_attempt_locally(
            self._repo_root,
            self._attempt_id,
            exit_code=exit_code,
            raw_trace_ref=raw_trace_ref,
        )


def run_agent_command(
    repo_root: str | Path,
    *,
    intent_title: str,
    command: list[str],
    agent_id: str | None = None,
    adapter_name: str | None = None,
    kind: str | None = None,
    description: str | None = None,
    commit_message: str | None = None,
    auto_commit: bool = True,
    with_context: bool = False,
    capture_command_output: bool = False,
) -> RunResult:
    if not intent_title.strip():
        raise ValueError("intent title must not be empty")
    if not command:
        raise ValueError("command must not be empty")

    adapter = get_adapter(adapter_name)
    resolved_agent_id = agent_id or adapter.default_agent_id
    resolved_with_context = with_context or adapter.default_with_context
    root = Path(repo_root).resolve()
    init_memory_policy(root)
    ensure_agent_memory_imported(root)
    daemon = start_daemon(root)
    local_only = False
    if not daemon.running:
        local_only = True
        print(
            f"ait warning: daemon did not start at {daemon.socket_path}; continuing in local-only mode",
            file=sys.stderr,
        )

    intent = create_intent(
        root,
        title=intent_title,
        description=description,
        kind=kind or f"{adapter.name}-run",
    )
    attempt = create_attempt(root, intent_id=intent.intent_id, agent_id=resolved_agent_id)
    workspace = Path(attempt.workspace_ref)
    _record_command_as_prompt(
        root,
        attempt_id=attempt.attempt_id,
        command=tuple(command),
        adapter_name=adapter.name,
    )
    context_file = (
        _write_context_file(
            root,
            workspace,
            intent.intent_id,
            attempt_id=attempt.attempt_id,
            command=tuple(command),
            agent_id=resolved_agent_id,
        )
        if resolved_with_context
        else None
    )

    started = time.monotonic()
    env = {
        **os.environ,
        "AIT_INTENT_ID": intent.intent_id,
        "AIT_ATTEMPT_ID": attempt.attempt_id,
        "AIT_WORKSPACE_REF": attempt.workspace_ref,
        **adapter.env,
    }
    if context_file is not None:
        env["AIT_CONTEXT_FILE"] = str(context_file)
    completed: subprocess.CompletedProcess[str] | None = None
    effective_exit_code = 1
    should_capture_output = capture_command_output or adapter.name == "cursor"
    should_capture_tty = not should_capture_output and _stdio_is_tty()
    raw_trace_ref: str | None = None
    raw_trace_text: str = ""
    postprocess_interrupted = False
    harness_context = (
        _LocalRunHarness(root, attempt.attempt_id)
        if local_only
        else AitHarness.open(
            attempt_id=attempt.attempt_id,
            ownership_token=attempt.ownership_token,
            socket_path=daemon.socket_path,
            agent={
                "agent_id": resolved_agent_id,
                "harness": resolved_agent_id.split(":", 1)[0],
                "harness_version": "ait-run",
            },
        )
    )
    with harness_context as harness:
        try:
            if should_capture_tty:
                completed = _run_command_with_pty_transcript(command, cwd=workspace, env=env)
                raw_trace_text = completed.stdout or ""
            else:
                completed = subprocess.run(
                    command,
                    cwd=workspace,
                    env=env,
                    check=False,
                    text=True,
                    capture_output=should_capture_output,
                )
                if should_capture_output:
                    raw_trace_text = "\n".join([completed.stdout or "", completed.stderr or ""])
        except OSError as exc:
            completed = subprocess.CompletedProcess(
                command,
                127,
                "",
                f"ait run failed: command not executable: {command[0]} ({exc})\n",
            )
            raw_trace_text = completed.stderr or ""
        if should_capture_output:
            raw_trace_ref, postprocess_interrupted = _write_command_transcript_best_effort(
                root,
                attempt.attempt_id,
                command=command,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                exit_code=completed.returncode,
            )
        elif should_capture_tty:
            raw_trace_ref, postprocess_interrupted = _write_command_transcript_best_effort(
                root,
                attempt.attempt_id,
                command=command,
                stdout=raw_trace_text,
                stderr="",
                exit_code=completed.returncode,
            )
        if adapter.name == "aider":
            from ait.aider_capture import persist_aider_session

            aider_ref = persist_aider_session(
                root,
                attempt_id=attempt.attempt_id,
                workspace=workspace,
            )
            if aider_ref is not None:
                raw_trace_ref = aider_ref
        if adapter.name == "cursor" and completed is not None:
            from ait.cursor_capture import persist_cursor_session

            cursor_ref = persist_cursor_session(
                root,
                attempt_id=attempt.attempt_id,
                stdout_text=completed.stdout or "",
            )
            if cursor_ref is not None:
                raw_trace_ref = cursor_ref
        effective_exit_code = _semantic_exit_code(
            completed.returncode,
            transcript=raw_trace_text,
            workspace=workspace,
            context_file=context_file,
        )
        if postprocess_interrupted:
            effective_exit_code = 130
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            harness.record_tool(
                tool_name=command[0],
                category="command",
                duration_ms=duration_ms,
                success=effective_exit_code == 0,
            )
            harness.finish(exit_code=effective_exit_code, raw_trace_ref=raw_trace_ref)
        except (HarnessError, KeyboardInterrupt):
            _finish_attempt_locally(
                root,
                attempt.attempt_id,
                exit_code=effective_exit_code,
                raw_trace_ref=raw_trace_ref,
            )

    resolved_commit_message = _resolve_commit_message(
        explicit=commit_message,
        intent_title=intent_title,
        adapter_name=adapter.name,
    )
    explicit_commit = bool(commit_message and commit_message.strip())
    commit_enabled = (
        completed is not None
        and effective_exit_code == 0
        and bool(resolved_commit_message)
        and (auto_commit or explicit_commit)
    )
    try:
        if commit_enabled:
            if context_file is not None:
                context_file.unlink(missing_ok=True)
            workspace_path = Path(attempt.workspace_ref)
            _stage_all_changes(workspace_path)
            if _has_staged_changes(workspace_path):
                create_attempt_commit(
                    attempt.workspace_ref,
                    message=resolved_commit_message,
                    intent_id=intent.intent_id,
                    attempt_id=attempt.attempt_id,
                )
            shown = verify_attempt(root, attempt_id=attempt.attempt_id)
        else:
            shown = verify_attempt(root, attempt_id=attempt.attempt_id)
        _add_attempt_memory_note_with_warning(root, shown)
    except KeyboardInterrupt:
        effective_exit_code = 130
        shown = verify_attempt(root, attempt_id=attempt.attempt_id)
        _add_attempt_memory_note_with_warning(root, shown)
    try:
        refresh_run_reports(root, latest_attempt_id=attempt.attempt_id)
    except Exception:
        pass

    return RunResult(
        intent_id=intent.intent_id,
        attempt_id=attempt.attempt_id,
        workspace_ref=attempt.workspace_ref,
        exit_code=effective_exit_code,
        command_stdout=completed.stdout if completed is not None and capture_command_output else None,
        command_stderr=completed.stderr if completed is not None and capture_command_output else None,
        attempt=shown,
    )


def _add_attempt_memory_note_with_warning(repo_root: Path, shown: AttemptShowResult) -> None:
    try:
        add_attempt_memory_note(repo_root, shown)
    except Exception as exc:
        print(f"ait warning: add_attempt_memory_note failed: {exc}", file=sys.stderr)


def _record_command_as_prompt(
    repo_root: Path,
    *,
    attempt_id: str,
    command: tuple[str, ...],
    adapter_name: str,
) -> str | None:
    """Persist the launched command line as the attempt's raw prompt.

    Native-hook adapters (Claude Code, Codex, Gemini) capture the actual
    user/assistant turns through their own hook bridges; for everyone else
    the closest analog of "prompt" is the command-line ait was asked to
    run, which is what this helper stores.
    """
    if not command:
        return None
    prompts_dir = repo_root / ".ait" / "prompts"
    try:
        prompts_dir.mkdir(parents=True, exist_ok=True)
        dest = prompts_dir / f"{attempt_id}.txt"
        body = (
            f"# adapter: {adapter_name}\n"
            f"# captured-by: ait runner _record_command_as_prompt\n"
            "\n"
            + " ".join(shlex.quote(arg) for arg in command)
            + "\n"
        )
        dest.write_text(body, encoding="utf-8")
    except OSError:
        return None
    relative_ref = dest.relative_to(repo_root).as_posix()
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return relative_ref
    try:
        conn = connect_db(db_path)
        try:
            conn.execute(
                "UPDATE evidence_summaries SET raw_prompt_ref = ? WHERE attempt_id = ?",
                (relative_ref, attempt_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    return relative_ref


def _resolve_commit_message(*, explicit: str | None, intent_title: str, adapter_name: str) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    cleaned_title = " ".join(intent_title.split()).strip()
    if cleaned_title:
        return f"{adapter_name}: {cleaned_title}"
    return f"{adapter_name}: agent changes"


def _finish_attempt_locally(
    repo_root: Path,
    attempt_id: str,
    *,
    exit_code: int,
    raw_trace_ref: str | None,
) -> None:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            return
        payload: dict[str, object] = {"exit_code": int(exit_code)}
        if raw_trace_ref is not None:
            payload["raw_trace_ref"] = raw_trace_ref
        process_event(
            conn,
            {
                "schema_version": 1,
                "event_id": f"ait-run-local-finish:{attempt_id}:{new_ulid()}",
                "event_type": "attempt_finished",
                "sent_at": utc_now(),
                "attempt_id": attempt_id,
                "ownership_token": attempt.ownership_token,
                "payload": payload,
            },
        )
    finally:
        conn.close()


def _write_command_transcript_best_effort(
    repo_root: Path,
    attempt_id: str,
    *,
    command: list[str],
    stdout: str,
    stderr: str,
    exit_code: int,
) -> tuple[str | None, bool]:
    try:
        return (
            _write_command_transcript(
                repo_root,
                attempt_id,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            ),
            False,
        )
    except KeyboardInterrupt:
        print("ait warning: interrupted while writing command transcript", file=sys.stderr)
        return None, True


def _stage_all_changes(workspace: Path) -> None:
    completed = subprocess.run(
        ["git", "add", "-A"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkspaceError(completed.stderr.strip() or "git add -A failed")


def _has_staged_changes(workspace: Path) -> bool:
    completed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return False
    if completed.returncode == 1:
        return True
    raise WorkspaceError(completed.stderr.strip() or "git diff --cached failed")
