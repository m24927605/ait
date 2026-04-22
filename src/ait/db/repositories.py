from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field

from ait.db.schema import SCHEMA_VERSION


@dataclass(frozen=True)
class NewIntent:
    id: str
    repo_id: str
    title: str
    created_at: str
    created_by_actor_type: str
    created_by_actor_id: str
    trigger_source: str
    description: str | None = None
    kind: str | None = None
    parent_intent_id: str | None = None
    root_intent_id: str | None = None
    trigger_prompt_ref: str | None = None
    status: str = "open"
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IntentRecord:
    id: str
    schema_version: int
    repo_id: str
    title: str
    description: str | None
    kind: str | None
    parent_intent_id: str | None
    root_intent_id: str
    created_at: str
    created_by_actor_type: str
    created_by_actor_id: str
    trigger_source: str
    trigger_prompt_ref: str | None
    status: str
    tags: tuple[str, ...]
    metadata: dict[str, str]


@dataclass(frozen=True)
class NewAttempt:
    id: str
    intent_id: str
    agent_id: str
    workspace_ref: str
    base_ref_oid: str
    started_at: str
    ownership_token: str
    agent_model: str | None = None
    agent_harness: str | None = None
    agent_harness_version: str | None = None
    workspace_kind: str = "worktree"
    base_ref_name: str | None = None
    heartbeat_at: str | None = None
    reported_status: str = "created"
    verified_status: str = "pending"


@dataclass(frozen=True)
class AttemptRecord:
    id: str
    schema_version: int
    intent_id: str
    ordinal: int
    agent_id: str
    agent_model: str | None
    agent_harness: str | None
    agent_harness_version: str | None
    workspace_kind: str
    workspace_ref: str
    base_ref_oid: str
    base_ref_name: str | None
    started_at: str
    ended_at: str | None
    heartbeat_at: str | None
    reported_status: str
    verified_status: str
    ownership_token: str
    raw_trace_ref: str | None
    logs_ref: str | None
    result_patch_refs: tuple[str, ...]
    result_promotion_ref: str | None
    result_exit_code: int | None


@dataclass(frozen=True)
class EvidenceSummaryRecord:
    id: str
    schema_version: int
    attempt_id: str
    observed_tool_calls: int
    observed_file_reads: int
    observed_file_writes: int
    observed_commands_run: int
    observed_duration_ms: int
    observed_tests_run: int
    observed_tests_passed: int
    observed_tests_failed: int
    observed_lint_passed: bool | None
    observed_build_passed: bool | None
    raw_prompt_ref: str | None
    raw_trace_ref: str | None
    logs_ref: str | None


def insert_intent(conn: sqlite3.Connection, new_intent: NewIntent) -> IntentRecord:
    root_intent_id = new_intent.root_intent_id or new_intent.id
    with conn:
        conn.execute(
            """
            INSERT INTO intents(
                id, schema_version, repo_id, title, description, kind,
                parent_intent_id, root_intent_id, created_at,
                created_by_actor_type, created_by_actor_id,
                trigger_source, trigger_prompt_ref, status, tags_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_intent.id,
                SCHEMA_VERSION,
                new_intent.repo_id,
                new_intent.title,
                new_intent.description,
                new_intent.kind,
                new_intent.parent_intent_id,
                root_intent_id,
                new_intent.created_at,
                new_intent.created_by_actor_type,
                new_intent.created_by_actor_id,
                new_intent.trigger_source,
                new_intent.trigger_prompt_ref,
                new_intent.status,
                _json_dump(list(new_intent.tags)),
                _json_dump(new_intent.metadata),
            ),
        )

    return get_intent(conn, new_intent.id)


def get_intent(conn: sqlite3.Connection, intent_id: str) -> IntentRecord | None:
    row = conn.execute("SELECT * FROM intents WHERE id = ?", (intent_id,)).fetchone()
    if row is None:
        return None
    return _row_to_intent(row)


def insert_attempt(conn: sqlite3.Connection, new_attempt: NewAttempt) -> AttemptRecord:
    with conn:
        intent_row = conn.execute(
            "SELECT id FROM intents WHERE id = ?", (new_attempt.intent_id,)
        ).fetchone()
        if intent_row is None:
            raise LookupError(f"intent not found: {new_attempt.intent_id}")

        ordinal = _next_attempt_ordinal(conn, new_attempt.intent_id)
        conn.execute(
            """
            INSERT INTO attempts(
                id, schema_version, intent_id, ordinal, agent_id, agent_model,
                agent_harness, agent_harness_version, workspace_kind, workspace_ref,
                base_ref_oid, base_ref_name, started_at, ended_at, heartbeat_at,
                reported_status, verified_status, ownership_token, raw_trace_ref,
                logs_ref, result_patch_refs_json, result_promotion_ref, result_exit_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL, '[]', NULL, NULL)
            """,
            (
                new_attempt.id,
                SCHEMA_VERSION,
                new_attempt.intent_id,
                ordinal,
                new_attempt.agent_id,
                new_attempt.agent_model,
                new_attempt.agent_harness,
                new_attempt.agent_harness_version,
                new_attempt.workspace_kind,
                new_attempt.workspace_ref,
                new_attempt.base_ref_oid,
                new_attempt.base_ref_name,
                new_attempt.started_at,
                new_attempt.heartbeat_at,
                new_attempt.reported_status,
                new_attempt.verified_status,
                new_attempt.ownership_token,
            ),
        )
        conn.execute(
            """
            INSERT INTO evidence_summaries(
                id, schema_version, attempt_id,
                observed_tool_calls, observed_file_reads, observed_file_writes,
                observed_commands_run, observed_duration_ms, observed_tests_run,
                observed_tests_passed, observed_tests_failed
            )
            VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
            """,
            (f"{new_attempt.id}:evidence:{uuid.uuid4().hex}", SCHEMA_VERSION, new_attempt.id),
        )

    return get_attempt(conn, new_attempt.id)


def get_attempt(conn: sqlite3.Connection, attempt_id: str) -> AttemptRecord | None:
    row = conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if row is None:
        return None
    return _row_to_attempt(row)


def get_evidence_summary(
    conn: sqlite3.Connection, attempt_id: str
) -> EvidenceSummaryRecord | None:
    row = conn.execute(
        "SELECT * FROM evidence_summaries WHERE attempt_id = ?", (attempt_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_evidence_summary(row)


def insert_attempt_commit(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    commit_oid: str,
    base_commit_oid: str,
    touched_files: tuple[str, ...] = (),
    insertions: int | None = None,
    deletions: int | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO attempt_commits(
                attempt_id, commit_oid, base_commit_oid, insertions, deletions, touched_files_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                commit_oid,
                base_commit_oid,
                insertions,
                deletions,
                _json_dump(list(touched_files)),
            ),
        )


def insert_evidence_file(
    conn: sqlite3.Connection, *, attempt_id: str, file_path: str, kind: str
) -> None:
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence_files(attempt_id, file_path, kind)
            VALUES (?, ?, ?)
            """,
            (attempt_id, file_path, kind),
        )


