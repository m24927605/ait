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
                    "memory_notes",
                    "attempt_outcomes",
                    "memory_facts",
                    "memory_fact_entities",
                    "memory_fact_edges",
                    "memory_retrieval_events",
                }.issubset(tables)
            )
            self.assertEqual(str(SCHEMA_VERSION), get_meta(conn, "schema_version"))

    def test_file_db_uses_wal_and_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".ait" / "ait.sqlite3"
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]

            self.assertEqual("wal", str(journal_mode).lower())
            self.assertEqual(5000, busy_timeout)
            self.assertEqual(1, synchronous)

    def test_memory_db_skips_wal_but_uses_busy_timeout(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual("memory", str(journal_mode).lower())
        self.assertEqual(5000, busy_timeout)

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

    def test_attempts_has_no_dead_result_patch_refs_column(self) -> None:
        # Regression for Finding #9: result_patch_refs_json was schema
        # bloat — no reader or writer ever touched it. Migration v3 drops
        # the column.
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(attempts)").fetchall()
        }
        self.assertNotIn("result_patch_refs_json", columns)

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

    def test_memory_notes_has_active_topic_index(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)

        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'memory_notes'"
            ).fetchall()
        }
        self.assertIn("idx_memory_notes_active_topic_updated_at", indexes)

    def test_attempt_outcomes_has_class_index(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)

        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'attempt_outcomes'"
            ).fetchall()
        }
        self.assertIn("idx_attempt_outcomes_class_classified_at", indexes)

    def test_temporal_memory_tables_have_expected_indexes(self) -> None:
        conn = connect_db(":memory:")
        self.addCleanup(conn.close)

        run_migrations(conn)

        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        self.assertIn("idx_memory_facts_status_kind_updated_at", indexes)
        self.assertIn("idx_memory_facts_topic_status_updated_at", indexes)
        self.assertIn("idx_memory_facts_source_attempt", indexes)
        self.assertIn("idx_memory_fact_entities_entity", indexes)
        self.assertIn("idx_memory_fact_entities_type_entity", indexes)
        self.assertIn("idx_memory_fact_edges_source", indexes)
        self.assertIn("idx_memory_fact_edges_target", indexes)
        self.assertIn("idx_memory_retrieval_events_attempt", indexes)

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
