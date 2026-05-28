from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3

from ait.bug_report.api import report_internal_error
from ait.db.schema import MIGRATIONS, SCHEMA_VERSION


def connect_db(
    db_path: str | Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    in_memory = str(db_path) == ":memory:"
    if in_memory:
        conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # P1 fix: SQLite creates the .db file inheriting the process
        # umask. On a multi-user host that is often mode 0o644 (or
        # 0o664 on group-writable umasks), exposing the attempt
        # ledger — which carries decision provenance and review
        # findings — to any local account. Constrain creation mode
        # via os.umask while opening, then tighten the file modes
        # explicitly as belt-and-braces for any sidecar files that
        # may pre-date this fix.
        old_umask = os.umask(0o077)
        try:
            conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        finally:
            os.umask(old_umask)
        for candidate in (
            path,
            path.with_name(path.name + "-wal"),
            path.with_name(path.name + "-shm"),
            path.with_name(path.name + "-journal"),
        ):
            try:
                if candidate.exists():
                    candidate.chmod(0o600)
            except OSError:
                pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if not in_memory:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError as exc:
            report_internal_error(category="db.operational", exc=exc)
            if "locked" not in str(exc).lower():
                raise
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO meta(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def run_migrations(conn: sqlite3.Connection) -> None:
    started_transaction = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        existing_version = get_meta(conn, "schema_version")
        if existing_version is not None and int(existing_version) > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema version {existing_version} is newer than supported {SCHEMA_VERSION}"
            )

        applied_versions = {
            int(row["version"])
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue
            _execute_migration_sql(conn, migration.sql)
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, utc_now()),
            )

        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        if started_transaction:
            conn.commit()
    except Exception:
        if started_transaction:
            conn.rollback()
        raise


def _execute_migration_sql(conn: sqlite3.Connection, sql: str) -> None:
    pending: list[str] = []
    for line in sql.splitlines():
        pending.append(line)
        statement = "\n".join(pending).strip()
        if not statement:
            pending.clear()
            continue
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            pending.clear()

    statement = "\n".join(pending).strip()
    if statement:
        conn.execute(statement)
