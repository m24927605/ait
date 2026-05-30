from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time

from ait.bug_report.api import report_internal_error
from ait.adapters import doctor_automation, get_adapter
from ait.app import AttemptShowResult, IntentResult, create_attempt, create_intent, init_repo, show_attempt, verify_attempt
from ait.daemon import start_daemon
from ait.db import connect_db, get_attempt, get_intent
from ait.idresolver import resolve_intent_id
from ait.db.core import utc_now
from ait.events import process_event
from ait.harness import AitHarness, HarnessError
from ait.ids import new_ulid
from ait.memory import add_attempt_memory_note
from ait.memory_policy import init_memory_policy
from ait.prompt_capture import record_command_prompt
from ait.run_report import refresh_run_reports
from ait.runner_context import AIT_CONTEXT_BUDGET_CHARS, _write_context_file
from ait.runner_pty import _run_command_with_pty_transcript, _stdio_is_tty
from ait.runner_semantics import _semantic_exit_code
from ait.runner_subprocess import run_command_with_budget_and_timeout
from ait.runner_transcript import (
    AIT_TRANSCRIPT_FIELD_BUDGET_CHARS,
    _fit_transcript_field_budget,
    _strip_terminal_control,
    _write_command_transcript,
)
from ait.banner import print_attempt_banner
from ait.workspace import WorkspaceError, create_attempt_commit, get_base_ref
from ait.workspace_lease import update_workspace_lease


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
    def __init__(self, repo_root: Path, attempt_id: str, ownership_token: str) -> None:
        self._repo_root = repo_root
        self._attempt_id = attempt_id
        self._ownership_token = ownership_token

    def __enter__(self) -> _LocalRunHarness:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def record_tool(self, **kwargs: object) -> None:
        conn = connect_db(self._repo_root / ".ait" / "state.sqlite3")
        try:
            process_event(
                conn,
                {
                    "schema_version": 1,
                    "event_id": f"ait-run-local-tool:{self._attempt_id}:{new_ulid()}",
                    "event_type": "tool_event",
                    "sent_at": utc_now(),
                    "attempt_id": self._attempt_id,
                    "ownership_token": self._ownership_token,
                    "payload": dict(kwargs),
                },
            )
        finally:
            conn.close()

    def finish(self, *, exit_code: int, raw_trace_ref: str | None = None) -> None:
        _finish_attempt_locally(
            self._repo_root,
            self._attempt_id,
            exit_code=exit_code,
            raw_trace_ref=raw_trace_ref,
        )


def _enoent_command_hint(*, command: list[str], adapter) -> str:
    """Suggest the correct `-- <agent> -p "<prompt>"` form when the
    operator's positional looks like a prose prompt rather than a
    binary name. Returns "" when no hint applies (shell adapter, or
    command[0] is a plausible binary name).
    """
    if not adapter.command_name or not command:
        return ""
    first = command[0]
    if " " not in first:
        return ""
    snippet = first[:80] + ("…" if len(first) > 80 else "")
    return (
        f"\nhint: positional looks like a prose prompt; "
        f"did you mean `ait run [opts] -- {adapter.command_name} -p \"{snippet}\"`?"
    )


def _resolve_agent_id(agent_id: str | None, adapter) -> str:
    """Normalize `agent_id` to the storage form `<harness>:<name>`.

    Empty/None → adapter.default_agent_id.
    Already qualified (contains `:`) → returned as-is (the user may
    intentionally pick a different harness like `manual:reviewer`).
    Bare slug → prefixed with `adapter.name:` so the operator can pass
    `--agent backend-architect` instead of `--agent claude-code:backend-architect`.
    """
    if not agent_id:
        return adapter.default_agent_id
    if ":" in agent_id:
        return agent_id
    return f"{adapter.name}:{agent_id}"


def _bind_to_existing_intent(repo_root: Path, intent_id_arg: str) -> IntentResult:
    """Resolve a user-supplied intent identifier to an IntentResult.

    Raises ValueError if the intent cannot be found in this repo.
    """
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        resolved = resolve_intent_id(conn, intent_id_arg)
        record = get_intent(conn, resolved)
        if record is None:
            raise ValueError(f"Unknown intent: {intent_id_arg!r}")
        if record.status in {"abandoned", "superseded"}:
            raise ValueError(f"Intent {resolved} is {record.status}")
    finally:
        conn.close()
    return IntentResult(intent_id=resolved, repo_id=init_result.repo_id)


