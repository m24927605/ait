from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from ait.db.schema import MIGRATIONS

FIXTURE_DIR = Path(__file__).resolve().parent
NOW = "2026-05-26T00:00:00Z"


def main() -> int:
    _build_fixture("v8_populated.sqlite3", 8, populated=True, identities=False, aliases=False)
    _build_fixture("v9_populated.sqlite3", 9, populated=True, identities=True, aliases=False)
    _build_fixture("v10_minimal.sqlite3", 10, populated=True, identities=True, aliases=True, minimal=True)
    return 0


def _build_fixture(
    filename: str,
    version: int,
    *,
    populated: bool,
    identities: bool,
    aliases: bool,
    minimal: bool = False,
) -> None:
    path = FIXTURE_DIR / filename
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        for migration in MIGRATIONS:
            if migration.version > version:
                continue
            conn.executescript(migration.sql)
            conn.execute(
                """
                INSERT INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, NOW),
            )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        if populated:
            _seed_populated(conn, version=version, minimal=minimal)
        if identities:
            _seed_identities(conn, minimal=minimal)
        if aliases:
            conn.execute(
                """
                INSERT INTO attempt_aliases(alias, attempt_id, created_at, updated_at)
                VALUES ('fixture-a1', 'fixture:attempt-1', ?, ?)
                """,
                (NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_populated(conn: sqlite3.Connection, *, version: int, minimal: bool) -> None:
    conn.executemany(
        """
        INSERT INTO intents(
            id, schema_version, repo_id, title, description, kind,
            parent_intent_id, root_intent_id, created_at,
            created_by_actor_type, created_by_actor_id, trigger_source,
            trigger_prompt_ref, status, tags_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 'user', 'fixture', 'cli', NULL, ?, ?, '{}')
        """,
        [
            (
                "fixture:intent-1",
                version,
                "repo:fixture",
                "Fix calculator rounding",
                "Synthetic migration fixture intent",
                "bugfix",
                "fixture:intent-1",
                "2026-05-20T10:00:00Z",
                "finished",
                json.dumps(["migration", "fixture"]),
            ),
            (
                "fixture:intent-2",
                version,
                "repo:fixture",
                "Document calculator behavior",
                "Synthetic documentation fixture intent",
                "docs",
                "fixture:intent-2",
                "2026-05-20T11:00:00Z",
                "open",
                json.dumps(["migration", "docs"]),
            ),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO attempts(
            id, schema_version, intent_id, ordinal, agent_id, agent_model,
            agent_harness, agent_harness_version, workspace_kind, workspace_ref,
            base_ref_oid, base_ref_name, started_at, ended_at, heartbeat_at,
            reported_status, verified_status, ownership_token, raw_trace_ref,
            logs_ref, result_promotion_ref, result_exit_code
        )
        VALUES (?, ?, ?, ?, ?, ?, 'codex', 'fixture', 'worktree', ?, ?, 'main', ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
        """,
        [
            (
                "fixture:attempt-1",
                version,
                "fixture:intent-1",
                1,
                "codex:fixture-1",
                "gpt-fixture",
                ".ait/workspaces/fixture-a1",
                "0" * 40,
                "2026-05-20T10:05:00Z",
                "2026-05-20T10:20:00Z",
                "2026-05-20T10:19:00Z",
                "finished",
                "succeeded",
                "fixture-token-1",
                0,
            ),
            (
                "fixture:attempt-2",
                version,
                "fixture:intent-2",
                1,
                "codex:fixture-2",
                "gpt-fixture",
                ".ait/workspaces/fixture-a2",
                "1" * 40,
                "2026-05-20T11:05:00Z",
                None,
                "2026-05-20T11:15:00Z",
                "running",
                "pending",
                "fixture-token-2",
                None,
            ),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO evidence_summaries(
            id, schema_version, attempt_id, observed_tool_calls,
            observed_file_reads, observed_file_writes, observed_commands_run,
            observed_duration_ms, observed_tests_run, observed_tests_passed,
            observed_tests_failed, observed_lint_passed, observed_build_passed,
            raw_prompt_ref, raw_trace_ref, logs_ref
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """,
        [
            ("fixture:evidence-1", version, "fixture:attempt-1", 4, 2, 1, 2, 9000, 3, 3, 0, 1, 1),
            ("fixture:evidence-2", version, "fixture:attempt-2", 1, 1, 0, 1, 3000, 0, 0, 0, None, None),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO attempt_commits(
            attempt_id, commit_oid, base_commit_oid, insertions, deletions,
            touched_files_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "fixture:attempt-1",
                "2" * 40,
                "0" * 40,
                12,
                3,
                json.dumps(["src/calculator.py", "tests/test_calculator.py"]),
            ),
            (
                "fixture:attempt-2",
                "3" * 40,
                "1" * 40,
                4,
                0,
                json.dumps(["docs/calculator.md"]),
            ),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO evidence_files(attempt_id, file_path, kind)
        VALUES (?, ?, ?)
        """,
        [
            ("fixture:attempt-1", "src/calculator.py", "changed"),
            ("fixture:attempt-1", "tests/test_calculator.py", "changed"),
            ("fixture:attempt-1", "src/calculator.py", "touched"),
            ("fixture:attempt-2", "docs/calculator.md", "touched"),
        ][:3 if minimal else 4],
    )
    conn.execute(
        """
        INSERT INTO attempt_outcomes(
            attempt_id, schema_version, outcome_class, confidence,
            reasons_json, classified_at
        )
        VALUES ('fixture:attempt-1', ?, 'succeeded', 'high', ?, ?)
        """,
        (version, json.dumps(["fixture completed"]), NOW),
    )
    conn.executemany(
        """
        INSERT INTO memory_notes(id, created_at, updated_at, topic, body, source, active)
        VALUES (?, ?, ?, ?, ?, 'fixture', 1)
        """,
        [
            ("fixture:note-1", NOW, NOW, "calculator", "Synthetic note about rounding."),
            ("fixture:note-2", NOW, NOW, "docs", "Synthetic note about docs."),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO memory_facts(
            id, schema_version, kind, topic, body, summary, status, confidence,
            source_attempt_id, source_trace_ref, source_commit_oid,
            source_file_path, valid_from, valid_to, superseded_by,
            created_at, updated_at, human_review_state, provenance
        )
        VALUES (?, ?, ?, ?, ?, ?, 'accepted', 'high', ?, NULL, ?, ?, ?, NULL, NULL, ?, ?, 'approved', 'manual')
        """,
        [
            (
                "fixture:fact-1",
                version,
                "decision",
                "calculator",
                "Calculator rounding uses bankers rounding in fixtures.",
                "Use bankers rounding.",
                "fixture:attempt-1",
                "2" * 40,
                "src/calculator.py",
                "2026-05-20T10:20:00Z",
                NOW,
                NOW,
            ),
            (
                "fixture:fact-2",
                version,
                "workflow",
                "docs",
                "Fixture docs should stay synthetic.",
                "Keep docs synthetic.",
                "fixture:attempt-2",
                "3" * 40,
                "docs/calculator.md",
                "2026-05-20T11:20:00Z",
                NOW,
                NOW,
            ),
        ][:1 if minimal else 2],
    )
    conn.executemany(
        """
        INSERT INTO memory_fact_entities(memory_fact_id, entity, entity_type, weight)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("fixture:fact-1", "calculator", "module", 1.0),
            ("fixture:fact-2", "docs", "area", 0.7),
        ][:1 if minimal else 2],
    )
    if not minimal:
        conn.execute(
            """
            INSERT INTO memory_fact_edges(
                id, source_fact_id, target_fact_id, edge_type, confidence, created_at
            )
            VALUES ('fixture:edge-1', 'fixture:fact-2', 'fixture:fact-1', 'related_to', 'medium', ?)
            """,
            (NOW,),
        )
    conn.execute(
        """
        INSERT INTO memory_retrieval_events(
            id, attempt_id, query, selected_fact_ids_json, ranker_version,
            budget_chars, created_at
        )
        VALUES ('fixture:retrieval-1', 'fixture:attempt-1', 'calculator rounding', ?, 'fixture-ranker', 1200, ?)
        """,
        (json.dumps(["fixture:fact-1"]), NOW),
    )
    if minimal:
        return
    conn.execute(
        """
        INSERT INTO attempt_reviews(
            id, target_attempt_id, review_attempt_id, mode, budget,
            profiles_json, reviewer_adapter, reviewer_agent_id, risk_level,
            risk_score, risk_reasons_json, status, blocking, artifact_ref,
            baseline_ref, target_head_oid, base_ref_oid, policy_hash,
            baseline_policy_hash, reviewer_model, created_at, completed_at, summary
        )
        VALUES (
            'fixture:review-1', 'fixture:attempt-1', NULL, 'light', 'quick',
            ?, 'fake:pass', 'codex:reviewer', 'low', 10, ?, 'passed', 0,
            '.ait/reviews/fixture-review.json', '.ait/reviews/baseline.json',
            ?, ?, 'fixture-policy', 'fixture-baseline-policy',
            'fixture-reviewer-model', ?, ?, 'Synthetic fixture review passed.'
        )
        """,
        (
            json.dumps(["security"]),
            json.dumps([{"reason": "synthetic fixture"}]),
            "2" * 40,
            "0" * 40,
            NOW,
            NOW,
        ),
    )
    conn.execute(
        """
        INSERT INTO attempt_review_findings(
            id, review_id, severity, blocking, lifecycle_status, path,
            line, hunk_ref, title, body, evidence_ref, suggested_test,
            confidence
        )
        VALUES (
            'fixture:finding-1', 'fixture:review-1', 'low', 0, 'fixed',
            'src/calculator.py', 12, NULL, 'Synthetic review finding',
            'Fixture-only finding for migration coverage.', NULL,
            'Run tests/test_calculator.py', 'high'
        )
        """
    )


def _seed_identities(conn: sqlite3.Connection, *, minimal: bool) -> None:
    conn.executemany(
        """
        INSERT INTO attempt_identities(
            attempt_id, handle_index, handle, display_title,
            deterministic_description, description_source,
            description_fingerprint, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'fixture:v9', ?, ?, ?)
        """,
        [
            (
                "fixture:attempt-1",
                1,
                "a1",
                "Fix calculator rounding",
                "Fix calculator rounding\n\nChanged: src/calculator.py, tests/test_calculator.py",
                "fixture-fingerprint-1",
                NOW,
                NOW,
            ),
            (
                "fixture:attempt-2",
                2,
                "a2",
                "Document calculator behavior",
                "Document calculator behavior\n\nChanged: docs/calculator.md",
                "fixture-fingerprint-2",
                NOW,
                NOW,
            ),
        ][:1 if minimal else 2],
    )


if __name__ == "__main__":
    raise SystemExit(main())
