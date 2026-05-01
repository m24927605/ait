from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from ait.db import connect_db, insert_memory_retrieval_event, run_migrations, utc_now
from ait.db.repositories import NewMemoryFact, NewMemoryRetrievalEvent, upsert_memory_fact
from ait.memory_policy import (
    EXCLUDED_MARKER,
    MemoryPolicy,
    default_memory_policy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
    transcript_excluded,
)
from ait.redaction import has_redactions, redact_text
from ait.repo import resolve_repo_root
from ait.workspace import commit_message

from .models import (
    AgentMemoryStatus,
    MemoryAttempt,
    MemoryCandidate,
    MemoryHealth,
    MemoryImportResult,
    MemoryLintFix,
    MemoryLintIssue,
    MemoryLintResult,
    MemoryNote,
    MemorySearchResult,
    RelevantMemoryItem,
    RelevantMemoryRecall,
    RepoMemory,
)

def _attempt_memory_note_advisory(source: str, text: str) -> bool:
    if not source.startswith("attempt-memory:"):
        return False
    return "confidence=advisory" in text or any(
        f"verified_status={status}" in text
        for status in ("failed", "failed_interrupted", "needs_review")
    )

def _attempt_memory_note_field(text: str, key: str) -> str:
    match = re.search(rf"(?:^|\s){re.escape(key)}=([^\s]+)", text)
    return match.group(1) if match else ""

def _trace_excluded(trace_text: str, *, policy: MemoryPolicy) -> bool:
    return (
        "Excluded-By-Memory-Policy: true" in trace_text
        or EXCLUDED_MARKER in trace_text
        or transcript_excluded(trace_text, policy)
    )

def _read_trace_text(raw_trace_ref: str, *, repo_root: Path, limit: int = 4000) -> str:
    if not raw_trace_ref:
        return ""
    path = _normalized_trace_path(raw_trace_ref, repo_root=repo_root)
    if path is None:
        path = Path(raw_trace_ref)
        if not path.is_absolute():
            path = repo_root / path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""

def _normalized_trace_path(raw_trace_ref: str, *, repo_root: Path) -> Path | None:
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = repo_root / path
    normalized_path = path.parent / "normalized" / path.name
    return normalized_path if normalized_path.exists() else None

def _terms(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    tokens = re.findall(r"[A-Za-z0-9_./:-]+|[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]", lowered)
    cjk_chars = [token for token in tokens if len(token) == 1 and re.fullmatch(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]", token)]
    bigrams = [left + right for left, right in zip(cjk_chars, cjk_chars[1:])]
    return tuple(tokens + bigrams)

def _normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", normalized).strip()

def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\u3040" <= char <= "\u30ff"
        or "\uac00" <= char <= "\ud7af"
        for char in text
    )

def _should_prefer_literal(query: str) -> bool:
    normalized = _normalize_search_text(query)
    return _contains_cjk(normalized)

def _literal_snippet(text: str, normalized_query: str, *, radius: int = 80) -> str:
    normalized_text = _normalize_search_text(text)
    match_start = normalized_text.find(normalized_query)
    if match_start < 0:
        return _compact_line(text)
    start = max(0, match_start - radius)
    end = min(len(normalized_text), match_start + len(normalized_query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(normalized_text) else ""
    return prefix + normalized_text[start:end] + suffix

def _compact_line(text: str, *, limit: int = 180) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."
