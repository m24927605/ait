from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios
import time
import tty

from ait.adapters import get_adapter
from ait.app import AttemptShowResult, create_attempt, create_intent, show_attempt, verify_attempt
from ait.brain import build_auto_briefing_query, build_repo_brain_briefing_from_graph, render_repo_brain_briefing, write_repo_brain
from ait.context import build_agent_context, render_agent_context_text
from ait.daemon import start_daemon
from ait.db import connect_db, get_attempt
from ait.db.core import utc_now
from ait.events import process_event
from ait.harness import AitHarness, HarnessError
from ait.ids import new_ulid
from ait.memory import (
    add_attempt_memory_note,
    build_relevant_memory_recall,
    build_repo_memory,
    ensure_agent_memory_imported,
    render_relevant_memory_recall,
    render_repo_memory_text,
)
from ait.memory_policy import EXCLUDED_MARKER, init_memory_policy, load_memory_policy, transcript_excluded
from ait.redaction import redact_text
from ait.run_report import refresh_run_reports
from ait.transcript import normalize_transcript, strip_terminal_control
from ait.workspace import WorkspaceError, create_attempt_commit

AIT_CONTEXT_BUDGET_CHARS = 16000
AIT_TRANSCRIPT_FIELD_BUDGET_CHARS = 1_000_000


@dataclass(frozen=True, slots=True)
class RunResult:
    intent_id: str
    attempt_id: str
    workspace_ref: str
    exit_code: int
    command_stdout: str | None
    command_stderr: str | None
    attempt: AttemptShowResult


@dataclass(frozen=True, slots=True)
class _PtyCompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str = ""


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
    should_capture_output = capture_command_output
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


