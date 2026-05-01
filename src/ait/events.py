from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
import sqlite3

from ait.db import AttemptRecord, get_attempt
from ait.lifecycle import refresh_intent_status

PROTOCOL_SCHEMA_VERSION = 1
_EVENT_SEEN_KEY_PREFIX = "event_seen:"


@dataclass(frozen=True)
class EventEnvelope:
    schema_version: int
    event_id: str
    event_type: str
    sent_at: str
    attempt_id: str
    ownership_token: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class EventProcessResult:
    event_id: str
    event_type: str
    attempt_id: str
    duplicate: bool
    mutated: bool


class EventError(ValueError):
    pass


class EventConflictError(EventError):
    pass


class EventOwnershipError(EventError):
    pass


class EventNotFoundError(EventError):
    pass


def process_event(
    conn: sqlite3.Connection, envelope: EventEnvelope | Mapping[str, Any]
) -> EventProcessResult:
    event = envelope if isinstance(envelope, EventEnvelope) else parse_event_envelope(envelope)
    with conn:
        attempt = validate_ownership_token(
            conn,
            attempt_id=event.attempt_id,
            ownership_token=event.ownership_token,
        )
        if not _claim_event_id(conn, event):
            return EventProcessResult(
                event_id=event.event_id,
                event_type=event.event_type,
                attempt_id=event.attempt_id,
                duplicate=True,
                mutated=False,
            )

        mutated = _dispatch_event(conn, attempt, event)
        return EventProcessResult(
            event_id=event.event_id,
            event_type=event.event_type,
            attempt_id=event.attempt_id,
            duplicate=False,
            mutated=mutated,
        )


def parse_event_envelope(raw: Mapping[str, Any]) -> EventEnvelope:
    schema_version = _required_int(raw, "schema_version")
    if schema_version != PROTOCOL_SCHEMA_VERSION:
        raise EventError(f"unsupported schema_version: {schema_version}")

    payload = raw.get("payload", {})
    if not isinstance(payload, Mapping):
        raise EventError("payload must be an object")

    return EventEnvelope(
        schema_version=schema_version,
        event_id=_required_str(raw, "event_id"),
        event_type=_required_str(raw, "event_type"),
        sent_at=_parse_timestamp(_required_str(raw, "sent_at")),
        attempt_id=_required_str(raw, "attempt_id"),
        ownership_token=_required_str(raw, "ownership_token"),
        payload=payload,
    )


def validate_ownership_token(
    conn: sqlite3.Connection, *, attempt_id: str, ownership_token: str
) -> AttemptRecord:
    attempt = get_attempt(conn, attempt_id)
    if attempt is None:
        raise EventNotFoundError(f"attempt not found: {attempt_id}")
    if attempt.ownership_token != ownership_token:
        raise EventOwnershipError(f"ownership token mismatch for attempt {attempt_id}")
    return attempt


def handle_attempt_started(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str, payload: Mapping[str, Any]
) -> bool:
    if attempt.verified_status in {"discarded", "failed", "promoted"} or attempt.reported_status in {"finished", "crashed"}:
        return False
    agent = payload.get("agent", {})
    if not isinstance(agent, Mapping):
        raise EventError("attempt_started payload.agent must be an object")

    agent_id = _coalesce_str(agent.get("agent_id"), attempt.agent_id)
    conn.execute(
        """
        UPDATE attempts
        SET agent_id = ?,
            agent_model = ?,
            agent_harness = ?,
            agent_harness_version = ?,
            reported_status = 'running',
            heartbeat_at = CASE
                WHEN heartbeat_at IS NULL OR heartbeat_at < ? THEN ?
                ELSE heartbeat_at
            END
        WHERE id = ?
        """,
        (
            agent_id,
            _nullable_str(agent.get("model"), fallback=attempt.agent_model),
            _nullable_str(agent.get("harness"), fallback=attempt.agent_harness),
            _nullable_str(agent.get("harness_version"), fallback=attempt.agent_harness_version),
            sent_at,
            sent_at,
            attempt.id,
        ),
    )
    refresh_intent_status(conn, attempt.intent_id)
    return True


def handle_attempt_heartbeat(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str
) -> bool:
    cursor = conn.execute(
        """
        UPDATE attempts
        SET heartbeat_at = CASE
            WHEN heartbeat_at IS NULL OR heartbeat_at < ? THEN ?
            ELSE heartbeat_at
        END
        WHERE id = ?
        """,
        (sent_at, sent_at, attempt.id),
    )
    return cursor.rowcount > 0


