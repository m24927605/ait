from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time

from ait.adapters import get_adapter
from ait.app import AttemptShowResult, create_attempt, create_intent, show_attempt, verify_attempt
from ait.brain import build_auto_briefing_query, build_repo_brain_briefing_from_graph, render_repo_brain_briefing, write_repo_brain
from ait.context import build_agent_context, render_agent_context_text
from ait.daemon import start_daemon
from ait.harness import AitHarness
from ait.memory import (
    add_attempt_memory_note,
    build_relevant_memory_recall,
    build_repo_memory,
    ensure_agent_memory_imported,
    render_relevant_memory_recall,
    render_repo_memory_text,
)
from ait.memory_policy import EXCLUDED_MARKER, load_memory_policy, transcript_excluded
from ait.redaction import redact_text
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
    ensure_agent_memory_imported(root)
    daemon = start_daemon(root)
    if not daemon.running:
        raise RuntimeError(f"ait daemon did not start at {daemon.socket_path}")

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
    should_capture_output = capture_command_output or adapter.name in {"aider", "codex"}
    raw_trace_ref: str | None = None
    with AitHarness.open(
        attempt_id=attempt.attempt_id,
        ownership_token=attempt.ownership_token,
        socket_path=daemon.socket_path,
        agent={
            "agent_id": resolved_agent_id,
            "harness": resolved_agent_id.split(":", 1)[0],
            "harness_version": "ait-run",
        },
    ) as harness:
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                env=env,
                check=False,
                text=True,
                capture_output=should_capture_output,
            )
        except OSError as exc:
            completed = subprocess.CompletedProcess(
                command,
                127,
                "",
                f"ait run failed: command not executable: {command[0]} ({exc})\n",
            )
        if should_capture_output and not capture_command_output:
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
        if adapter.name in {"aider", "codex"}:
            raw_trace_ref = _write_command_transcript(
                root,
                attempt.attempt_id,
                command=command,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                exit_code=completed.returncode,
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        harness.record_tool(
            tool_name=command[0],
            category="command",
            duration_ms=duration_ms,
            success=completed.returncode == 0,
        )
        harness.finish(exit_code=completed.returncode, raw_trace_ref=raw_trace_ref)

    resolved_commit_message = _resolve_commit_message(
        explicit=commit_message,
        intent_title=intent_title,
        adapter_name=adapter.name,
    )
    explicit_commit = bool(commit_message and commit_message.strip())
    commit_enabled = (
        completed is not None
        and completed.returncode == 0
        and bool(resolved_commit_message)
        and (auto_commit or explicit_commit)
    )
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
        shown = show_attempt(root, attempt_id=attempt.attempt_id)
    add_attempt_memory_note(root, shown)

    return RunResult(
        intent_id=intent.intent_id,
        attempt_id=attempt.attempt_id,
        workspace_ref=attempt.workspace_ref,
        exit_code=completed.returncode if completed is not None else 1,
        command_stdout=completed.stdout if completed is not None and capture_command_output else None,
        command_stderr=completed.stderr if completed is not None and capture_command_output else None,
        attempt=shown,
    )


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
    recall = build_relevant_memory_recall(repo_root, auto_query.query, budget_chars=4000)
    relevant_memory = render_relevant_memory_recall(recall)
    path = workspace / ".ait-context.md"
    path.write_text(
        render_agent_context_text(context)
        + "\n"
        + relevant_memory
        + "\n"
        + render_repo_memory_text(memory, budget_chars=12000)
        + "\n"
        + render_repo_brain_briefing(briefing, budget_chars=5000),
        encoding="utf-8",
    )
    return path


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
    return str(path.relative_to(repo_root))


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
