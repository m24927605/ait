from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

PROTOCOL_SCHEMA_VERSION = 1
EVENT_ATTEMPT_STARTED = "attempt_started"
EVENT_ATTEMPT_HEARTBEAT = "attempt_heartbeat"
EVENT_TOOL_EVENT = "tool_event"
EVENT_ATTEMPT_FINISHED = "attempt_finished"
EVENT_ATTEMPT_PROMOTED = "attempt_promoted"
EVENT_ATTEMPT_DISCARDED = "attempt_discarded"

EVENT_TYPES = (
    EVENT_ATTEMPT_STARTED,
    EVENT_ATTEMPT_HEARTBEAT,
    EVENT_TOOL_EVENT,
    EVENT_ATTEMPT_FINISHED,
    EVENT_ATTEMPT_PROMOTED,
    EVENT_ATTEMPT_DISCARDED,
)
TOOL_EVENT_CATEGORIES = ("read", "write", "command", "other")
TOOL_FILE_ACCESS_VALUES = ("read", "write")


class ProtocolError(ValueError):
    """Raised when a daemon protocol message is malformed."""


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    agent_id: str
    harness: str
    harness_version: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class ToolFile:
    path: str
    access: str


@dataclass(frozen=True, slots=True)
class AttemptStartedPayload:
    agent: AgentDescriptor


@dataclass(frozen=True, slots=True)
class AttemptHeartbeatPayload:
    pass


@dataclass(frozen=True, slots=True)
class ToolEventPayload:
    tool_name: str
    category: str
    duration_ms: int
    success: bool
    files: tuple[ToolFile, ...] = ()
    payload_ref: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationMetrics:
    tests_run: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    lint_passed: bool | None = None
    build_passed: bool | None = None


@dataclass(frozen=True, slots=True)
class AttemptFinishedPayload:
    exit_code: int
    raw_trace_ref: str | None = None
    logs_ref: str | None = None
    verification: VerificationMetrics | None = None


@dataclass(frozen=True, slots=True)
class AttemptPromotedPayload:
    promotion_ref: str
    commit_oids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttemptDiscardedPayload:
    reason: str


Payload = (
    AttemptStartedPayload
    | AttemptHeartbeatPayload
    | ToolEventPayload
    | AttemptFinishedPayload
    | AttemptPromotedPayload
    | AttemptDiscardedPayload
)


@dataclass(frozen=True, slots=True)
class ProtocolEnvelope:
    schema_version: int
    event_id: str
    event_type: str
    sent_at: str
    attempt_id: str
    ownership_token: str
    payload: Payload


def parse_ndjson_message(message: str | bytes) -> ProtocolEnvelope:
    text = _decode_message_text(message)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("message must decode to a JSON object")
    return validate_envelope(raw)


def validate_envelope(raw: Mapping[str, Any]) -> ProtocolEnvelope:
    _reject_unknown_keys(
        raw,
        {
            "schema_version",
            "event_id",
            "event_type",
            "sent_at",
            "attempt_id",
            "ownership_token",
            "payload",
        },
        "envelope",
    )
    schema_version = _require_int(raw, "schema_version")
    if schema_version != PROTOCOL_SCHEMA_VERSION:
        raise ProtocolError(
            f"unsupported schema_version: {schema_version}"
        )
    event_type = _require_enum(raw, "event_type", EVENT_TYPES)
    sent_at = _require_timestamp(raw, "sent_at")
    payload_raw = _require_mapping(raw, "payload")
    return ProtocolEnvelope(
        schema_version=schema_version,
        event_id=_require_non_empty_str(raw, "event_id"),
        event_type=event_type,
        sent_at=sent_at,
        attempt_id=_require_non_empty_str(raw, "attempt_id"),
        ownership_token=_require_non_empty_str(raw, "ownership_token"),
        payload=_validate_payload(event_type, payload_raw),
    )


def envelope_to_dict(envelope: ProtocolEnvelope) -> dict[str, Any]:
    payload = _payload_to_dict(envelope.payload)
    return {
        "schema_version": envelope.schema_version,
        "event_id": envelope.event_id,
        "event_type": envelope.event_type,
        "sent_at": envelope.sent_at,
        "attempt_id": envelope.attempt_id,
        "ownership_token": envelope.ownership_token,
        "payload": payload,
    }


def envelope_to_json(envelope: ProtocolEnvelope) -> str:
    return json.dumps(envelope_to_dict(envelope), separators=(",", ":"), sort_keys=True)


def encode_ndjson_message(envelope: ProtocolEnvelope) -> bytes:
    return (envelope_to_json(envelope) + "\n").encode("utf-8")


def read_payload_ref(payload: Payload) -> str | None:
    if isinstance(payload, ToolEventPayload):
        return payload.payload_ref
    if isinstance(payload, AttemptFinishedPayload):
        return payload.raw_trace_ref or payload.logs_ref
    return None


