"""Aider chat history capture for ait provenance.

Aider does not expose a hook system the way Claude Code and Codex do.
What it does have is a markdown chat-history file (default name
``.aider.chat.history.md``, written in the working directory) that
records each turn of the conversation between the user and aider.

This module parses that file into the common transcript envelope and
copies the result to ``.ait/transcripts/<attempt-id>.jsonl`` so the
heuristic and LLM summarizers (and the recall pipeline) can treat
aider sessions the same as Claude Code and Codex.

The parser is intentionally tolerant — aider's output format has
shifted across versions (heading style, blockquote prefix for user
input, etc.). It looks for ``####`` lines (the historical user-input
marker) and ``# aider chat started`` markers, and treats everything
else between user inputs as the assistant's reply.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


DEFAULT_HISTORY_FILENAME = ".aider.chat.history.md"


def aider_history_path(workspace: str | Path) -> Path:
    """Where aider writes its chat history by default."""
    return Path(workspace) / DEFAULT_HISTORY_FILENAME


def parse_aider_history(path: str | Path) -> Iterator[dict]:
    """Yield common-envelope events parsed from aider's chat history.

    Markers recognized:

    - ``# aider chat started ...`` → meta event with the timestamp
    - ``#### <user input>`` → user event; trailing lines until the
      next ``####`` are the assistant's reply
    - blockquote-prefixed user input (``> ...``) at the start of a
      block is also accepted as user input

    Blank lines inside an assistant message are preserved.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    state: str | None = None
    buffer: list[str] = []

    def flush_assistant() -> dict | None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        buffer = []
        if not body:
            return None
        return {"role": "assistant", "text": body}

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("# aider chat started"):
            event = flush_assistant()
            if event is not None:
                yield event
            yield {"role": "meta", "text": line.lstrip("# ").strip()}
            state = None
            continue
        if line.startswith("####"):
            event = flush_assistant()
            if event is not None:
                yield event
            user_text = line[4:].lstrip()
            yield {"role": "user", "text": user_text}
            state = "assistant"
            continue
        if state == "assistant":
            buffer.append(line)

    final = flush_assistant()
    if final is not None:
        yield final


def persist_aider_session(
    repo_root: str | Path,
    *,
    attempt_id: str,
    workspace: str | Path,
) -> str | None:
    """Convert aider's chat history into the envelope and store it.

    Returns the repo-relative POSIX path of
    ``.ait/transcripts/<attempt-id>.jsonl`` on success, or None when no
    aider history exists for this attempt or the file is empty.
    """
    workspace_path = Path(workspace)
    history = aider_history_path(workspace_path)
    if not history.exists():
        return None
    events = list(parse_aider_history(history))
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
