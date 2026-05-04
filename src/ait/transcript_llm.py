"""LLM-based transcript summarizer providers.

Pluggable second tier of the agent transcript memory pipeline. Reads a
parsed transcript, calls a configured LLM provider over plain stdlib
``urllib.request``, and returns a compact summary string.

Two providers are shipped:

- ``anthropic``: POSTs to ``https://api.anthropic.com/v1/messages``.
- ``openai-compat``: POSTs to ``<base_url>/chat/completions``. Works
  with OpenAI, Azure OpenAI, Together, OpenRouter, vLLM, Ollama
  (``http://localhost:11434/v1``), etc.

There is no SDK dependency. ``ait`` keeps its zero-runtime-dependency
guarantee.

A failure of any kind raises :class:`LLMSummarizerError`. The caller is
expected to catch it and fall back to the heuristic summarizer.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterable

from ait.memory_policy import SummarizerLLMConfig
from ait.transcript_summarizer import TranscriptEvent


SYSTEM_PROMPT = (
    "You summarize an AI coding agent's session transcript so the next "
    "agent can pick up where this one stopped. Output one tight paragraph, "
    "no preamble, no headers, no markdown. Cover: decisions made and the "
    "reason; approaches that were tried and abandoned and why; errors hit "
    "and how they were resolved; tool actions of structural interest "
    "(file writes, migrations, network calls); open questions left for "
    "the user. Skip read-only exploration (greps, file reads), restatements "
    "of the user's prompt, and boilerplate ('I'll help you with that'). "
    "Use third-person past tense."
)


class LLMSummarizerError(RuntimeError):
    """Raised when an LLM provider call fails for any reason.

    The orchestrator catches this and falls back to the heuristic
    summarizer so a misconfigured key, a network blip, or a malformed
    response never poisons the attempt lifecycle.
    """


def llm_summary(
    events: Iterable[TranscriptEvent],
    *,
    config: SummarizerLLMConfig,
) -> str:
    """Render events as text and ask the configured provider for a summary."""
    transcript_text = _render_events_for_prompt(events)
    if not transcript_text.strip():
        raise LLMSummarizerError("transcript is empty after rendering")
    api_key = os.environ.get(config.api_key_env, "").strip()
    if not api_key:
        raise LLMSummarizerError(
            f"environment variable {config.api_key_env} is not set"
        )
    if config.provider == "anthropic":
        return _call_anthropic(transcript_text, config=config, api_key=api_key)
    if config.provider == "openai-compat":
        return _call_openai_compat(transcript_text, config=config, api_key=api_key)
    raise LLMSummarizerError(f"unsupported provider: {config.provider}")


def _call_anthropic(
    transcript_text: str, *, config: SummarizerLLMConfig, api_key: str
) -> str:
    body = json.dumps(
        {
            "model": config.model,
            "max_tokens": max(256, config.max_chars * 2),
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": _user_prompt(transcript_text, config.max_chars),
                }
            ],
        }
    ).encode("utf-8")
    url = (config.base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
    response = _post_json(
        url,
        body=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout=config.timeout_seconds,
    )
    parts = response.get("content")
    if not isinstance(parts, list):
        raise LLMSummarizerError("anthropic response missing content array")
    text_chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            value = part.get("text")
            if isinstance(value, str):
                text_chunks.append(value)
    summary = "".join(text_chunks).strip()
    if not summary:
        raise LLMSummarizerError("anthropic response had no text content")
    return _truncate(summary, config.max_chars)


def _call_openai_compat(
    transcript_text: str, *, config: SummarizerLLMConfig, api_key: str
) -> str:
    base = config.base_url or "https://api.openai.com/v1"
    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": config.model,
            "max_tokens": max(256, config.max_chars * 2),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _user_prompt(transcript_text, config.max_chars),
                },
            ],
        }
    ).encode("utf-8")
    response = _post_json(
        url,
        body=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=config.timeout_seconds,
    )
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMSummarizerError("openai-compat response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMSummarizerError("openai-compat first choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise LLMSummarizerError("openai-compat first choice missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMSummarizerError("openai-compat message content is empty")
    return _truncate(content.strip(), config.max_chars)


def _post_json(
    url: str, *, body: bytes, headers: dict[str, str], timeout: int
) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise LLMSummarizerError(
            f"HTTP {exc.code} from {url}: {snippet}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMSummarizerError(f"network error to {url}: {exc}") from exc
    try:
        decoded = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise LLMSummarizerError(f"non-JSON response from {url}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise LLMSummarizerError(f"non-object JSON response from {url}")
    return decoded


def _render_events_for_prompt(events: Iterable[TranscriptEvent]) -> str:
    lines: list[str] = []
    for event in events:
        role = event.role
        if event.tool:
            files = f" files={','.join(event.files)}" if event.files else ""
            ok = ""
            if event.ok is False:
                ok = " ok=false"
            elif event.ok is True:
                ok = " ok=true"
            lines.append(f"[{role}] tool={event.tool}{files}{ok}")
            if event.text:
                lines.append(event.text.strip())
        else:
            text = event.text.strip() if event.text else ""
            if text:
                lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _user_prompt(transcript_text: str, max_chars: int) -> str:
    return (
        f"Summarize the following agent session transcript in <= {max_chars} "
        "characters. Output only the summary text, no quotes, no headers.\n\n"
        f"<transcript>\n{transcript_text}\n</transcript>"
    )


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
