from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import sqlite3
import uuid

from ait.db import connect_db, run_migrations, utc_now
from ait.repo import resolve_repo_root


@dataclass(frozen=True, slots=True)
class MemoryNote:
    id: str
    topic: str | None
    body: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MemoryAttempt:
    intent_title: str
    intent_status: str
    attempt_id: str
    agent_id: str
    verified_status: str
    result_exit_code: int | None
    started_at: str
    changed_files: tuple[str, ...]
    commit_oids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepoMemory:
    repo_root: str
    recent_attempts: tuple[MemoryAttempt, ...]
    hot_files: tuple[str, ...]
    notes: tuple[MemoryNote, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "recent_attempts": [asdict(attempt) for attempt in self.recent_attempts],
            "hot_files": list(self.hot_files),
            "notes": [asdict(note) for note in self.notes],
            "recommendations": list(self.recommendations),
        }


def build_repo_memory(
    repo_root: str | Path,
    *,
    limit: int = 8,
    path_filter: str | None = None,
    topic: str | None = None,
    promoted_only: bool = False,
) -> RepoMemory:
    root = resolve_repo_root(repo_root)
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
) -> RepoMemory:
    attempts = tuple(
        _recent_attempts(
            conn,
            limit=limit,
            path_filter=path_filter,
            promoted_only=promoted_only,
        )
    )
    hot_files = _hot_files(conn, limit=10, path_filter=path_filter)
    notes = _memory_notes(conn, limit=limit, topic=topic)
    return RepoMemory(
        repo_root=str(Path(repo_root).resolve()),
        recent_attempts=attempts,
        hot_files=hot_files,
        notes=notes,
        recommendations=_recommendations(attempts, hot_files, notes),
    )


def render_repo_memory_text(memory: RepoMemory, *, budget_chars: int | None = None) -> str:
    lines = [
        "AIT Long-Term Repo Memory",
        f"Repo: {memory.repo_root}",
        "",
        "Curated Notes:",
    ]
    if not memory.notes:
        lines.append("- none")
    for note in memory.notes:
        topic = note.topic if note.topic else "general"
        lines.append(f"- {note.id} topic={topic} source={note.source}")
        lines.append(f"  {note.body}")

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


def _recent_attempts(
    conn: sqlite3.Connection,
    *,
    limit: int,
    path_filter: str | None,
    promoted_only: bool,
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
            changed_files=_changed_files(conn, str(row["attempt_id"])),
            commit_oids=_commit_oids(conn, str(row["attempt_id"])),
        )
        for row in rows
    ]


def _changed_files(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path
        FROM evidence_files
        WHERE attempt_id = ? AND kind = 'changed'
        ORDER BY file_path
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows)


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
    return tuple(str(row["file_path"]) for row in rows)


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
