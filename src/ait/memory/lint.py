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

from .common import _terms
from .notes import _all_active_memory_notes, list_memory_notes, remove_memory_note
from .repository import open_memory_repository

def lint_memory_notes(
    repo_root: str | Path,
    *,
    fix: bool = False,
    max_chars: int = 6000,
) -> MemoryLintResult:
    root = resolve_repo_root(repo_root)
    with open_memory_repository(root) as repo:
        notes = _all_active_memory_notes(repo.conn)
        duplicate_ids = _duplicate_memory_note_ids(notes)
        issues: list[MemoryLintIssue] = []
        fixes: list[MemoryLintFix] = []
        for note in notes:
            detected = _lint_one_memory_note(repo.conn, note, duplicate_ids=duplicate_ids, max_chars=max_chars)
            for issue in detected:
                fixed_issue = issue
                if fix and issue.fixable:
                    applied = _apply_memory_lint_fix(repo.conn, note, issue, max_chars=max_chars)
                    if applied is not None:
                        fixes.append(applied)
                        fixed_issue = MemoryLintIssue(
                            code=issue.code,
                            severity=issue.severity,
                            note_id=issue.note_id,
                            source=issue.source,
                            topic=issue.topic,
                            detail=issue.detail,
                            fixable=issue.fixable,
                            fixed=True,
                        )
                issues.append(fixed_issue)
        return MemoryLintResult(checked=len(notes), issues=tuple(issues), fixes=tuple(fixes))

def memory_health_from_lint(result: MemoryLintResult) -> MemoryHealth:
    error_count = len([issue for issue in result.issues if issue.severity == "error"])
    warning_count = len([issue for issue in result.issues if issue.severity == "warning"])
    info_count = len([issue for issue in result.issues if issue.severity == "info"])
    if error_count:
        status = "error"
    elif warning_count:
        status = "warning"
    elif info_count:
        status = "info"
    else:
        status = "ok"
    return MemoryHealth(
        status=status,
        checked=result.checked,
        issue_count=len(result.issues),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
    )

def render_memory_lint_result(result: MemoryLintResult) -> str:
    lines = [
        "AIT memory lint",
        f"Checked: {result.checked}",
        f"Issues: {len(result.issues)}",
        f"Fixes: {len(result.fixes)}",
    ]
    if result.issues:
        lines.append("Issues:")
        for issue in result.issues:
            fixed = " fixed=true" if issue.fixed else ""
            lines.append(
                f"- {issue.severity} {issue.code} note={issue.note_id} "
                f"source={issue.source} fixable={issue.fixable}{fixed}: {issue.detail}"
            )
    if result.fixes:
        lines.append("Fixes:")
        for fix in result.fixes:
            lines.append(f"- {fix.action} note={fix.note_id}: {fix.detail}")
    return "\n".join(lines) + "\n"

def _duplicate_memory_note_ids(notes: tuple[MemoryNote, ...]) -> set[str]:
    seen: dict[tuple[str | None, str], str] = {}
    duplicates: set[str] = set()
    for note in notes:
        key = (note.topic, _normalized_memory_body(note.body))
        if key in seen:
            duplicates.add(note.id)
        else:
            seen[key] = note.id
    return duplicates

def _normalized_memory_body(body: str) -> str:
    return " ".join(body.split()).strip().lower()

def _lint_one_memory_note(
    conn: sqlite3.Connection,
    note: MemoryNote,
    *,
    duplicate_ids: set[str],
    max_chars: int,
) -> tuple[MemoryLintIssue, ...]:
    issues: list[MemoryLintIssue] = []
    redacted, redacted_changed = redact_text(note.body)
    if note.id in duplicate_ids:
        issues.append(_memory_lint_issue(note, "duplicate", "error", "body duplicates an earlier active note", True))
    if max_chars > 0 and len(note.body) > max_chars:
        issues.append(
            _memory_lint_issue(note, "too_long", "warning", f"body has {len(note.body)} chars over {max_chars}", True)
        )
    if redacted_changed and redacted != note.body:
        issues.append(_memory_lint_issue(note, "possible_secret", "error", "body matches a redaction pattern", True))
    if note.source.startswith(("agent-memory:", "attempt-memory:")) and "confidence=" not in note.body:
        issues.append(_memory_lint_issue(note, "missing_confidence", "warning", "managed memory lacks confidence=", False))
    if _low_information_memory_body(note.body):
        issues.append(_memory_lint_issue(note, "low_information", "info", "body is too short or repetitive", False))
    if note.source.startswith("attempt-memory:") and not _attempt_memory_source_exists(conn, note.source):
        issues.append(_memory_lint_issue(note, "stale_attempt_memory", "warning", "source attempt no longer exists", False))
    return tuple(issues)

def _memory_lint_issue(
    note: MemoryNote,
    code: str,
    severity: str,
    detail: str,
    fixable: bool,
) -> MemoryLintIssue:
    return MemoryLintIssue(
        code=code,
        severity=severity,
        note_id=note.id,
        source=note.source,
        topic=note.topic,
        detail=detail,
        fixable=fixable,
    )

def _low_information_memory_body(body: str) -> bool:
    terms = _terms(body)
    if len(body.strip()) < 20 or len(terms) < 3:
        return True
    if terms and max(terms.count(term) for term in set(terms)) / len(terms) > 0.8:
        return True
    return False

def _attempt_memory_source_exists(conn: sqlite3.Connection, source: str) -> bool:
    attempt_id = source.removeprefix("attempt-memory:")
    if not attempt_id:
        return False
    row = conn.execute("SELECT 1 FROM attempts WHERE id = ? LIMIT 1", (attempt_id,)).fetchone()
    return row is not None

def _apply_memory_lint_fix(
    conn: sqlite3.Connection,
    note: MemoryNote,
    issue: MemoryLintIssue,
    *,
    max_chars: int,
) -> MemoryLintFix | None:
    if issue.code == "duplicate":
        with conn:
            conn.execute(
                "UPDATE memory_notes SET active = 0, updated_at = ? WHERE id = ?",
                (utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="deactivate", detail="deactivated duplicate note")
    if issue.code == "possible_secret":
        redacted, _ = redact_text(note.body)
        with conn:
            conn.execute(
                "UPDATE memory_notes SET body = ?, updated_at = ? WHERE id = ?",
                (redacted, utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="redact", detail="redacted matching secret pattern")
    if issue.code == "too_long" and max_chars > 0:
        marker = "\n[ait memory lint compacted]\n"
        keep = max(0, max_chars - len(marker))
        compacted = note.body[:keep].rstrip() + marker
        with conn:
            conn.execute(
                "UPDATE memory_notes SET body = ?, updated_at = ? WHERE id = ?",
                (compacted, utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="compact", detail=f"compacted body to {len(compacted)} chars")
    return None