def handle_tool_event(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str, payload: Mapping[str, Any]
) -> None:
    category = _required_str(payload, "category")
    duration_ms = payload.get("duration_ms")
    if duration_ms is None:
        duration_value = 0
    else:
        duration_value = int(duration_ms)
        if duration_value < 0:
            raise EventError("tool_event duration_ms must be >= 0")

    conn.execute(
        """
        UPDATE attempts
        SET heartbeat_at = CASE
            WHEN heartbeat_at IS NULL OR heartbeat_at < ? THEN ?
            ELSE heartbeat_at
        END
        WHERE id = ?
        """,
        (sent_at, sent_at, attempt.id),
    )
    conn.execute(
        """
        UPDATE evidence_summaries
        SET observed_tool_calls = observed_tool_calls + 1,
            observed_file_reads = observed_file_reads + ?,
            observed_file_writes = observed_file_writes + ?,
            observed_commands_run = observed_commands_run + ?,
            observed_duration_ms = observed_duration_ms + ?
        WHERE attempt_id = ?
        """,
        (
            1 if category == "read" else 0,
            1 if category == "write" else 0,
            1 if category == "command" else 0,
            duration_value,
            attempt.id,
        ),
    )

    files = payload.get("files")
    if files is None:
        return
    if not isinstance(files, list):
        raise EventError("tool_event files must be a list")
    for entry in files:
        if not isinstance(entry, Mapping):
            raise EventError("tool_event file entry must be an object")
        file_path = _required_str(entry, "path")
        access = _required_str(entry, "access")
        if access == "read":
            kind = "read"
        elif access == "write":
            kind = "touched"
        else:
            raise EventError(f"unsupported file access: {access}")
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence_files(attempt_id, file_path, kind)
            VALUES (?, ?, ?)
            """,
            (attempt.id, file_path, kind),
        )


def handle_attempt_finished(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str, payload: Mapping[str, Any]
) -> None:
    raw_trace_ref = _nullable_str(payload.get("raw_trace_ref"), fallback=attempt.raw_trace_ref)
    logs_ref = _nullable_str(payload.get("logs_ref"), fallback=attempt.logs_ref)
    exit_code = payload.get("exit_code")
    exit_code_value = attempt.result_exit_code if exit_code is None else int(exit_code)
    verification = payload.get("verification")
    if verification is not None and not isinstance(verification, Mapping):
        raise EventError("attempt_finished verification must be an object")

    conn.execute(
        """
        UPDATE attempts
        SET ended_at = CASE
                WHEN ended_at IS NULL OR ended_at < ? THEN ?
                ELSE ended_at
            END,
            heartbeat_at = CASE
                WHEN heartbeat_at IS NULL OR heartbeat_at < ? THEN ?
                ELSE heartbeat_at
            END,
            reported_status = 'finished',
            raw_trace_ref = ?,
            logs_ref = ?,
            result_exit_code = ?
        WHERE id = ?
        """,
        (
            sent_at,
            sent_at,
            sent_at,
            sent_at,
            raw_trace_ref,
            logs_ref,
            exit_code_value,
            attempt.id,
        ),
    )
    conn.execute(
        """
        UPDATE evidence_summaries
        SET raw_trace_ref = ?,
            logs_ref = ?
        WHERE attempt_id = ?
        """,
        (raw_trace_ref, logs_ref, attempt.id),
    )
    if verification is not None:
        _apply_verification_metrics(conn, attempt_id=attempt.id, metrics=verification)


def _apply_verification_metrics(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    metrics: Mapping[str, Any],
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    for field, validator in (
        ("tests_run", _require_non_negative_int),
        ("tests_passed", _require_non_negative_int),
        ("tests_failed", _require_non_negative_int),
        ("lint_passed", _require_bool),
        ("build_passed", _require_bool),
    ):
        if field not in metrics:
            continue
        value = validator(metrics, field)
        column = f"observed_{field}"
        if isinstance(value, bool):
            params.append(1 if value else 0)
        else:
            params.append(value)
        updates.append(f"{column} = ?")
    if not updates:
        return
    params.append(attempt_id)
    conn.execute(
        f"UPDATE evidence_summaries SET {', '.join(updates)} WHERE attempt_id = ?",
        params,
    )


def _require_non_negative_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EventError(f"verification.{key} must be an integer")
    if value < 0:
        raise EventError(f"verification.{key} must be >= 0")
    return value


def _require_bool(mapping: Mapping[str, Any], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise EventError(f"verification.{key} must be a boolean")
    return value


def handle_attempt_promoted(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str, payload: Mapping[str, Any]
) -> bool:
    if attempt.verified_status == "discarded":
        raise EventConflictError(f"attempt already discarded: {attempt.id}")

    promotion_ref = _required_str(payload, "promotion_ref")
    if not promotion_ref.startswith("refs/heads/"):
        raise EventError("promotion_ref must be a branch under refs/heads/")
    conn.execute(
        """
        UPDATE attempts
        SET result_promotion_ref = ?,
            verified_status = 'promoted',
            reported_status = CASE
                WHEN reported_status IN ('created', 'running') THEN 'finished'
                ELSE reported_status
            END,
            ended_at = CASE
                WHEN ended_at IS NULL OR ended_at < ? THEN ?
                ELSE ended_at
            END
        WHERE id = ?
        """,
        (promotion_ref, sent_at, sent_at, attempt.id),
    )
    return True


def handle_attempt_discarded(
    conn: sqlite3.Connection, *, attempt: AttemptRecord, sent_at: str
) -> bool:
    if attempt.verified_status == "promoted":
        return False

    conn.execute(
        """
        UPDATE attempts
        SET verified_status = 'discarded',
            reported_status = CASE
                WHEN reported_status IN ('created', 'running') THEN 'finished'
                ELSE reported_status
            END,
            ended_at = CASE
                WHEN ended_at IS NULL OR ended_at < ? THEN ?
                ELSE ended_at
            END
        WHERE id = ?
        """,
        (sent_at, sent_at, attempt.id),
    )
    refresh_intent_status(conn, attempt.intent_id)
    return True


def recover_running_attempts(
    conn: sqlite3.Connection, *, now: str, heartbeat_ttl_seconds: int
) -> tuple[str, ...]:
    return _mark_stale_running_attempts(conn, now=now, heartbeat_ttl_seconds=heartbeat_ttl_seconds)


def reap_stale_attempts(
    conn: sqlite3.Connection, *, now: str, heartbeat_ttl_seconds: int
) -> tuple[str, ...]:
    return _mark_stale_running_attempts(conn, now=now, heartbeat_ttl_seconds=heartbeat_ttl_seconds)


def _mark_stale_running_attempts(
    conn: sqlite3.Connection, *, now: str, heartbeat_ttl_seconds: int
) -> tuple[str, ...]:
    now_iso = _parse_timestamp(now)
    cutoff_dt = _parse_timestamp(now_iso, to_datetime=True) - timedelta(seconds=heartbeat_ttl_seconds)
    assert isinstance(cutoff_dt, datetime)
    cutoff_iso = cutoff_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stale_ids: list[str] = []

    started_transaction = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True
    try:
        rows = conn.execute(
            """
            SELECT id, heartbeat_at, started_at
            FROM attempts
            WHERE reported_status = 'running'
            """
        ).fetchall()
        for row in rows:
            last_seen = row["heartbeat_at"] or row["started_at"]
            if _parse_timestamp(str(last_seen), to_datetime=True) > cutoff_dt:
                continue
            attempt_id = str(row["id"])
            updated = conn.execute(
                """
                UPDATE attempts
                SET reported_status = 'crashed',
                    verified_status = 'failed',
                    ended_at = CASE
                        WHEN ended_at IS NULL OR ended_at < ? THEN ?
                        ELSE ended_at
                    END
                WHERE id = ?
                  AND reported_status = 'running'
                  AND COALESCE(heartbeat_at, started_at) <= ?
                """,
                (now_iso, now_iso, attempt_id, cutoff_iso),
            ).rowcount
            if updated == 0:
                continue
            stale_ids.append(attempt_id)
            intent_id = conn.execute(
                "SELECT intent_id FROM attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()["intent_id"]
            refresh_intent_status(conn, str(intent_id))
        if started_transaction:
            conn.commit()
    except Exception:
        if started_transaction:
            conn.rollback()
        raise
    return tuple(stale_ids)


def _dispatch_event(
    conn: sqlite3.Connection, attempt: AttemptRecord, event: EventEnvelope
) -> bool:
    if event.event_type == "attempt_started":
        return handle_attempt_started(conn, attempt=attempt, sent_at=event.sent_at, payload=event.payload)
    if event.event_type == "attempt_heartbeat":
        return handle_attempt_heartbeat(conn, attempt=attempt, sent_at=event.sent_at)
    if event.event_type == "tool_event":
        handle_tool_event(conn, attempt=attempt, sent_at=event.sent_at, payload=event.payload)
        return True
    if event.event_type == "attempt_finished":
        handle_attempt_finished(conn, attempt=attempt, sent_at=event.sent_at, payload=event.payload)
        return True
    if event.event_type == "attempt_promoted":
        return handle_attempt_promoted(conn, attempt=attempt, sent_at=event.sent_at, payload=event.payload)
    if event.event_type == "attempt_discarded":
        return handle_attempt_discarded(conn, attempt=attempt, sent_at=event.sent_at)
    raise EventError(f"unsupported event_type: {event.event_type}")


def _claim_event_id(conn: sqlite3.Connection, event: EventEnvelope) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO meta(key, value)
        VALUES (?, ?)
        """,
        (_event_meta_key(event.event_id), f"{event.event_type}:{event.sent_at}"),
    )
    return cursor.rowcount > 0


def _event_meta_key(event_id: str) -> str:
    return f"{_EVENT_SEEN_KEY_PREFIX}{event_id}"


def _required_str(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise EventError(f"{key} must be a string")
    if value == "":
        raise EventError(f"{key} must not be empty")
    return value


def _required_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise EventError(f"{key} must be an integer")
    return value


def _nullable_str(value: Any, *, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise EventError("expected string or null")
    return value


def _coalesce_str(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str) or value == "":
        raise EventError("expected non-empty string")
    return value


def _parse_timestamp(value: str, *, to_datetime: bool = False) -> str | datetime:
    parsed = None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
        break
    if parsed is None:
        raise EventError(f"invalid timestamp: {value}")
    normalized = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if to_datetime:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    return normalized
