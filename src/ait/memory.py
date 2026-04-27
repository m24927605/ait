from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import sqlite3

from ait.db import connect_db, run_migrations
from ait.repo import resolve_repo_root


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
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "recent_attempts": [asdict(attempt) for attempt in self.recent_attempts],
            "hot_files": list(self.hot_files),
            "recommendations": list(self.recommendations),
        }


def build_repo_memory(repo_root: str | Path, *, limit: int = 8) -> RepoMemory:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return build_repo_memory_with_connection(conn, repo_root=root, limit=limit)
    finally:
        conn.close()


def build_repo_memory_with_connection(
    conn: sqlite3.Connection,
    *,
    repo_root: str | Path,
    limit: int = 8,
) -> RepoMemory:
    attempts = tuple(_recent_attempts(conn, limit=limit))
    hot_files = _hot_files(conn, limit=10)
    return RepoMemory(
        repo_root=str(Path(repo_root).resolve()),
        recent_attempts=attempts,
        hot_files=hot_files,
        recommendations=_recommendations(attempts, hot_files),
    )


def render_repo_memory_text(memory: RepoMemory) -> str:
    lines = [
        "AIT Long-Term Repo Memory",
        f"Repo: {memory.repo_root}",
        "",
        "Recent Attempts:",
    ]
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
    return "\n".join(lines) + "\n"


def _recent_attempts(conn: sqlite3.Connection, *, limit: int) -> list[MemoryAttempt]:
    rows = conn.execute(
        """
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
        ORDER BY a.started_at DESC, a.ordinal DESC
        LIMIT ?
        """,
        (limit,),
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


def _hot_files(conn: sqlite3.Connection, *, limit: int) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path, COUNT(*) AS touch_count
        FROM evidence_files
        WHERE kind IN ('changed', 'touched')
        GROUP BY file_path
        ORDER BY touch_count DESC, file_path ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows)


def _recommendations(
    attempts: tuple[MemoryAttempt, ...],
    hot_files: tuple[str, ...],
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
    return tuple(items)
