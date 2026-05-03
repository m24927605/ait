"""Heuristic summarizer for agent transcripts.

Reads a persisted transcript (JSON-Lines) under ``.ait/transcripts/`` and
produces a compact memory note body that captures what an agent
actually did during the session — final answer, structural tool calls,
file touches, and failures — not just the diff.

The parser tolerates two shapes:

1. The common envelope this project standardizes on for non-Claude
   adapters (Step 3 of the transcript memory design):
   ``{"role": "user|assistant|tool_use|tool_result", "text": "...", ...}``.
2. The Claude Code session jsonl shape that ships verbatim from Claude:
   ``{"type": "user|assistant", "message": {"role": ..., "content": ...}}``
   where ``content`` may be a string or a list of typed blocks.

Lines that fail to parse or do not match either shape are skipped
silently. The summarizer must never raise on malformed input — it is
called from the daemon and a single bad line should not poison the
note.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from ait.db import connect_db, get_attempt
from ait.memory.notes import add_memory_note
from ait.memory.models import MemoryNote


STRUCTURAL_TOOLS: frozenset[str] = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
)
DEFAULT_SUMMARY_MAX_CHARS = 600


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    role: str
    text: str = ""
    tool: str | None = None
    files: tuple[str, ...] = ()
    ok: bool | None = None


def parse_transcript(path: str | Path) -> Iterator[TranscriptEvent]:
    """Yield TranscriptEvent for each parsable line in the transcript."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        yield from _events_from_object(obj)


def _events_from_object(obj: dict) -> Iterator[TranscriptEvent]:
    role = obj.get("role")
    if isinstance(role, str) and role:
        text = _coerce_text(obj.get("text"))
        tool = _coerce_str_or_none(obj.get("tool"))
        ok = _coerce_bool_or_none(obj.get("ok"))
        files = _coerce_files(obj.get("files"), tool=tool, payload=obj)
        yield TranscriptEvent(role=role, text=text, tool=tool, files=files, ok=ok)
        return
    msg = obj.get("message")
    if isinstance(msg, dict):
        msg_role = _coerce_str_or_none(msg.get("role")) or _coerce_str_or_none(obj.get("type"))
        if not msg_role:
            return
        content = msg.get("content")
        yield from _events_from_claude_content(msg_role, content)


def _events_from_claude_content(role: str, content: object) -> Iterator[TranscriptEvent]:
    if isinstance(content, str):
        yield TranscriptEvent(role=role, text=content)
        return
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = _coerce_str_or_none(block.get("type"))
        if block_type == "text":
            text = _coerce_text(block.get("text"))
            yield TranscriptEvent(role=role, text=text)
        elif block_type == "tool_use":
            tool = _coerce_str_or_none(block.get("name"))
            files = _coerce_files(None, tool=tool, payload=block.get("input"))
            yield TranscriptEvent(role="tool_use", text="", tool=tool, files=files)
        elif block_type == "tool_result":
            ok = not bool(block.get("is_error"))
            text = _coerce_text(block.get("content"))
            yield TranscriptEvent(role="tool_result", text=text, ok=ok)


def heuristic_summary(
    events: Iterable[TranscriptEvent], *, max_chars: int = DEFAULT_SUMMARY_MAX_CHARS
) -> str:
    """Compose a short text summary from parsed events."""
    parts: list[str] = []
    user_text = ""
    assistant_text = ""
    structural_tools: list[TranscriptEvent] = []
    failed_results: list[TranscriptEvent] = []

    for event in events:
        if event.role == "user" and event.text:
            user_text = event.text
        elif event.role == "assistant" and event.text:
            assistant_text = event.text
        elif event.role == "tool_use" and event.tool:
            structural_tools.append(event)
        elif event.role == "tool_result" and event.ok is False:
            failed_results.append(event)

    if user_text:
        parts.append(f"User intent: {_truncate(user_text, 200)}")
    if assistant_text:
        parts.append(f"Agent ended with: {_truncate(assistant_text, 200)}")

    structural = [e for e in structural_tools if e.tool in STRUCTURAL_TOOLS]
    if structural:
        names = sorted({e.tool for e in structural if e.tool})
        parts.append(
            f"Structural tools: {', '.join(names)} ({len(structural)} call"
            f"{'s' if len(structural) != 1 else ''})"
        )
        files = sorted({f for e in structural for f in e.files})
        if files:
            shown = ", ".join(files[:5])
            suffix = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
            parts.append(f"Files touched: {shown}{suffix}")

    if failed_results:
        parts.append(f"Tool failures: {len(failed_results)}")

    if not parts:
        return ""

    summary = "\n".join(parts)
    return _truncate(summary, max_chars)


def summarize_transcript_to_note(
    repo_root: str | Path,
    *,
    attempt_id: str,
    transcript_path: str | Path,
    agent_id: str,
    max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
) -> MemoryNote | None:
    """Parse + summarize + persist as a memory note. Returns the note."""
    body = heuristic_summary(parse_transcript(transcript_path), max_chars=max_chars)
    if not body.strip():
        return None
    return add_memory_note(
        repo_root,
        body=body,
        topic="transcript-summary",
        source=f"transcript-summary:{agent_id}:{attempt_id}",
    )


INTERNAL_TRANSCRIPT_PREFIX = ".ait/transcripts/"


def summarize_attempt_transcript(
    repo_root: str | Path,
    attempt_id: str,
    *,
    max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
) -> MemoryNote | None:
    """Look up the attempt, find its persisted transcript, and summarize.

    Skipped (returns None) when:
    - the attempt has no raw_trace_ref
    - the trace points outside the repo-local .ait/transcripts/ tree
      (typically a legacy external Claude Code path; we do not summarize
      what we cannot guarantee will still exist)
    - the transcript file is empty or yields no events.
    """
    root = Path(repo_root).resolve()
    db_path = root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return None
    conn = connect_db(db_path)
    try:
        attempt = get_attempt(conn, attempt_id)
    finally:
        conn.close()
    if attempt is None or not attempt.raw_trace_ref:
        return None
    ref = attempt.raw_trace_ref.replace("\\", "/")
    if not ref.startswith(INTERNAL_TRANSCRIPT_PREFIX):
        return None
    transcript_path = root / ref
    if not transcript_path.exists():
        return None
    return summarize_transcript_to_note(
        root,
        attempt_id=attempt_id,
        transcript_path=transcript_path,
        agent_id=attempt.agent_id,
        max_chars=max_chars,
    )


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                inner = item.get("text") or item.get("content")
                if isinstance(inner, str):
                    chunks.append(inner)
        return "\n".join(chunks)
    if value is None:
        return ""
    return str(value)


def _coerce_str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _coerce_bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _coerce_files(
    files_value: object, *, tool: str | None, payload: object
) -> tuple[str, ...]:
    if isinstance(files_value, list):
        return tuple(str(item) for item in files_value if isinstance(item, str) and item)
    if not isinstance(payload, dict):
        return ()
    candidates: list[str] = []
    for key in ("file_path", "path", "notebook_path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    return tuple(sorted(set(candidates)))


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
