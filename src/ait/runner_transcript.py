from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from ait.memory_policy import (
    EXCLUDED_MARKER,
    default_memory_policy,
    load_memory_policy,
    transcript_excluded,
)
from ait.redaction import has_redactions, redact_text
from ait.transcript import normalize_transcript, strip_terminal_control


AIT_TRANSCRIPT_FIELD_BUDGET_CHARS = 1_000_000


@dataclass(frozen=True, slots=True)
class SafeTranscriptText:
    text: str
    mode: str
    redacted: bool = False
    excluded_by_memory_policy: bool = False


def persist_agent_transcript_safely(
    repo_root: Path,
    *,
    attempt_id: str,
    source_path: str | None,
    source_kind: str,
) -> str | None:
    """Persist an upstream agent transcript as the safe trace ref.

    The raw upstream transcript is not retained by default. The persisted
    transcript is either redacted text or a policy-excluded marker so downstream
    memory/report/review paths can keep using raw_trace_ref without reading
    secret-bearing source files.
    """
    if not source_path:
        return None
    root = Path(repo_root).resolve()
    src = Path(source_path)
    if not src.is_absolute():
        candidate = root / src
        src = candidate if candidate.exists() else src
    if not src.exists() or not src.is_file():
        return None
    try:
        raw_text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    safe = _safe_transcript_text(
        raw_text,
        repo_root=root,
        attempt_id=attempt_id,
        source_kind=source_kind,
    )
    dest_dir = root / ".ait" / "transcripts" / "redacted"
    suffix = src.suffix or ".jsonl"
    dest = dest_dir / f"{_safe_trace_name(attempt_id)}{suffix}"
    metadata_path = dest.with_name(dest.name + ".meta.json")
    metadata = {
        "schema": "ait.safe_transcript",
        "schema_version": 1,
        "attempt_id": attempt_id,
        "source_kind": source_kind,
        "redacted": safe.redacted,
        "excluded_by_memory_policy": safe.excluded_by_memory_policy,
        "raw_retained": False,
    }
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(safe.text, encoding="utf-8")
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return None
    return dest.relative_to(root).as_posix()


def read_agent_transcript_safely(
    repo_root: Path,
    raw_trace_ref: str,
    *,
    limit: int = 4000,
) -> SafeTranscriptText:
    """Read a trace ref for downstream context without exposing raw secrets."""
    if not raw_trace_ref:
        return SafeTranscriptText(text="", mode="none")
    root = Path(repo_root).resolve()
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = root / path
    normalized_path = path.parent / "normalized" / path.name
    original_redacted = False
    if normalized_path.exists():
        original_redacted = _trace_has_redaction_metadata(path)
        path = normalized_path
        mode = "normalized"
    elif _is_redacted_transcript_path(path, root):
        mode = "redacted"
    else:
        mode = "raw"
    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return SafeTranscriptText(text="", mode="missing")

    safe = _safe_transcript_text(raw_text, repo_root=root)
    if safe.excluded_by_memory_policy:
        mode = "excluded"
    elif safe.redacted and mode == "raw":
        mode = "redacted"
    text = safe.text
    if len(text) > limit:
        text = text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"
    return SafeTranscriptText(
        text=text,
        mode=mode,
        redacted=safe.redacted or original_redacted,
        excluded_by_memory_policy=safe.excluded_by_memory_policy,
    )


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


def _safe_transcript_text(
    text: str,
    *,
    repo_root: Path,
    attempt_id: str | None = None,
    source_kind: str | None = None,
) -> SafeTranscriptText:
    normalized = _strip_terminal_control(text)
    policy = None
    try:
        policy = load_memory_policy(repo_root)
    except ValueError:
        if not (repo_root / ".git").exists():
            policy = default_memory_policy()
    except Exception:
        policy = None
    if policy is None or _trace_marked_excluded(normalized) or transcript_excluded(normalized, policy):
        header = [
            "AIT Agent Transcript",
        ]
        if attempt_id:
            header.append(f"Attempt-Id: {attempt_id}")
        if source_kind:
            header.append(f"Source-Kind: {source_kind}")
        header.extend(
            [
                "Excluded-By-Memory-Policy: true",
                "",
                EXCLUDED_MARKER,
            ]
        )
        return SafeTranscriptText(
            text="\n".join(header),
            mode="excluded",
            redacted=False,
            excluded_by_memory_policy=True,
        )
    redacted_text, redacted = redact_text(normalized)
    return SafeTranscriptText(
        text=redacted_text,
        mode="redacted" if redacted else "raw",
        redacted=redacted or has_redactions(normalized) or "Redacted: true" in normalized,
        excluded_by_memory_policy=False,
    )


def _trace_marked_excluded(text: str) -> bool:
    return "Excluded-By-Memory-Policy: true" in text or EXCLUDED_MARKER in text


def _is_redacted_transcript_path(path: Path, repo_root: Path) -> bool:
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    return relative.startswith(".ait/transcripts/redacted/")


def _trace_has_redaction_metadata(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return has_redactions(text) or "Redacted: true" in text


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
