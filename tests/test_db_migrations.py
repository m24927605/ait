from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.db import SCHEMA_VERSION, connect_db, get_meta, run_migrations, set_meta


class MigrationTests(unittest.TestCase):
    def test_run_migrations_creates_expected_tables_and_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".ait" / "ait.sqlite3"
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            run_migrations(conn)

            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            self.assertTrue(
                {
                    "meta",
                    "schema_migrations",
                    "intents",
                    "attempts",
                    "evidence_summaries",
                    "intent_edges",
                    "attempt_commits",
                    "evidence_files",
                }.issubset(tables)
            )
            self.assertEqual(str(SCHEMA_VERSION), get_meta(conn, "schema_version"))

    def test_run_migrations_is_idempotent(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)
        first_count = conn.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]
        run_migrations(conn)
        second_count = conn.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]

        self.assertEqual(SCHEMA_VERSION, first_count)
        self.assertEqual(first_count, second_count)

    def test_intent_edges_has_child_reverse_index(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)

        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'intent_edges'"
            ).fetchall()
        }
        self.assertIn("idx_intent_edges_child", indexes)

    def test_run_migrations_rejects_newer_schema_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        set_meta(conn, "schema_version", str(SCHEMA_VERSION + 1))
        self.addCleanup(conn.close)

        with self.assertRaises(RuntimeError):
            run_migrations(conn)


if __name__ == "__main__":
    unittest.main()
