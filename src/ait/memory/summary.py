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

from .common import _attempt_memory_note_advisory

def build_repo_memory(
    repo_root: str | Path,
    *,
    limit: int = 8,
    path_filter: str | None = None,
    topic: str | None = None,
    promoted_only: bool = False,
) -> RepoMemory:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return build_repo_memory_with_connection(
            conn,
            repo_root=root,
            limit=limit,
            path_filter=path_filter,
            topic=topic,
            promoted_only=promoted_only,
            policy=policy,
        )
    finally:
        conn.close()

def build_repo_memory_with_connection(
    conn: sqlite3.Connection,
    *,
    repo_root: str | Path,
    limit: int = 8,
    path_filter: str | None = None,
    topic: str | None = None,
    promoted_only: bool = False,
    policy: MemoryPolicy | None = None,
) -> RepoMemory:
    resolved_policy = policy or default_memory_policy()
    attempts = tuple(
        _recent_attempts(
            conn,
            limit=limit,
            path_filter=path_filter,
            promoted_only=promoted_only,
            policy=resolved_policy,
        )
    )
    hot_files = _hot_files(conn, limit=10, path_filter=path_filter, policy=resolved_policy)
    notes = _memory_notes(conn, limit=limit, topic=topic)
    return RepoMemory(
        repo_root=str(Path(repo_root).resolve()),
        recent_attempts=attempts,
        hot_files=hot_files,
        notes=notes,
        recommendations=_recommendations(attempts, hot_files, notes),
    )

def render_repo_memory_text(
    memory: RepoMemory,
    *,
    budget_chars: int | None = None,
    include_advisory_attempt_memory: bool = True,
) -> str:
    notes = (
        memory.notes
        if include_advisory_attempt_memory
        else tuple(
            note
            for note in memory.notes
            if not _attempt_memory_note_advisory(note.source, note.body)
        )
    )
    lines = [
        "AIT Long-Term Repo Memory",
        f"Repo: {memory.repo_root}",
        "",
        "Curated Notes:",
    ]
    if not notes:
        lines.append("- none")
    for note in notes:
        body, redacted = redact_text(note.body)
        topic = note.topic if note.topic else "general"
        lines.append(f"- {note.id} topic={topic} source={note.source}")
        lines.append(f"  {body}")
        if redacted:
            lines.append("  redacted: true")

    lines.extend(
        [
            "",
            "Recent Attempts:",
        ]
    )
    if not memory.recent_attempts:
        lines.append("- none recorded yet")
    for attempt in memory.recent_attempts:
        lines.append(
            "- "
            f"{attempt.attempt_id} intent={attempt.intent_title!r} "
            f"agent={attempt.agent_id} verified={attempt.verified_status} "
            f"exit={attempt.result_exit_code}"
        )
        if attempt.changed_files:
            lines.append(f"  changed: {', '.join(attempt.changed_files)}")
        if attempt.commit_oids:
            lines.append(f"  commits: {', '.join(attempt.commit_oids)}")

    lines.append("")
    lines.append("Hot Files:")
    if not memory.hot_files:
        lines.append("- none")
    for file_path in memory.hot_files:
        lines.append(f"- {file_path}")

    lines.append("")
    lines.append("Recommended Memory Use:")
    for recommendation in memory.recommendations:
        lines.append(f"- {recommendation}")
    text = "\n".join(lines) + "\n"
    if budget_chars is None or budget_chars <= 0 or len(text) <= budget_chars:
        return text
    marker = "\n[ait memory compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker

def _recent_attempts(
    conn: sqlite3.Connection,
    *,
    limit: int,
    path_filter: str | None,
    promoted_only: bool,
    policy: MemoryPolicy,
) -> list[MemoryAttempt]:
    where = []
    params: list[object] = []
    if promoted_only:
        where.append("a.verified_status = 'promoted'")
    if path_filter:
        where.append(
            """
            EXISTS (
              SELECT 1
              FROM evidence_files AS ef
              WHERE ef.attempt_id = a.id
                AND ef.file_path LIKE ?
            )
            """
        )
        params.append(f"{path_filter}%")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
          a.id AS attempt_id,
          a.agent_id,
          a.verified_status,
          a.result_exit_code,
          a.raw_trace_ref,
          a.started_at,
          i.title AS intent_title,
          i.status AS intent_status
        FROM attempts AS a
        JOIN intents AS i ON i.id = a.intent_id
        {where_sql}
        ORDER BY a.started_at DESC, a.ordinal DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [
        MemoryAttempt(
            intent_title=str(row["intent_title"]),
            intent_status=str(row["intent_status"]),
            attempt_id=str(row["attempt_id"]),
            agent_id=str(row["agent_id"]),
            verified_status=str(row["verified_status"]),
            result_exit_code=row["result_exit_code"],
            started_at=str(row["started_at"]),
            changed_files=_changed_files(conn, str(row["attempt_id"]), policy=policy),
            commit_oids=_commit_oids(conn, str(row["attempt_id"])),
        )
        for row in rows
    ]

def _changed_files(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    policy: MemoryPolicy,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path
        FROM evidence_files
        WHERE attempt_id = ? AND kind = 'changed'
        ORDER BY file_path
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))

def _commit_oids(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT commit_oid
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["commit_oid"]) for row in rows)

def _hot_files(
    conn: sqlite3.Connection,
    *,
    limit: int,
    path_filter: str | None,
    policy: MemoryPolicy,
) -> tuple[str, ...]:
    where = "kind IN ('changed', 'touched')"
    params: list[object] = []
    if path_filter:
        where += " AND file_path LIKE ?"
        params.append(f"{path_filter}%")
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT file_path, COUNT(*) AS touch_count
        FROM evidence_files
        WHERE {where}
        GROUP BY file_path
        ORDER BY touch_count DESC, file_path ASC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))

def _memory_notes(
    conn: sqlite3.Connection,
    *,
    limit: int,
    topic: str | None,
) -> tuple[MemoryNote, ...]:
    where = "active = 1"
    params: list[object] = []
    if topic:
        where += " AND topic = ?"
        params.append(topic)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, topic, body, source, created_at, updated_at
        FROM memory_notes
        WHERE {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return tuple(
        MemoryNote(
            id=str(row["id"]),
            topic=str(row["topic"]) if row["topic"] is not None else None,
            body=str(row["body"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    )

def _recommendations(
    attempts: tuple[MemoryAttempt, ...],
    hot_files: tuple[str, ...],
    notes: tuple[MemoryNote, ...],
) -> tuple[str, ...]:
    items: list[str] = [
        "treat this as external memory; verify current files before editing",
        "prefer continuing from promoted or succeeded attempts over failed attempts",
    ]
    failed = next((attempt for attempt in attempts if attempt.verified_status == "failed"), None)
    if failed is not None:
        items.append(f"review latest failed attempt before repeating work: {failed.attempt_id}")
    if hot_files:
        items.append(f"inspect frequently changed files first: {', '.join(hot_files[:5])}")
    if notes:
        items.append("apply curated notes as stable project guidance unless current files disagree")
    return tuple(items)