def _decode_message_text(message: str | bytes) -> str:
    if isinstance(message, bytes):
        try:
            text = message.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("message is not valid UTF-8") from exc
    else:
        text = message
    if text.endswith("\n"):
        text = text[:-1]
    if "\n" in text or "\r" in text:
        raise ProtocolError("message must contain exactly one NDJSON line")
    if not text.strip():
        raise ProtocolError("message must not be empty")
    return text


def _validate_payload(event_type: str, payload_raw: Mapping[str, Any]) -> Payload:
    if event_type == EVENT_ATTEMPT_STARTED:
        return _validate_attempt_started_payload(payload_raw)
    if event_type == EVENT_ATTEMPT_HEARTBEAT:
        return _validate_attempt_heartbeat_payload(payload_raw)
    if event_type == EVENT_TOOL_EVENT:
        return _validate_tool_event_payload(payload_raw)
    if event_type == EVENT_ATTEMPT_FINISHED:
        return _validate_attempt_finished_payload(payload_raw)
    if event_type == EVENT_ATTEMPT_PROMOTED:
        return _validate_attempt_promoted_payload(payload_raw)
    if event_type == EVENT_ATTEMPT_DISCARDED:
        return _validate_attempt_discarded_payload(payload_raw)
    raise ProtocolError(f"unsupported event_type: {event_type}")


def _validate_attempt_started_payload(payload_raw: Mapping[str, Any]) -> AttemptStartedPayload:
    _reject_unknown_keys(payload_raw, {"agent"}, EVENT_ATTEMPT_STARTED)
    agent_raw = _require_mapping(payload_raw, "agent")
    _reject_unknown_keys(
        agent_raw,
        {"agent_id", "model", "harness", "harness_version"},
        "attempt_started.agent",
    )
    return AttemptStartedPayload(
        agent=AgentDescriptor(
            agent_id=_require_non_empty_str(agent_raw, "agent_id"),
            model=_optional_non_empty_str(agent_raw, "model"),
            harness=_require_non_empty_str(agent_raw, "harness"),
            harness_version=_require_non_empty_str(agent_raw, "harness_version"),
        )
    )


def _validate_attempt_heartbeat_payload(
    payload_raw: Mapping[str, Any]
) -> AttemptHeartbeatPayload:
    _reject_unknown_keys(payload_raw, set(), EVENT_ATTEMPT_HEARTBEAT)
    return AttemptHeartbeatPayload()


def _validate_tool_event_payload(payload_raw: Mapping[str, Any]) -> ToolEventPayload:
    _reject_unknown_keys(
        payload_raw,
        {"tool_name", "category", "duration_ms", "success", "files", "payload_ref"},
        EVENT_TOOL_EVENT,
    )
    files_raw = payload_raw.get("files", [])
    if not isinstance(files_raw, list):
        raise ProtocolError("tool_event.files must be a list")
    files = tuple(_validate_tool_file(item, idx) for idx, item in enumerate(files_raw))
    duration_ms = _require_int(payload_raw, "duration_ms")
    if duration_ms < 0:
        raise ProtocolError("tool_event.duration_ms must be >= 0")
    success = payload_raw.get("success")
    if not isinstance(success, bool):
        raise ProtocolError("tool_event.success must be a boolean")
    return ToolEventPayload(
        tool_name=_require_non_empty_str(payload_raw, "tool_name"),
        category=_require_enum(payload_raw, "category", TOOL_EVENT_CATEGORIES),
        duration_ms=duration_ms,
        success=success,
        files=files,
        payload_ref=_optional_non_empty_str(payload_raw, "payload_ref"),
    )


def _validate_attempt_finished_payload(
    payload_raw: Mapping[str, Any]
) -> AttemptFinishedPayload:
    _reject_unknown_keys(
        payload_raw,
        {"exit_code", "raw_trace_ref", "logs_ref", "verification"},
        EVENT_ATTEMPT_FINISHED,
    )
    verification_raw = payload_raw.get("verification")
    if verification_raw is None:
        verification: VerificationMetrics | None = None
    else:
        if not isinstance(verification_raw, dict):
            raise ProtocolError("attempt_finished.verification must be an object")
        _reject_unknown_keys(
            verification_raw,
            {
                "tests_run",
                "tests_passed",
                "tests_failed",
                "lint_passed",
                "build_passed",
            },
            "attempt_finished.verification",
        )
        verification = VerificationMetrics(
            tests_run=_optional_non_negative_int(verification_raw, "tests_run"),
            tests_passed=_optional_non_negative_int(verification_raw, "tests_passed"),
            tests_failed=_optional_non_negative_int(verification_raw, "tests_failed"),
            lint_passed=_optional_bool(verification_raw, "lint_passed"),
            build_passed=_optional_bool(verification_raw, "build_passed"),
        )
    return AttemptFinishedPayload(
        exit_code=_require_int(payload_raw, "exit_code"),
        raw_trace_ref=_optional_non_empty_str(payload_raw, "raw_trace_ref"),
        logs_ref=_optional_non_empty_str(payload_raw, "logs_ref"),
        verification=verification,
    )


