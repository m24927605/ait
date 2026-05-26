from __future__ import annotations

import sqlite3
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ait.db.core as db_core
from ait.db import (
    SCHEMA_VERSION,
    backfill_attempt_identities,
    connect_db,
    get_meta,
    list_attempt_commits,
    list_attempt_identities,
    list_attempt_reviews,
    list_attempts,
    list_memory_facts,
    run_migrations,
    set_meta,
)
from ait.query import execute_query

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "db_migrations"


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
                    "attempt_reviews",
                    "attempt_review_findings",
                    "attempt_review_overrides",
                    "attempt_identities",
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

    def test_migrates_v8_populated_db_preserving_attempts(self) -> None:
        with self._fixture_db("v8_populated.sqlite3") as db_path:
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            run_migrations(conn)

            self.assertEqual(str(SCHEMA_VERSION), get_meta(conn, "schema_version"))
            attempts = list_attempts(conn)
            self.assertEqual(
                ["fixture:attempt-1", "fixture:attempt-2"],
                [attempt.id for attempt in attempts],
            )
            commits = list_attempt_commits(conn, "fixture:attempt-1")
            self.assertEqual(["2" * 40], [commit.commit_oid for commit in commits])
            self.assertEqual(
                ("src/calculator.py", "tests/test_calculator.py"),
                commits[0].touched_files,
            )
            self.assertEqual(
                1,
                len(list_attempt_reviews(conn, target_attempt_id="fixture:attempt-1")),
            )
            self.assertEqual(
                ["fixture:fact-1", "fixture:fact-2"],
                sorted(fact.id for fact in list_memory_facts(conn)),
            )

    def test_migrates_v9_populated_db_preserving_identities(self) -> None:
        with self._fixture_db("v9_populated.sqlite3") as db_path:
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            before = self._identity_snapshot(
                conn, ("fixture:attempt-1", "fixture:attempt-2")
            )
            run_migrations(conn)
            backfilled = backfill_attempt_identities(conn)
            after = self._identity_snapshot(
                conn, ("fixture:attempt-1", "fixture:attempt-2")
            )

            self.assertEqual(0, backfilled)
            self.assertEqual(str(SCHEMA_VERSION), get_meta(conn, "schema_version"))
            self.assertEqual(before, after)
            self.assertEqual(("a1", "a2"), tuple(item[0] for item in after.values()))

    def test_migrated_db_supports_core_queries(self) -> None:
        with self._fixture_db("v8_populated.sqlite3") as db_path:
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            run_migrations(conn)
            self.assertEqual(2, backfill_attempt_identities(conn))

            attempts = execute_query(
                conn,
                "attempt",
                'kind="bugfix" AND files_changed~"src/calculator.py"',
            )
            reviewable = execute_query(conn, "attempt", 'review.status="passed"')
            intent_rows = execute_query(conn, "intent", 'observed.tests_passed>0')
            identities = list_attempt_identities(
                conn, ("fixture:attempt-1", "fixture:attempt-2")
            )

            self.assertEqual(["fixture:attempt-1"], [row["id"] for row in attempts])
            self.assertEqual(["fixture:attempt-1"], [row["id"] for row in reviewable])
            self.assertEqual(["fixture:intent-1"], [row["id"] for row in intent_rows])
            self.assertEqual(
                {"fixture:attempt-1": "a1", "fixture:attempt-2": "a2"},
                {
                    attempt_id: identity.handle
                    for attempt_id, identity in identities.items()
                },
            )

    def test_migration_failure_rolls_back(self) -> None:
        with self._fixture_db("v8_populated.sqlite3") as db_path:
            conn = connect_db(db_path)
            self.addCleanup(conn.close)

            with patch.object(
                db_core,
                "_execute_migration_sql",
                side_effect=sqlite3.OperationalError("fixture migration failed"),
            ):
                with self.assertRaises(sqlite3.OperationalError):
                    run_migrations(conn)

            self.assertEqual("8", get_meta(conn, "schema_version"))
            versions = {
                int(row["version"])
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            self.assertEqual(set(range(1, 9)), versions)
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertNotIn("attempt_identities", tables)
            self.assertNotIn("attempt_aliases", tables)

    def test_run_migrations_rejects_newer_schema_version(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE sentinel (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO sentinel(id) VALUES ('unchanged')")
        set_meta(conn, "schema_version", str(SCHEMA_VERSION + 1))
        conn.commit()
        self.addCleanup(conn.close)

        with self.assertRaises(RuntimeError):
            run_migrations(conn)

        self.assertEqual(str(SCHEMA_VERSION + 1), get_meta(conn, "schema_version"))
        self.assertEqual(
            ["unchanged"],
            [row["id"] for row in conn.execute("SELECT id FROM sentinel")],
        )
        self.assertEqual(
            0,
            conn.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()[
                "count"
            ],
        )
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertNotIn("attempts", tables)

    def _fixture_db(self, fixture_name: str):
        class FixtureContext:
            def __enter__(self_inner) -> Path:
                self_inner.tmp = tempfile.TemporaryDirectory()
                db_path = Path(self_inner.tmp.name) / "state.sqlite3"
                shutil.copy2(FIXTURE_DIR / fixture_name, db_path)
                return db_path

            def __exit__(self_inner, *_exc: object) -> None:
                self_inner.tmp.cleanup()

        return FixtureContext()

    def _identity_snapshot(
        self, conn: sqlite3.Connection, attempt_ids: tuple[str, ...]
    ) -> dict[str, tuple[str, str, str]]:
        identities = list_attempt_identities(conn, attempt_ids)
        return {
            attempt_id: (
                identity.handle,
                identity.deterministic_description,
                identity.description_fingerprint,
            )
            for attempt_id, identity in sorted(identities.items())
        }


if __name__ == "__main__":
    unittest.main()
