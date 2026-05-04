"""Cursor CLI stream-json capture for ait provenance.

Cursor CLI's headless mode (``cursor-agent --print --output-format
stream-json``) emits a newline-delimited JSON event stream to stdout.
Each line is a typed event:

- ``{"type": "system", "subtype": "init", ...}``
- ``{"type": "user", "message": "..."}``
- ``{"type": "assistant", "content": "..."}`` (multiple chunks per turn)
- ``{"type": "tool_call", "subtype": "started", "name": "...", ...}``
- ``{"type": "tool_call", "subtype": "completed", "name": "...", ...}``
- ``{"type": "result", "subtype": "success", ...}``

This module parses that stream into the common transcript envelope and
copies the result to ``.ait/transcripts/<attempt-id>.jsonl`` so the
heuristic and LLM summarizers and the recall pipeline treat Cursor
sessions the same as Claude Code, Codex, Aider, and Gemini.

The Cursor CLI does not yet fire post-tool hooks reliably in headless
mode (only ``sessionStart`` is dependable as of early 2026), so this
stdout-stream path is the most complete capture available today.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def parse_cursor_stream_json(text: str) -> Iterator[dict]:
    """Yield common-envelope events parsed from Cursor stream-json output."""
    if not text:
        return

    assistant_buffer: list[str] = []

    def flush_assistant() -> dict | None:
        nonlocal assistant_buffer
        if not assistant_buffer:
            return None
        body = "".join(assistant_buffer).strip()
        assistant_buffer = []
        if not body:
            return None
        return {"role": "assistant", "text": body}

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
        event_type = obj.get("type")
        if event_type == "assistant":
            chunk = _extract_text(obj)
            if chunk:
                assistant_buffer.append(chunk)
            continue
        flushed = flush_assistant()
        if flushed is not None:
            yield flushed
        if event_type == "user":
            text_value = _extract_text(obj)
            if text_value:
                yield {"role": "user", "text": text_value}
        elif event_type == "tool_call":
            yield from _events_from_tool_call(obj)
        elif event_type == "system":
            sub = str(obj.get("subtype") or "")
            session_id = obj.get("session_id")
            yield {
                "role": "meta",
                "text": f"system:{sub}"
                + (f" session_id={session_id}" if session_id else ""),
            }
        elif event_type == "result":
            sub = str(obj.get("subtype") or "")
            yield {"role": "meta", "text": f"result:{sub}"}

    final = flush_assistant()
    if final is not None:
        yield final


def _events_from_tool_call(obj: dict) -> Iterator[dict]:
    name = obj.get("name") or obj.get("tool_name")
    sub = str(obj.get("subtype") or "")
    files = _files_from_input(obj)
    if sub == "started":
        yield {
            "role": "tool_use",
            "tool": str(name) if name else None,
            "files": list(files),
        }
    elif sub == "completed":
        ok = obj.get("ok")
        if ok is None and "is_error" in obj:
            ok = not bool(obj.get("is_error"))
        if ok is None:
            ok = True
        yield {
            "role": "tool_result",
            "tool": str(name) if name else None,
            "ok": bool(ok),
        }


def _extract_text(obj: dict) -> str:
    for key in ("text", "content", "message", "delta"):
        value = obj.get(key)
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
            if chunks:
                return "\n".join(chunks)
    return ""


def _files_from_input(obj: dict) -> Iterable[str]:
    seen: set[str] = set()
    for source in (obj, obj.get("input"), obj.get("arguments")):
        if not isinstance(source, dict):
            continue
        for key in ("file_path", "path", "absolute_path", "notebook_path"):
            value = source.get(key)
            if isinstance(value, str) and value and value not in seen:
                seen.add(value)
    return sorted(seen)


def persist_cursor_session(
    repo_root: str | Path,
    *,
    attempt_id: str,
    stdout_text: str,
) -> str | None:
    """Convert Cursor stream-json stdout to envelope and store under .ait/transcripts/."""
    if not stdout_text or not stdout_text.strip():
        return None
    events = list(parse_cursor_stream_json(stdout_text))
    if not events:
        return None
    root = Path(repo_root).resolve()
    dest_dir = root / ".ait" / "transcripts"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{attempt_id}.jsonl"
        with dest.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
    except OSError:
        return None
    return dest.relative_to(root).as_posix()
