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
from .repository import MemoryRepository, open_memory_repository
from .summary import _memory_notes

def add_memory_note(
    repo_root: str | Path,
    *,
    body: str,
    topic: str | None = None,
    source: str = "manual",
) -> MemoryNote:
    root = resolve_repo_root(repo_root)
    with open_memory_repository(root) as repo:
        return add_memory_note_with_repository(repo, body=body, topic=topic, source=source)

def add_memory_note_with_repository(
    repo: MemoryRepository,
    *,
    body: str,
    topic: str | None = None,
    source: str = "manual",
) -> MemoryNote:
    return repo.add_note(body=body, topic=topic, source=source)

def list_memory_notes(
    repo_root: str | Path,
    *,
    topic: str | None = None,
    limit: int = 100,
) -> tuple[MemoryNote, ...]:
    root = resolve_repo_root(repo_root)
    with open_memory_repository(root) as repo:
        return _memory_notes(repo.conn, limit=limit, topic=topic)

def remove_memory_note(repo_root: str | Path, *, note_id: str) -> bool:
    root = resolve_repo_root(repo_root)
    with open_memory_repository(root) as repo:
        return repo.remove_note(note_id=note_id)

def _active_memory_source_exists(repo: MemoryRepository, source: str) -> bool:
    return repo.active_source_exists(source)

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
