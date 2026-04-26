from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time

from ait.app import AttemptShowResult, create_attempt, create_intent, show_attempt
from ait.context import build_agent_context, render_agent_context_text
from ait.daemon import start_daemon
from ait.harness import AitHarness
from ait.workspace import create_attempt_commit


@dataclass(frozen=True, slots=True)
class RunResult:
    intent_id: str
    attempt_id: str
    workspace_ref: str
    exit_code: int
    attempt: AttemptShowResult


def run_agent_command(
    repo_root: str | Path,
    *,
    intent_title: str,
    agent_id: str,
    command: list[str],
    kind: str | None = None,
    description: str | None = None,
    commit_message: str | None = None,
    with_context: bool = False,
) -> RunResult:
    if not intent_title.strip():
        raise ValueError("intent title must not be empty")
    if not command:
        raise ValueError("command must not be empty")

    root = Path(repo_root).resolve()
    daemon = start_daemon(root)
    if not daemon.running:
        raise RuntimeError(f"ait daemon did not start at {daemon.socket_path}")

    intent = create_intent(
        root,
        title=intent_title,
        description=description,
        kind=kind or "agent-run",
    )
    attempt = create_attempt(root, intent_id=intent.intent_id, agent_id=agent_id)
    workspace = Path(attempt.workspace_ref)
    context_file = _write_context_file(root, workspace, intent.intent_id) if with_context else None

    started = time.monotonic()
    env = {
        **os.environ,
        "AIT_INTENT_ID": intent.intent_id,
        "AIT_ATTEMPT_ID": attempt.attempt_id,
        "AIT_WORKSPACE_REF": attempt.workspace_ref,
    }
    if context_file is not None:
        env["AIT_CONTEXT_FILE"] = str(context_file)
    completed: subprocess.CompletedProcess[str] | None = None
    with AitHarness.open(
        attempt_id=attempt.attempt_id,
        ownership_token=attempt.ownership_token,
        socket_path=daemon.socket_path,
        agent={
            "agent_id": agent_id,
            "harness": agent_id.split(":", 1)[0],
            "harness_version": "ait-run",
        },
    ) as harness:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            check=False,
            text=True,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        harness.record_tool(
            tool_name=command[0],
            category="command",
            duration_ms=duration_ms,
            success=completed.returncode == 0,
        )
        harness.finish(exit_code=completed.returncode)

    if commit_message and completed is not None and completed.returncode == 0:
        create_attempt_commit(
            attempt.workspace_ref,
            message=commit_message,
            intent_id=intent.intent_id,
            attempt_id=attempt.attempt_id,
        )

    shown = show_attempt(root, attempt_id=attempt.attempt_id)
    return RunResult(
        intent_id=intent.intent_id,
        attempt_id=attempt.attempt_id,
        workspace_ref=attempt.workspace_ref,
        exit_code=completed.returncode if completed is not None else 1,
        attempt=shown,
    )


def _write_context_file(repo_root: Path, workspace: Path, intent_id: str) -> Path:
    context = build_agent_context(repo_root, intent_id=intent_id)
    path = workspace / ".ait-context.md"
    path.write_text(render_agent_context_text(context), encoding="utf-8")
    return path