def run_agent_command(
    repo_root: str | Path,
    *,
    intent_title: str | None = None,
    intent_id: str | None = None,
    command: list[str],
    agent_id: str | None = None,
    adapter_name: str | None = None,
    kind: str | None = None,
    description: str | None = None,
    commit_message: str | None = None,
    auto_commit: bool = True,
    with_context: bool = False,
    capture_command_output: bool = False,
    refresh_reports: bool = True,
    context_file_override: str | Path | None = None,
    command_stdin: str | None = None,
    extra_env: dict[str, str] | None = None,
    stdin_mode: str = "auto",
) -> RunResult:
    if not intent_id and (not intent_title or not intent_title.strip()):
        raise ValueError("either intent_id or intent_title must be provided")
    if not command:
        raise ValueError("command must not be empty")
    if stdin_mode not in ("auto", "inherit", "none"):
        raise ValueError(f"stdin_mode must be 'auto', 'inherit', or 'none', got: {stdin_mode!r}")

    adapter = get_adapter(adapter_name)
    stdio_is_tty = _stdio_is_tty()
    effective_stdin_mode = _resolve_stdin_mode(
        adapter_name=adapter.name,
        command=command,
        requested_stdin_mode=stdin_mode,
        command_stdin=command_stdin,
        stdio_is_tty=stdio_is_tty,
    )
    resolved_agent_id = _resolve_agent_id(agent_id, adapter)
    resolved_with_context = with_context or adapter.default_with_context
    if (
        effective_stdin_mode == "inherit"
        and command_stdin is None
        and adapter.native_hooks
        and not stdio_is_tty
    ):
        print(
            f"ait hint: stdin is not a TTY and adapter '{adapter.name}' may wait for stdin EOF; "
            "pass --stdin none if the wrapped command does not need stdin",
            file=sys.stderr,
        )
    root = Path(repo_root).resolve()
    if adapter.name != "shell":
        try:
            if not doctor_automation(adapter.name, root).ok:
                print(
                    f"ait warning: adapter '{adapter.name}' wrapper is not active. "
                    f"ait cannot capture internal tool calls (tests, edits, etc.); "
                    f"the verifier will see no test evidence and may mark the attempt failed. "
                    f"Run `ait init --adapter {adapter.name}` for full observability.",
                    file=sys.stderr,
                )
        except Exception:
            pass
    init_memory_policy(root)
    daemon = start_daemon(root)
    local_only = False
    if not daemon.running:
        local_only = True
        print(
            f"ait warning: daemon did not start at {daemon.socket_path}; continuing in local-only mode",
            file=sys.stderr,
        )

    if intent_id is not None:
        intent = _bind_to_existing_intent(root, intent_id)
    else:
        intent = create_intent(
            root,
            title=intent_title,
            description=description,
            kind=kind or f"{adapter.name}-run",
        )
    attempt = create_attempt(root, intent_id=intent.intent_id, agent_id=resolved_agent_id)
    update_workspace_lease(
        attempt.workspace_ref,
        owner_pid=os.getpid(),
        owner_command="ait run",
        state="active",
        clear_preserve_reason=True,
    )
    workspace = Path(attempt.workspace_ref)
    record_command_prompt(
        root,
        attempt_id=attempt.attempt_id,
        command=tuple(command),
        adapter_name=adapter.name,
    )
    context_file = (
        Path(context_file_override)
        if context_file_override is not None
        else (
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
    )

    started = time.monotonic()
    env = {
        **os.environ,
        "AIT_INTENT_ID": intent.intent_id,
        # AIT_INTENT mirrors AIT_INTENT_ID; the adapter_wrapper.py shim
        # reads `$AIT_INTENT` when re-execing `ait run` so it can
        # forward the parent attempt's intent through wrapper recursion.
        # See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md.
        "AIT_INTENT": intent.intent_id,
        "AIT_ATTEMPT_ID": attempt.attempt_id,
        "AIT_WORKSPACE_REF": attempt.workspace_ref,
        **adapter.env,
    }
    if extra_env:
        env.update(extra_env)
    if context_file is not None:
        env["AIT_CONTEXT_FILE"] = str(context_file)
    completed: subprocess.CompletedProcess[str] | None = None
    effective_exit_code = 1
    should_capture_tty = command_stdin is None and not capture_command_output and adapter.name != "cursor" and stdio_is_tty
    should_capture_output = capture_command_output or adapter.name == "cursor" or not should_capture_tty
    raw_trace_ref: str | None = None
    raw_trace_text: str = ""
    postprocess_interrupted = False
    harness_context = (
        _LocalRunHarness(root, attempt.attempt_id, attempt.ownership_token)
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
    try:
        _, target_ref_name = get_base_ref(root)
        workspace_rel = os.path.relpath(str(workspace), start=str(root))
        print_attempt_banner(
            attempt_id=attempt.attempt_id,
            workspace_rel=workspace_rel,
            head="detached",
            target=target_ref_name or "main",
        )
    except Exception:
        # Never fail the run on a banner emission error.
        pass

    with harness_context as harness:
        try:
            if should_capture_tty:
                completed = _run_command_with_pty_transcript(command, cwd=workspace, env=env)
                raw_trace_text = completed.stdout or ""
            else:
                # P0 fix: was `subprocess.run(capture_output=...)` which
                # (a) buffered entire stdout/stderr in RAM (OOM risk on
                # chatty agents) and (b) lacked start_new_session=True
                # so Ctrl-C / timeout could not killpg the child tree.
                # `run_command_with_budget_and_timeout` streams with a
                # byte budget, escalates SIGINT/SIGKILL on the process
                # group, and honors AIT_RUN_TIMEOUT_SECONDS.
                completed = run_command_with_budget_and_timeout(
                    command,
                    cwd=workspace,
                    env=env,
                    capture_output=should_capture_output,
                    command_stdin=command_stdin,
                    stdin_mode=effective_stdin_mode,
                )
                if should_capture_output:
                    raw_trace_text = "\n".join([completed.stdout or "", completed.stderr or ""])
                    if not capture_command_output and adapter.name != "cursor":
                        _replay_completed_output(completed)
        except OSError as exc:
            hint = _enoent_command_hint(command=command, adapter=adapter)
            completed = subprocess.CompletedProcess(
                command,
                127,
                "",
                f"ait run failed: command not executable: {command[0]} ({exc}){hint}\n",
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
            mark_finished_locally = getattr(harness, "mark_finished_locally", None)
            if callable(mark_finished_locally):
                mark_finished_locally()

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
                context_file.with_name(context_file.name + ".manifest.json").unlink(missing_ok=True)
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
    if refresh_reports:
        try:
            refresh_run_reports(root, latest_attempt_id=attempt.attempt_id)
        except Exception:
            pass
    update_workspace_lease(
        attempt.workspace_ref,
        state=_lease_state_for_run_result(shown.attempt.get("verified_status"), effective_exit_code),
        cleanup_policy="auto",
        clear_preserve_reason=True,
    )

    return RunResult(
        intent_id=intent.intent_id,
        attempt_id=attempt.attempt_id,
        workspace_ref=attempt.workspace_ref,
        exit_code=effective_exit_code,
        command_stdout=completed.stdout if completed is not None and capture_command_output else None,
        command_stderr=completed.stderr if completed is not None and capture_command_output else None,
        attempt=shown,
    )


def _resolve_stdin_mode(
    *,
    adapter_name: str,
    command: list[str],
    requested_stdin_mode: str,
    command_stdin: str | None,
    stdio_is_tty: bool,
) -> str:
    if requested_stdin_mode != "auto":
        return requested_stdin_mode
    if command_stdin is not None:
        return "inherit"
    if _is_noninteractive_codex_exec(
        adapter_name=adapter_name,
        command=command,
        stdio_is_tty=stdio_is_tty,
    ):
        return "none"
    return "inherit"


def _is_noninteractive_codex_exec(
    *,
    adapter_name: str,
    command: list[str],
    stdio_is_tty: bool,
) -> bool:
    if adapter_name != "codex":
        return False
    exec_index = _codex_exec_index(command)
    if exec_index is None:
        return False
    return not stdio_is_tty or _codex_exec_has_argv_prompt(command[exec_index + 1 :])


def _codex_exec_index(command: list[str]) -> int | None:
    if len(command) >= 2 and Path(command[0]).name in {"codex", "codex.js", "codex.exe"}:
        return 1 if command[1] == "exec" else None
    if (
        len(command) >= 3
        and Path(command[0]).name in {"node", "nodejs"}
        and Path(command[1]).name in {"codex.js", "codex"}
    ):
        return 2 if command[2] == "exec" else None
    return None


def _codex_exec_has_argv_prompt(exec_args: list[str]) -> bool:
    options_with_value = {
        "-C",
        "-c",
        "-m",
        "-o",
        "--cd",
        "--config",
        "--config-file",
        "--model",
        "--output-last-message",
        "--profile",
        "--sandbox",
    }
    skip_next = False
    for index, arg in enumerate(exec_args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--":
            return any(candidate != "-" for candidate in exec_args[index + 1 :])
        if arg in options_with_value:
            skip_next = True
            continue
        if any(
            arg.startswith(option + "=")
            for option in options_with_value
            if option.startswith("--")
        ):
            continue
        if arg.startswith("-"):
            continue
        return arg != "-"
    return False


def _replay_completed_output(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        print(completed.stdout, end="", file=sys.stdout)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)


def _add_attempt_memory_note_with_warning(repo_root: Path, shown: AttemptShowResult) -> None:
    try:
        add_attempt_memory_note(repo_root, shown)
    except Exception as exc:
        report_internal_error(category="memory.note_write", exc=exc)
        print(f"ait warning: add_attempt_memory_note failed: {exc}", file=sys.stderr)


def _lease_state_for_run_result(verified_status: object, exit_code: int) -> str:
    if verified_status == "promoted":
        return "applied"
    if verified_status == "succeeded" and exit_code == 0:
        return "succeeded"
    return "failed"


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
        update_workspace_lease(
            attempt.workspace_ref,
            state="failed" if exit_code else "active",
            owner_pid=os.getpid(),
            owner_command="ait run",
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
    if not workspace.exists():
        raise WorkspaceError(f"missing workspace: {workspace}")
    if not workspace.is_dir():
        raise WorkspaceError(f"workspace is not a directory: {workspace}")
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
