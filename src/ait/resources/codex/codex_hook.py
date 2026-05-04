"""Codex CLI hook bridge for ait provenance.

Codex CLI exposes Claude-compatible lifecycle hooks (`SessionStart`,
`PostToolUse`, `Stop`, `SessionEnd`) and forwards the same payload
shape (`hook_event_name`, `transcript_path`, `cwd`, `session_id`).
This script mirrors the Claude Code hook bridge so each Codex session
becomes one ait attempt with the persisted transcript landing under
`.ait/transcripts/<attempt-id>.jsonl`.

The bridge is deliberately non-blocking for Codex: operational errors
are written to stderr and the hook exits 0 with `{"continue": true}`
so a telemetry problem does not interrupt the coding session.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Mapping

from ait.app import create_attempt, create_intent
from ait.daemon import daemon_status, start_daemon
from ait.harness import AitHarness


STATE_DIR_NAME = "codex-hooks"


def main() -> int:
    output: dict[str, Any] = {}
    try:
        payload = json.load(sys.stdin)
        result = handle_hook(payload, os.environ)
        if result:
            output.update(result)
    except Exception as exc:
        print(f"ait codex hook warning: {exc}", file=sys.stderr)
    if output:
        print(json.dumps(output, sort_keys=True))
    return 0


def handle_hook(
    payload: Mapping[str, Any], environ: Mapping[str, str]
) -> dict[str, Any] | None:
    event_name = str(payload.get("hook_event_name", ""))
    if event_name == "SessionStart":
        return handle_session_start(payload, environ)
    if event_name in {"PostToolUse", "PostToolUseFailure"}:
        handle_tool_event(payload, success=event_name == "PostToolUse")
        return None
    if event_name == "SessionEnd":
        handle_session_end(payload)
        return None
    if event_name == "Stop":
        handle_stop(payload)
        return {"continue": True}
    return None


def handle_session_start(
    payload: Mapping[str, Any], environ: Mapping[str, str]
) -> dict[str, Any]:
    repo_root = repo_root_for_payload(payload, environ)
    session_id = required_str(payload, "session_id")
    source = str(payload.get("source") or "startup")
    model = optional_str(payload.get("model"))
    agent_type = str(payload.get("agent_type") or "default")

    status = start_daemon(repo_root)
    if not status.running:
        raise RuntimeError(f"ait daemon did not start at {status.socket_path}")

    intent = create_intent(
        repo_root,
        title=f"Codex session {short_session_id(session_id)}",
        description=f"source={source}",
        kind="agent-session",
    )
    attempt = create_attempt(
        repo_root,
        intent_id=intent.intent_id,
        agent_id=f"codex:{agent_type}",
    )

    agent: dict[str, Any] = {
        "agent_id": f"codex:{agent_type}",
        "harness": "codex",
        "harness_version": "hook-example",
    }
    if model:
        agent["model"] = model
    state = {
        "session_id": session_id,
        "intent_id": intent.intent_id,
        "attempt_id": attempt.attempt_id,
        "ownership_token": attempt.ownership_token,
        "socket_path": str(status.socket_path),
        "workspace_ref": attempt.workspace_ref,
        "agent": agent,
    }
    write_state(repo_root, session_id, state)
    append_env_file(
        environ,
        {
            "AIT_INTENT_ID": intent.intent_id,
            "AIT_ATTEMPT_ID": attempt.attempt_id,
            "AIT_WORKSPACE_REF": attempt.workspace_ref,
        },
    )

    harness = open_harness(state)
    try:
        harness.start()
    finally:
        harness.close()

    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"ait attempt {attempt.attempt_id} is recording this Codex "
                f"session. Attempt workspace: {attempt.workspace_ref}"
            ),
        }
    }


def handle_tool_event(payload: Mapping[str, Any], *, success: bool) -> None:
    repo_root = repo_root_for_payload(payload, os.environ)
    state = read_state(repo_root, required_str(payload, "session_id"))
    if state is None:
        return
    tool_name = str(payload.get("tool_name") or "unknown")
    category = tool_category(tool_name)
    files = tool_files(payload)
    duration_ms = int(payload.get("duration_ms") or 0)

    harness = open_harness(state)
    try:
        harness.record_tool(
            tool_name=tool_name,
            category=category,
            duration_ms=duration_ms,
            success=success,
            files=files,
        )
    finally:
        harness.close()


def handle_stop(payload: Mapping[str, Any]) -> None:
    repo_root = repo_root_for_payload(payload, os.environ)
    state = read_state(repo_root, required_str(payload, "session_id"))
    if state is None:
        return
    harness = open_harness(state)
    try:
        harness.heartbeat()
    finally:
        harness.close()


def handle_session_end(payload: Mapping[str, Any]) -> None:
    repo_root = repo_root_for_payload(payload, os.environ)
    session_id = required_str(payload, "session_id")
    state = read_state(repo_root, session_id)
    if state is None:
        return
    exit_code = int(payload.get("exit_code") or 0)
    transcript_source = optional_str(payload.get("transcript_path"))
    persisted = persist_transcript(
        repo_root,
        attempt_id=str(state["attempt_id"]),
        source_path=transcript_source,
    )
    raw_trace_ref = persisted or transcript_source

    harness = open_harness(state)
    try:
        harness.finish(exit_code=exit_code, raw_trace_ref=raw_trace_ref)
    finally:
        harness.close()


def persist_transcript(
    repo_root: Path, *, attempt_id: str, source_path: str | None
) -> str | None:
    """Copy the upstream Codex session jsonl into .ait/transcripts/.

    Returns the repo-relative path on success so the caller can use it
    as raw_trace_ref. Returns None if the source is missing or
    unreadable so the caller can fall back to the upstream path string.
    """
    if not source_path:
        return None
    src = Path(source_path)
    if not src.is_absolute():
        candidate = repo_root / src
        src = candidate if candidate.exists() else src
    if not src.exists() or not src.is_file():
        return None
    dest_dir = repo_root / ".ait" / "transcripts"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = src.suffix or ".jsonl"
        dest = dest_dir / f"{attempt_id}{suffix}"
        dest.write_bytes(src.read_bytes())
    except OSError:
        return None
    return dest.relative_to(repo_root).as_posix()


def open_harness(state: Mapping[str, Any]) -> AitHarness:
    return AitHarness.open(
        attempt_id=str(state["attempt_id"]),
        ownership_token=str(state["ownership_token"]),
        socket_path=Path(str(state["socket_path"])),
        agent=dict(state["agent"]),
    )


def repo_root_for_payload(payload: Mapping[str, Any], environ: Mapping[str, str]) -> Path:
    start = Path(
        environ.get("CODEX_PROJECT_DIR")
        or environ.get("CLAUDE_PROJECT_DIR")
        or str(payload.get("cwd") or "")
        or os.getcwd()
    ).resolve()
    for path in (start, *start.parents):
        if (path / ".git").exists():
            return path
    raise RuntimeError(f"not inside a git repository: {start}")


def state_path(repo_root: Path, session_id: str) -> Path:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in session_id)
    return repo_root / ".ait" / STATE_DIR_NAME / f"{safe}.json"


def write_state(repo_root: Path, session_id: str, state: Mapping[str, Any]) -> None:
    path = state_path(repo_root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(state), indent=2, sort_keys=True), encoding="utf-8")


def read_state(repo_root: Path, session_id: str) -> dict[str, Any] | None:
    path = state_path(repo_root, session_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_env_file(environ: Mapping[str, str], values: Mapping[str, str]) -> None:
    env_file = environ.get("CODEX_ENV_FILE") or environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    with Path(env_file).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"export {key}={shlex.quote(value)}\n")


def tool_category(tool_name: str) -> str:
    if tool_name in {"Read", "Grep", "Glob", "LS"}:
        return "read"
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"}:
        return "write"
    if tool_name in {"Bash", "shell"}:
        return "command"
    return "other"


def tool_files(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return []
    access = "write" if tool_category(tool_name) == "write" else "read"
    paths: list[str] = []
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    return [{"path": path, "access": access} for path in sorted(set(paths))]


def required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"missing required string field: {key}")
    return value


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def short_session_id(session_id: str) -> str:
    return session_id.replace("-", "")[:12] or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
