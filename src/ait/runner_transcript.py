from __future__ import annotations

from pathlib import Path

from ait.memory_policy import EXCLUDED_MARKER, load_memory_policy, transcript_excluded
from ait.redaction import redact_text
from ait.transcript import normalize_transcript, strip_terminal_control


AIT_TRANSCRIPT_FIELD_BUDGET_CHARS = 1_000_000


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
