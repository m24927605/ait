from __future__ import annotations



import json

import sqlite3

import uuid



from ait.db.records import (

    AttemptCommitRecord,

    AttemptOutcomeRecord,

    AttemptRecord,

    EvidenceSummaryRecord,

    IntentRecord,

    NewAttempt,

    NewIntent,

)

from ait.db.schema import SCHEMA_VERSION



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

def list_intent_attempts(conn: sqlite3.Connection, intent_id: str) -> list[AttemptRecord]:
    rows = conn.execute(
        "SELECT * FROM attempts WHERE intent_id = ? ORDER BY ordinal ASC",
        (intent_id,),
    ).fetchall()
    return [_row_to_attempt(row) for row in rows]

def list_attempts(conn: sqlite3.Connection) -> list[AttemptRecord]:
    rows = conn.execute(
        "SELECT * FROM attempts ORDER BY started_at ASC, ordinal ASC"
    ).fetchall()
    return [_row_to_attempt(row) for row in rows]

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
                logs_ref, result_promotion_ref, result_exit_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
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

def get_attempt_by_workspace_ref(
    conn: sqlite3.Connection, workspace_ref: str
) -> AttemptRecord | None:
    row = conn.execute(
        "SELECT * FROM attempts WHERE workspace_ref = ?",
        (workspace_ref,),
    ).fetchone()
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

def list_evidence_files(conn: sqlite3.Connection, attempt_id: str) -> dict[str, tuple[str, ...]]:
    rows = conn.execute(
        """
        SELECT kind, file_path
        FROM evidence_files
        WHERE attempt_id = ?
        ORDER BY kind, file_path
        """,
        (attempt_id,),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row["kind"]), []).append(str(row["file_path"]))
    return {kind: tuple(paths) for kind, paths in grouped.items()}

def list_attempt_commits(conn: sqlite3.Connection, attempt_id: str) -> list[AttemptCommitRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return [_row_to_attempt_commit(row) for row in rows]

def get_attempt_outcome(conn: sqlite3.Connection, attempt_id: str) -> AttemptOutcomeRecord | None:
    row = conn.execute(
        "SELECT * FROM attempt_outcomes WHERE attempt_id = ?",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_attempt_outcome(row)

def upsert_attempt_outcome(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    outcome_class: str,
    confidence: str,
    reasons: tuple[str, ...],
    classified_at: str,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO attempt_outcomes(
                attempt_id, schema_version, outcome_class, confidence, reasons_json, classified_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                outcome_class = excluded.outcome_class,
                confidence = excluded.confidence,
                reasons_json = excluded.reasons_json,
                classified_at = excluded.classified_at
            """,
            (
                attempt_id,
                SCHEMA_VERSION,
                outcome_class,
                confidence,
                _json_dump(list(reasons)),
                classified_at,
            ),
        )

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

def replace_attempt_commits(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    commits: tuple[AttemptCommitRecord, ...],
) -> None:
    with conn:
        conn.execute("DELETE FROM attempt_commits WHERE attempt_id = ?", (attempt_id,))
        for commit in commits:
            conn.execute(
                """
                INSERT INTO attempt_commits(
                    attempt_id, commit_oid, base_commit_oid, insertions, deletions, touched_files_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    commit.attempt_id,
                    commit.commit_oid,
                    commit.base_commit_oid,
                    commit.insertions,
                    commit.deletions,
                    _json_dump(list(commit.touched_files)),
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

def replace_evidence_files_kind(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    kind: str,
    file_paths: tuple[str, ...],
) -> None:
    with conn:
        conn.execute(
            "DELETE FROM evidence_files WHERE attempt_id = ? AND kind = ?",
            (attempt_id, kind),
        )
        for file_path in file_paths:
            conn.execute(
                """
                INSERT INTO evidence_files(attempt_id, file_path, kind)
                VALUES (?, ?, ?)
                """,
                (attempt_id, file_path, kind),
            )

def update_attempt(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    base_ref_oid: str | None = None,
    base_ref_name: str | None = None,
    reported_status: str | None = None,
    verified_status: str | None = None,
    ended_at: str | None = None,
    heartbeat_at: str | None = None,
    raw_trace_ref: str | None = None,
    logs_ref: str | None = None,
    result_promotion_ref: str | None = None,
    result_exit_code: int | None = None,
) -> None:
    updates: list[tuple[str, object]] = []
    if base_ref_oid is not None:
        updates.append(("base_ref_oid", base_ref_oid))
    if base_ref_name is not None:
        updates.append(("base_ref_name", base_ref_name))
    if reported_status is not None:
        updates.append(("reported_status", reported_status))
    if verified_status is not None:
        updates.append(("verified_status", verified_status))
    if ended_at is not None:
        updates.append(("ended_at", ended_at))
    if heartbeat_at is not None:
        updates.append(("heartbeat_at", heartbeat_at))
    if raw_trace_ref is not None:
        updates.append(("raw_trace_ref", raw_trace_ref))
    if logs_ref is not None:
        updates.append(("logs_ref", logs_ref))
    if result_promotion_ref is not None:
        updates.append(("result_promotion_ref", result_promotion_ref))
    if result_exit_code is not None:
        updates.append(("result_exit_code", result_exit_code))
    if not updates:
        return
    assignments = ", ".join(f"{column} = ?" for column, _ in updates)
    params = tuple(value for _, value in updates) + (attempt_id,)
    with conn:
        conn.execute(f"UPDATE attempts SET {assignments} WHERE id = ?", params)

def update_intent_status(conn: sqlite3.Connection, intent_id: str, status: str) -> None:
    with conn:
        conn.execute(
            "UPDATE intents SET status = ? WHERE id = ?",
            (status, intent_id),
        )

def insert_intent_edge(
    conn: sqlite3.Connection,
    *,
    parent_intent_id: str,
    child_intent_id: str,
    edge_type: str,
    created_at: str,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO intent_edges(parent_intent_id, child_intent_id, edge_type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (parent_intent_id, child_intent_id, edge_type, created_at),
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

def _row_to_attempt_commit(row: sqlite3.Row) -> AttemptCommitRecord:
    return AttemptCommitRecord(
        attempt_id=str(row["attempt_id"]),
        commit_oid=str(row["commit_oid"]),
        base_commit_oid=str(row["base_commit_oid"]),
        insertions=_int_or_none(row["insertions"]),
        deletions=_int_or_none(row["deletions"]),
        touched_files=tuple(_json_load(row["touched_files_json"])),
    )

def _row_to_attempt_outcome(row: sqlite3.Row) -> AttemptOutcomeRecord:
    return AttemptOutcomeRecord(
        attempt_id=str(row["attempt_id"]),
        schema_version=int(row["schema_version"]),
        outcome_class=str(row["outcome_class"]),
        confidence=str(row["confidence"]),
        reasons=tuple(str(item) for item in _json_load(row["reasons_json"])),
        classified_at=str(row["classified_at"]),
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



__all__ = [

    "insert_intent",

    "get_intent",

    "list_intent_attempts",

    "list_attempts",

    "insert_attempt",

    "get_attempt",

    "get_attempt_by_workspace_ref",

    "get_evidence_summary",

    "list_evidence_files",

    "list_attempt_commits",

    "get_attempt_outcome",

    "upsert_attempt_outcome",

    "insert_attempt_commit",

    "replace_attempt_commits",

    "insert_evidence_file",

    "replace_evidence_files_kind",

    "update_attempt",

    "update_intent_status",

    "insert_intent_edge",

]