def _validate_attempt_promoted_payload(
    payload_raw: Mapping[str, Any]
) -> AttemptPromotedPayload:
    _reject_unknown_keys(
        payload_raw,
        {"promotion_ref", "commit_oids"},
        EVENT_ATTEMPT_PROMOTED,
    )
    commit_oids_raw = payload_raw.get("commit_oids")
    if not isinstance(commit_oids_raw, list) or not commit_oids_raw:
        raise ProtocolError("attempt_promoted.commit_oids must be a non-empty list")
    commit_oids = tuple(_require_non_empty_str({"value": value}, "value") for value in commit_oids_raw)
    return AttemptPromotedPayload(
        promotion_ref=_require_non_empty_str(payload_raw, "promotion_ref"),
        commit_oids=commit_oids,
    )


def _validate_attempt_discarded_payload(
    payload_raw: Mapping[str, Any]
) -> AttemptDiscardedPayload:
    _reject_unknown_keys(payload_raw, {"reason"}, EVENT_ATTEMPT_DISCARDED)
    return AttemptDiscardedPayload(reason=_require_non_empty_str(payload_raw, "reason"))


def _validate_tool_file(raw: Any, index: int) -> ToolFile:
    if not isinstance(raw, dict):
        raise ProtocolError(f"tool_event.files[{index}] must be an object")
    _reject_unknown_keys(raw, {"path", "access"}, f"tool_event.files[{index}]")
    return ToolFile(
        path=_require_non_empty_str(raw, "path"),
        access=_require_enum(raw, "access", TOOL_FILE_ACCESS_VALUES),
    )


def _payload_to_dict(payload: Payload) -> dict[str, Any]:
    if isinstance(payload, AttemptStartedPayload):
        data = {
            "agent": {
                "agent_id": payload.agent.agent_id,
                "harness": payload.agent.harness,
                "harness_version": payload.agent.harness_version,
            }
        }
        if payload.agent.model is not None:
            data["agent"]["model"] = payload.agent.model
        return data
    if isinstance(payload, AttemptHeartbeatPayload):
        return {}
    if isinstance(payload, ToolEventPayload):
        data = {
            "tool_name": payload.tool_name,
            "category": payload.category,
            "duration_ms": payload.duration_ms,
            "success": payload.success,
        }
        if payload.files:
            data["files"] = [
                {"path": file.path, "access": file.access} for file in payload.files
            ]
        if payload.payload_ref is not None:
            data["payload_ref"] = payload.payload_ref
        return data
    if isinstance(payload, AttemptFinishedPayload):
        data = {"exit_code": payload.exit_code}
        if payload.raw_trace_ref is not None:
            data["raw_trace_ref"] = payload.raw_trace_ref
        if payload.logs_ref is not None:
            data["logs_ref"] = payload.logs_ref
        if payload.verification is not None:
            verification: dict[str, Any] = {}
            v = payload.verification
            if v.tests_run is not None:
                verification["tests_run"] = v.tests_run
            if v.tests_passed is not None:
                verification["tests_passed"] = v.tests_passed
            if v.tests_failed is not None:
                verification["tests_failed"] = v.tests_failed
            if v.lint_passed is not None:
                verification["lint_passed"] = v.lint_passed
            if v.build_passed is not None:
                verification["build_passed"] = v.build_passed
            if verification:
                data["verification"] = verification
        return data
    if isinstance(payload, AttemptPromotedPayload):
        return {
            "promotion_ref": payload.promotion_ref,
            "commit_oids": list(payload.commit_oids),
        }
    if isinstance(payload, AttemptDiscardedPayload):
        return {"reason": payload.reason}
    raise TypeError(f"unsupported payload type: {type(payload)!r}")


def _reject_unknown_keys(
    raw: Mapping[str, Any],
    allowed_keys: set[str],
    context: str,
) -> None:
    extras = sorted(set(raw) - allowed_keys)
    if extras:
        raise ProtocolError(f"{context} contains unknown keys: {', '.join(extras)}")


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ProtocolError(f"{key} must be an object")
    return value


def _require_non_empty_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{key} must be a non-empty string")
    return value


def _optional_non_empty_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{key} must be a non-empty string when provided")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{key} must be an integer")
    return value


def _optional_non_negative_int(raw: Mapping[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{key} must be an integer when provided")
    if value < 0:
        raise ProtocolError(f"{key} must be >= 0 when provided")
    return value


def _optional_bool(raw: Mapping[str, Any], key: str) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ProtocolError(f"{key} must be a boolean when provided")
    return value


def _require_enum(raw: Mapping[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = _require_non_empty_str(raw, key)
    if value not in allowed:
        raise ProtocolError(f"{key} must be one of: {', '.join(allowed)}")
    return value


def _require_timestamp(raw: Mapping[str, Any], key: str) -> str:
    value = _require_non_empty_str(raw, key)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        parsed.replace(tzinfo=timezone.utc)
        return value
    raise ProtocolError(f"{key} must be an RFC3339 UTC timestamp ending with Z")
