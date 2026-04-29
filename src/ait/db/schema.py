from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 5


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_schema",
        sql="""
        CREATE TABLE intents (
            id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            repo_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            kind TEXT,
            parent_intent_id TEXT REFERENCES intents(id),
            root_intent_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by_actor_type TEXT NOT NULL,
            created_by_actor_id TEXT NOT NULL,
            trigger_source TEXT NOT NULL,
            trigger_prompt_ref TEXT,
            status TEXT NOT NULL CHECK (status IN ('open', 'running', 'finished', 'abandoned', 'superseded')),
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX idx_intents_status_created_at
            ON intents(status, created_at);
        CREATE INDEX idx_intents_kind_created_at
            ON intents(kind, created_at);

        CREATE TABLE attempts (
            id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            agent_model TEXT,
            agent_harness TEXT,
            agent_harness_version TEXT,
            workspace_kind TEXT NOT NULL CHECK (workspace_kind = 'worktree'),
            workspace_ref TEXT NOT NULL,
            base_ref_oid TEXT NOT NULL,
            base_ref_name TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            heartbeat_at TEXT,
            reported_status TEXT NOT NULL CHECK (reported_status IN ('created', 'running', 'finished', 'crashed')),
            verified_status TEXT NOT NULL CHECK (verified_status IN ('pending', 'succeeded', 'failed', 'discarded', 'promoted')),
            ownership_token TEXT NOT NULL,
            raw_trace_ref TEXT,
            logs_ref TEXT,
            result_promotion_ref TEXT,
            result_exit_code INTEGER,
            UNIQUE(intent_id, ordinal)
        );

        CREATE INDEX idx_attempts_intent_id
            ON attempts(intent_id);
        CREATE INDEX idx_attempts_reported_status_heartbeat_at
            ON attempts(reported_status, heartbeat_at);
        CREATE INDEX idx_attempts_verified_status_started_at
            ON attempts(verified_status, started_at);

        CREATE TABLE evidence_summaries (
            id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
            observed_tool_calls INTEGER NOT NULL DEFAULT 0,
            observed_file_reads INTEGER NOT NULL DEFAULT 0,
            observed_file_writes INTEGER NOT NULL DEFAULT 0,
            observed_commands_run INTEGER NOT NULL DEFAULT 0,
            observed_duration_ms INTEGER NOT NULL DEFAULT 0,
            observed_tests_run INTEGER NOT NULL DEFAULT 0,
            observed_tests_passed INTEGER NOT NULL DEFAULT 0,
            observed_tests_failed INTEGER NOT NULL DEFAULT 0,
            observed_lint_passed INTEGER,
            observed_build_passed INTEGER,
            raw_prompt_ref TEXT,
            raw_trace_ref TEXT,
            logs_ref TEXT
        );

        CREATE INDEX idx_evidence_summaries_attempt_id
            ON evidence_summaries(attempt_id);

        CREATE TABLE intent_edges (
            parent_intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
            child_intent_id TEXT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
            edge_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (parent_intent_id, child_intent_id, edge_type)
        );

        CREATE TABLE attempt_commits (
            attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
            commit_oid TEXT NOT NULL,
            base_commit_oid TEXT NOT NULL,
            insertions INTEGER,
            deletions INTEGER,
            touched_files_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (attempt_id, commit_oid)
        );

        CREATE INDEX idx_attempt_commits_commit_oid
            ON attempt_commits(commit_oid);

        CREATE TABLE evidence_files (
            attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('read', 'touched', 'changed')),
            PRIMARY KEY (attempt_id, file_path, kind)
        );

        CREATE INDEX idx_evidence_files_file_path_kind_attempt_id
            ON evidence_files(file_path, kind, attempt_id);
        """,
    ),
    Migration(
        version=2,
        name="intent_edges_reverse_index",
        sql="""
        CREATE INDEX idx_intent_edges_child
            ON intent_edges(child_intent_id, edge_type);
        """,
    ),
    Migration(
        version=3,
        name="drop_result_patch_refs_json",
        sql="""
        SELECT 1;
        """,
    ),
    Migration(
        version=4,
        name="memory_notes",
        sql="""
        CREATE TABLE IF NOT EXISTS memory_notes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            topic TEXT,
            body TEXT NOT NULL,
            source TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_memory_notes_active_topic_updated_at
            ON memory_notes(active, topic, updated_at);
        """,
    ),
    Migration(
        version=5,
        name="attempt_outcomes",
        sql="""
        CREATE TABLE IF NOT EXISTS attempt_outcomes (
            attempt_id TEXT PRIMARY KEY REFERENCES attempts(id) ON DELETE CASCADE,
            schema_version INTEGER NOT NULL,
            outcome_class TEXT NOT NULL CHECK (
                outcome_class IN (
                    'pending',
                    'succeeded',
                    'succeeded_noop',
                    'promoted',
                    'failed',
                    'failed_with_evidence',
                    'failed_interrupted',
                    'failed_infra',
                    'discarded',
                    'needs_review'
                )
            ),
            confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
            reasons_json TEXT NOT NULL DEFAULT '[]',
            classified_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_attempt_outcomes_class_classified_at
            ON attempt_outcomes(outcome_class, classified_at);
        """,
    ),
)