def _stdio_is_tty() -> bool:
    return (
        hasattr(sys.stdin, "isatty")
        and hasattr(sys.stdout, "isatty")
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def _run_command_with_pty_transcript(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> _PtyCompletedProcess:
    master_fd, slave_fd = pty.openpty()
    old_stdin_attrs = None
    output = bytearray()
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    stdin_is_tty = sys.stdin.isatty()
    stdin_fd = sys.stdin.fileno() if stdin_is_tty else None
    if stdin_is_tty:
        assert stdin_fd is not None
        old_stdin_attrs = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
    finally:
        os.close(slave_fd)

    try:
        while True:
            read_fds = [master_fd]
            if stdin_fd is not None and process.poll() is None:
                read_fds.append(stdin_fd)
            readable, _, _ = select.select(read_fds, [], [], 0.05)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    data = b""
                if data:
                    output.extend(data)
                    _write_terminal_bytes(stdout_buffer, data)
                elif process.poll() is not None:
                    break
            if stdin_fd is not None and stdin_fd in readable:
                data = os.read(stdin_fd, 4096)
                if data:
                    os.write(master_fd, data)
            if process.poll() is not None:
                try:
                    while True:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        output.extend(data)
                        _write_terminal_bytes(stdout_buffer, data)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                break
        return _PtyCompletedProcess(
            args=command,
            returncode=process.wait(),
            stdout=output.decode("utf-8", errors="replace"),
        )
    finally:
        if old_stdin_attrs is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_stdin_attrs)
        os.close(master_fd)


def _write_terminal_bytes(stdout_buffer: object, data: bytes) -> None:
    if stdout_buffer is not None:
        stdout_buffer.write(data)  # type: ignore[attr-defined]
        stdout_buffer.flush()  # type: ignore[attr-defined]
        return
    sys.stdout.write(data.decode("utf-8", errors="replace"))
    sys.stdout.flush()


def _semantic_exit_code(
    exit_code: int,
    *,
    transcript: str,
    workspace: Path,
    context_file: Path | None,
) -> int:
    if exit_code != 0:
        return exit_code
    if not _looks_like_agent_refusal(transcript):
        return exit_code
    if _has_workspace_changes(workspace, context_file=context_file):
        return exit_code
    return 3


def _looks_like_agent_refusal(transcript: str) -> bool:
    text = transcript.lower()
    refusal_markers = (
        "don't have permission",
        "do not have permission",
        "cannot make changes",
        "can't make changes",
        "cannot edit",
        "can't edit",
        "cannot write",
        "can't write",
        "permission denied",
        "operation not permitted",
        "refusing to",
        "i won't",
        "i cannot",
        "i can't",
        "unable to modify",
        "unable to write",
    )
    return any(marker in text for marker in refusal_markers)


def _has_workspace_changes(workspace: Path, *, context_file: Path | None) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    ignored = str(context_file.relative_to(workspace)) if context_file is not None else None
    for line in completed.stdout.splitlines():
        path = line[3:].strip()
        if ignored is not None and path == ignored:
            continue
        return True
    return False


def _resolve_commit_message(*, explicit: str | None, intent_title: str, adapter_name: str) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    cleaned_title = " ".join(intent_title.split()).strip()
    if cleaned_title:
        return f"{adapter_name}: {cleaned_title}"
    return f"{adapter_name}: agent changes"


def _write_context_file(
    repo_root: Path,
    workspace: Path,
    intent_id: str,
    *,
    attempt_id: str,
    command: tuple[str, ...] = (),
    agent_id: str | None = None,
) -> Path:
    context = build_agent_context(repo_root, intent_id=intent_id)
    memory = build_repo_memory(repo_root)
    brain = write_repo_brain(repo_root)
    intent = context.intent
    auto_query = build_auto_briefing_query(
        repo_root,
        intent_title=str(intent.get("title") or ""),
        description=str(intent.get("description") or ""),
        kind=str(intent.get("kind") or ""),
        command=command,
        agent_id=agent_id,
    )
    briefing = build_repo_brain_briefing_from_graph(
        brain,
        auto_query.query,
        sources=auto_query.sources,
    )
    recall = build_relevant_memory_recall(
        repo_root,
        auto_query.query,
        budget_chars=4000,
        attempt_id=attempt_id,
    )
    relevant_memory = render_relevant_memory_recall(recall)
    path = workspace / ".ait-context.md"
    context_text = (
        render_agent_context_text(context)
        + "\n"
        + relevant_memory
        + "\n"
        + render_repo_memory_text(
            memory,
            budget_chars=12000,
            include_advisory_attempt_memory=False,
        )
        + "\n"
        + render_repo_brain_briefing(briefing, budget_chars=5000)
    )
    path.write_text(_fit_context_budget(context_text), encoding="utf-8")
    return path


def _fit_context_budget(text: str, *, budget_chars: int = AIT_CONTEXT_BUDGET_CHARS) -> str:
    if budget_chars <= 0:
        return ""
    if len(text) <= budget_chars:
        return text
    marker = (
        "\n\n[ait context truncated: total context exceeded "
        f"{budget_chars} character budget]\n"
    )
    if len(marker) >= budget_chars:
        return marker[:budget_chars]
    return text[: budget_chars - len(marker)].rstrip() + marker


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


def _write_command_transcript(
    repo_root: Path,
    attempt_id: str,
    *,
    command: list[str],
    stdout: str,
    stderr: str,
    exit_code: int,
) -> str:
    trace_dir = repo_root / ".ait" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"{_safe_trace_name(attempt_id)}.txt"
    stdout = _strip_terminal_control(stdout)
    stderr = _strip_terminal_control(stderr)
    raw_transcript = "\n".join([" ".join(command), stdout, stderr])
    if transcript_excluded(raw_transcript, load_memory_policy(repo_root)):
        path.write_text(
            "\n".join(
                [
                    "AIT Agent Transcript",
                    f"Attempt-Id: {attempt_id}",
                    f"Exit-Code: {exit_code}",
                    "Excluded-By-Memory-Policy: true",
                    "",
                    EXCLUDED_MARKER,
                ]
            ),
            encoding="utf-8",
        )
        return str(path.relative_to(repo_root))

    stdout, stdout_redacted = redact_text(stdout)
    stderr, stderr_redacted = redact_text(stderr)
    command_text, command_redacted = redact_text(" ".join(command))
    path.write_text(
        "\n".join(
            [
                "AIT Agent Transcript",
                f"Attempt-Id: {attempt_id}",
                f"Command: {command_text}",
                f"Exit-Code: {exit_code}",
                f"Redacted: {str(command_redacted or stdout_redacted or stderr_redacted).lower()}",
                "",
                "STDOUT:",
                stdout,
                "",
                "STDERR:",
                stderr,
            ]
        ),
        encoding="utf-8",
    )
    raw_trace_ref = str(path.relative_to(repo_root))
    _write_normalized_transcript(repo_root, attempt_id, raw_trace_ref=raw_trace_ref)
    return raw_trace_ref


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


def _strip_terminal_control(text: str) -> str:
    return strip_terminal_control(_fit_transcript_field_budget(text))


def _fit_transcript_field_budget(
    text: str,
    *,
    budget_chars: int = AIT_TRANSCRIPT_FIELD_BUDGET_CHARS,
) -> str:
    if budget_chars <= 0 or len(text) <= budget_chars:
        return text
    marker = (
        "\n\n[ait transcript truncated: field exceeded "
        f"{budget_chars} character budget]\n\n"
    )
    if len(marker) >= budget_chars:
        return marker[:budget_chars]
    head_budget = (budget_chars - len(marker)) // 2
    tail_budget = budget_chars - len(marker) - head_budget
    return text[:head_budget].rstrip() + marker + text[-tail_budget:].lstrip()


def _write_normalized_transcript(repo_root: Path, attempt_id: str, *, raw_trace_ref: str) -> str | None:
    raw_path = repo_root / raw_trace_ref
    try:
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    adapter = _adapter_from_trace(raw_text)
    normalized = normalize_transcript(raw_text, adapter=adapter)
    if not normalized:
        return None
    normalized_dir = repo_root / ".ait" / "traces" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = normalized_dir / f"{_safe_trace_name(attempt_id)}.txt"
    normalized_path.write_text(normalized, encoding="utf-8")
    return str(normalized_path.relative_to(repo_root))


def _adapter_from_trace(trace_text: str) -> str | None:
    for line in trace_text.splitlines():
        if line.startswith("Command: "):
            command = line[len("Command: ") :]
            if "codex" in command:
                return "codex"
            if "claude" in command:
                return "claude-code"
            if "gemini" in command:
                return "gemini"
            return None
    return None


def _safe_trace_name(attempt_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in attempt_id)


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
