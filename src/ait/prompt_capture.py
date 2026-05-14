from __future__ import annotations

from pathlib import Path
import shlex
from typing import Mapping

from ait.db import connect_db
from ait.redaction import redact_text


PROMPT_PAYLOAD_KEYS = (
    "prompt",
    "user_prompt",
    "initial_prompt",
    "instruction",
    "instructions",
    "message",
    "input",
    "text",
)

PROMPT_VALUE_OPTIONS = {
    "-p",
    "--prompt",
    "--message",
    "--instruction",
    "--instructions",
    "--task",
    "--query",
}

PROMPT_INLINE_OPTIONS = tuple(f"{option}=" for option in PROMPT_VALUE_OPTIONS if option.startswith("--"))

AGENT_COMMAND_MARKERS = {
    "aider": ("aider",),
    "claude-code": ("claude", "claude-code"),
    "codex": ("codex",),
    "gemini": ("gemini",),
}


def record_command_prompt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    command: tuple[str, ...],
    adapter_name: str,
) -> str | None:
    if not command:
        return None
    root = Path(repo_root)
    prompt_args = _command_prompt_arguments(command, adapter_name=adapter_name)
    redacted_command, command_redacted = redact_text(" ".join(shlex.quote(arg) for arg in command))
    redacted_prompt_args = []
    prompt_redacted = False
    for index, value, source in prompt_args:
        redacted, was_redacted = redact_text(value)
        prompt_redacted = prompt_redacted or was_redacted
        redacted_prompt_args.append((index, redacted, source))

    prompt_status = "captured-from-command-args" if redacted_prompt_args else "not-observable"
    body = [
        f"# adapter: {adapter_name}",
        "# captured-by: ait prompt_capture record_command_prompt",
        "# capture-kind: command-line",
        f"# prompt-status: {prompt_status}",
        f"# redacted: {str(command_redacted or prompt_redacted).lower()}",
        "",
        "## Command",
        redacted_command,
        "",
    ]
    if redacted_prompt_args:
        body.extend(["## Prompt Arguments"])
        for index, value, source in redacted_prompt_args:
            body.append(f"- argv[{index}] via {source}: {value}")
        body.append("")
    else:
        body.extend(
            [
                "## Prompt Visibility",
                (
                    "AIT captured the launched command, but no user prompt was "
                    "observable in the command line. For interactive CLIs, use "
                    "the adapter transcript evidence when available."
                ),
                "",
            ]
        )
    return _write_prompt_file(root, attempt_id=attempt_id, body="\n".join(body))


def record_payload_prompt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    adapter_name: str,
    payload: Mapping[str, object],
    event_name: str,
) -> str | None:
    extracted = _payload_prompt_fields(payload)
    if not extracted:
        return None
    redacted_fields: list[tuple[str, str]] = []
    was_redacted = False
    for key, value in extracted:
        redacted, field_redacted = redact_text(value)
        was_redacted = was_redacted or field_redacted
        redacted_fields.append((key, redacted))
    body = [
        f"# adapter: {adapter_name}",
        "# captured-by: ait prompt_capture record_payload_prompt",
        "# capture-kind: hook-payload",
        f"# hook-event: {event_name}",
        "# prompt-status: captured-from-hook-payload",
        f"# redacted: {str(was_redacted).lower()}",
        "",
        "## Prompt Fields",
    ]
    for key, value in redacted_fields:
        body.extend([f"### {key}", value, ""])
    return _write_prompt_file(Path(repo_root), attempt_id=attempt_id, body="\n".join(body))


def _write_prompt_file(repo_root: Path, *, attempt_id: str, body: str) -> str | None:
    prompts_dir = repo_root / ".ait" / "prompts"
    try:
        prompts_dir.mkdir(parents=True, exist_ok=True)
        dest = prompts_dir / f"{_safe_name(attempt_id)}.txt"
        dest.write_text(body.rstrip() + "\n", encoding="utf-8")
    except OSError:
        return None
    relative_ref = dest.relative_to(repo_root).as_posix()
    _update_raw_prompt_ref(repo_root, attempt_id=attempt_id, raw_prompt_ref=relative_ref)
    return relative_ref


def _update_raw_prompt_ref(repo_root: Path, *, attempt_id: str, raw_prompt_ref: str) -> None:
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return
    try:
        conn = connect_db(db_path)
        try:
            conn.execute(
                "UPDATE evidence_summaries SET raw_prompt_ref = ? WHERE attempt_id = ?",
                (raw_prompt_ref, attempt_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _payload_prompt_fields(payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    for key in PROMPT_PAYLOAD_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            fields.append((key, value.strip()))
    messages = payload.get("messages")
    if isinstance(messages, list):
        for index, item in enumerate(messages):
            if not isinstance(item, Mapping):
                continue
            role = item.get("role")
            text = item.get("text") or item.get("content")
            if role == "user" and isinstance(text, str) and text.strip():
                fields.append((f"messages[{index}]", text.strip()))
    return tuple(fields)


def _command_prompt_arguments(
    command: tuple[str, ...],
    *,
    adapter_name: str,
) -> tuple[tuple[int, str, str], ...]:
    found: list[tuple[int, str, str]] = []
    prompt_value_next: tuple[int, str] | None = None
    for index, arg in enumerate(command[1:], start=1):
        if prompt_value_next is not None:
            option_index, option = prompt_value_next
            if arg.strip():
                found.append((index, arg, f"option {option} at argv[{option_index}]"))
            prompt_value_next = None
            continue
        if arg in PROMPT_VALUE_OPTIONS:
            prompt_value_next = (index, arg)
            continue
        inline = _inline_prompt_option(arg)
        if inline is not None:
            option, value = inline
            if value.strip():
                found.append((index, value, option))
            continue
    if found or not _looks_like_agent_command(command[0], adapter_name=adapter_name):
        return tuple(found)
    positional = []
    skip_next = False
    for index, arg in enumerate(command[1:], start=1):
        if skip_next:
            skip_next = False
            continue
        if arg in PROMPT_VALUE_OPTIONS:
            skip_next = True
            continue
        if arg.startswith("-"):
            if "=" not in arg and _option_likely_takes_value(arg):
                skip_next = True
            continue
        if _looks_like_prompt_positional(arg):
            positional.append((index, arg, "agent positional argument"))
    return tuple(positional)


def _inline_prompt_option(arg: str) -> tuple[str, str] | None:
    for prefix in PROMPT_INLINE_OPTIONS:
        if arg.startswith(prefix):
            return prefix[:-1], arg[len(prefix) :]
    return None


def _looks_like_agent_command(command: str, *, adapter_name: str) -> bool:
    markers = AGENT_COMMAND_MARKERS.get(adapter_name, ())
    if not markers:
        return False
    lowered = command.lower()
    return any(marker in lowered for marker in markers)


def _looks_like_prompt_positional(arg: str) -> bool:
    stripped = arg.strip()
    if not stripped:
        return False
    if "\n" in stripped:
        return True
    if len(stripped.split()) >= 2:
        return True
    return len(stripped) >= 24 and not Path(stripped).suffix


def _option_likely_takes_value(arg: str) -> bool:
    return arg in {"-c", "-m", "-f", "--config", "--model", "--file", "--cwd"}


def _safe_name(attempt_id: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in attempt_id)
