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
from .summary import _memory_notes

def add_memory_note(
    repo_root: str | Path,
    *,
    body: str,
    topic: str | None = None,
    source: str = "manual",
) -> MemoryNote:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        note = MemoryNote(
            id=f"note:{uuid.uuid4().hex}",
            topic=topic,
            body=body,
            source=source,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with conn:
            conn.execute(
                """
                INSERT INTO memory_notes(id, created_at, updated_at, topic, body, source, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (note.id, note.created_at, note.updated_at, note.topic, note.body, note.source),
            )
        return note
    finally:
        conn.close()

def list_memory_notes(
    repo_root: str | Path,
    *,
    topic: str | None = None,
    limit: int = 100,
) -> tuple[MemoryNote, ...]:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return _memory_notes(conn, limit=limit, topic=topic)
    finally:
        conn.close()

def remove_memory_note(repo_root: str | Path, *, note_id: str) -> bool:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        with conn:
            cursor = conn.execute(
                """
                UPDATE memory_notes
                SET active = 0, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (utc_now(), note_id),
            )
        return cursor.rowcount > 0
    finally:
        conn.close()

def _active_memory_source_exists(root: Path, source: str) -> bool:
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        row = conn.execute(
            """
            SELECT 1
            FROM memory_notes
            WHERE active = 1 AND source = ?
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()

def _all_active_memory_notes(conn: sqlite3.Connection) -> tuple[MemoryNote, ...]:
    rows = conn.execute(
        """
        SELECT id, topic, body, source, created_at, updated_at
        FROM memory_notes
        WHERE active = 1
        ORDER BY created_at ASC, id ASC
        """
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