def _next_attempt_ordinal(conn: sqlite3.Connection, intent_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(ordinal), 0) AS max_ordinal FROM attempts WHERE intent_id = ?",
        (intent_id,),
    ).fetchone()
    return int(row["max_ordinal"]) + 1


def _row_to_intent(row: sqlite3.Row) -> IntentRecord:
    return IntentRecord(
        id=str(row["id"]),
        schema_version=int(row["schema_version"]),
        repo_id=str(row["repo_id"]),
        title=str(row["title"]),
        description=_str_or_none(row["description"]),
        kind=_str_or_none(row["kind"]),
        parent_intent_id=_str_or_none(row["parent_intent_id"]),
        root_intent_id=str(row["root_intent_id"]),
        created_at=str(row["created_at"]),
        created_by_actor_type=str(row["created_by_actor_type"]),
        created_by_actor_id=str(row["created_by_actor_id"]),
        trigger_source=str(row["trigger_source"]),
        trigger_prompt_ref=_str_or_none(row["trigger_prompt_ref"]),
        status=str(row["status"]),
        tags=tuple(_json_load(row["tags_json"])),
        metadata=dict(_json_load(row["metadata_json"])),
    )


def _row_to_attempt(row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        id=str(row["id"]),
        schema_version=int(row["schema_version"]),
        intent_id=str(row["intent_id"]),
        ordinal=int(row["ordinal"]),
        agent_id=str(row["agent_id"]),
        agent_model=_str_or_none(row["agent_model"]),
        agent_harness=_str_or_none(row["agent_harness"]),
        agent_harness_version=_str_or_none(row["agent_harness_version"]),
        workspace_kind=str(row["workspace_kind"]),
        workspace_ref=str(row["workspace_ref"]),
        base_ref_oid=str(row["base_ref_oid"]),
        base_ref_name=_str_or_none(row["base_ref_name"]),
        started_at=str(row["started_at"]),
        ended_at=_str_or_none(row["ended_at"]),
        heartbeat_at=_str_or_none(row["heartbeat_at"]),
        reported_status=str(row["reported_status"]),
        verified_status=str(row["verified_status"]),
        ownership_token=str(row["ownership_token"]),
        raw_trace_ref=_str_or_none(row["raw_trace_ref"]),
        logs_ref=_str_or_none(row["logs_ref"]),
        result_patch_refs=tuple(_json_load(row["result_patch_refs_json"])),
        result_promotion_ref=_str_or_none(row["result_promotion_ref"]),
        result_exit_code=_int_or_none(row["result_exit_code"]),
    )


def _row_to_evidence_summary(row: sqlite3.Row) -> EvidenceSummaryRecord:
    return EvidenceSummaryRecord(
        id=str(row["id"]),
        schema_version=int(row["schema_version"]),
        attempt_id=str(row["attempt_id"]),
        observed_tool_calls=int(row["observed_tool_calls"]),
        observed_file_reads=int(row["observed_file_reads"]),
        observed_file_writes=int(row["observed_file_writes"]),
        observed_commands_run=int(row["observed_commands_run"]),
        observed_duration_ms=int(row["observed_duration_ms"]),
        observed_tests_run=int(row["observed_tests_run"]),
        observed_tests_passed=int(row["observed_tests_passed"]),
        observed_tests_failed=int(row["observed_tests_failed"]),
        observed_lint_passed=_bool_or_none(row["observed_lint_passed"]),
        observed_build_passed=_bool_or_none(row["observed_build_passed"]),
        raw_prompt_ref=_str_or_none(row["raw_prompt_ref"]),
        raw_trace_ref=_str_or_none(row["raw_trace_ref"]),
        logs_ref=_str_or_none(row["logs_ref"]),
    )


def _json_dump(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_load(value: object) -> object:
    return json.loads(str(value))


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    return bool(int(value))


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
