from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import uuid

from ait.db import connect_db, insert_memory_retrieval_event, run_migrations, utc_now
from ait.db.repositories import NewMemoryFact, NewMemoryRetrievalEvent, upsert_memory_fact

from .models import MemoryNote


@dataclass(frozen=True, slots=True)
class MemoryRepository:
    conn: sqlite3.Connection
    root: Path

    def add_note(self, *, body: str, topic: str | None = None, source: str = "manual") -> MemoryNote:
        note = MemoryNote(
            id=f"note:{uuid.uuid4().hex}",
            topic=topic,
            body=body,
            source=source,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO memory_notes(id, created_at, updated_at, topic, body, source, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (note.id, note.created_at, note.updated_at, note.topic, note.body, note.source),
            )
        return note

    def active_source_exists(self, source: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM memory_notes
            WHERE active = 1 AND source = ?
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        return row is not None

    def remove_note(self, *, note_id: str) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE memory_notes
                SET active = 0, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (utc_now(), note_id),
            )
        return cursor.rowcount > 0

    def all_active_notes(self) -> tuple[MemoryNote, ...]:
        rows = self.conn.execute(
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

    def agent_memory_sources(self) -> tuple[str, ...]:
        rows = self.conn.execute(
            """
            SELECT source
            FROM memory_notes
            WHERE active = 1 AND topic = 'agent-memory' AND source LIKE 'agent-memory:%'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        return tuple(str(row["source"]) for row in rows)

    def imported_agent_memory_bodies(self) -> set[str]:
        rows = self.conn.execute(
            """
            SELECT body
            FROM memory_notes
            WHERE active = 1 AND source LIKE 'agent-memory:%'
            """
        ).fetchall()
        return {str(row["body"]) for row in rows}

    def intent_fields(self, intent_id: str) -> dict[str, str]:
        if not intent_id:
            return {}
        row = self.conn.execute(
            """
            SELECT title, kind, description
            FROM intents
            WHERE id = ?
            """,
            (intent_id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "title": str(row["title"]),
            "kind": str(row["kind"] or ""),
            "description": str(row["description"] or ""),
        }

    def upsert_candidate_fact(
        self,
        fact: NewMemoryFact,
    ) -> None:
        upsert_memory_fact(self.conn, fact)

    def insert_retrieval_event(self, event: NewMemoryRetrievalEvent) -> None:
        insert_memory_retrieval_event(self.conn, event)


@contextmanager
def open_memory_repository(root: Path):
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        yield MemoryRepository(conn=conn, root=root)
    finally:
        conn.close()
