from __future__ import annotations

import unittest

from ait.protocol import (
    EVENT_ATTEMPT_DISCARDED,
    EVENT_ATTEMPT_FINISHED,
    EVENT_ATTEMPT_HEARTBEAT,
    EVENT_ATTEMPT_PROMOTED,
    EVENT_ATTEMPT_STARTED,
    EVENT_TOOL_EVENT,
    AgentDescriptor,
    AttemptDiscardedPayload,
    AttemptFinishedPayload,
    AttemptHeartbeatPayload,
    AttemptPromotedPayload,
    AttemptStartedPayload,
    ProtocolEnvelope,
    ProtocolError,
    ToolEventPayload,
    ToolFile,
    VerificationMetrics,
    encode_ndjson_message,
    envelope_to_dict,
    parse_ndjson_message,
    validate_envelope,
)


class ProtocolValidationTests(unittest.TestCase):
    def test_validate_attempt_started_envelope(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-1",
                "event_type": EVENT_ATTEMPT_STARTED,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {
                    "agent": {
                        "agent_id": "codex:worker-4",
                        "model": "gpt-5",
                        "harness": "codex",
                        "harness_version": "1.2.3",
                    }
                },
            }
        )

        self.assertEqual(envelope.event_type, EVENT_ATTEMPT_STARTED)
        self.assertEqual(
            envelope.payload,
            AttemptStartedPayload(
                agent=AgentDescriptor(
                    agent_id="codex:worker-4",
                    model="gpt-5",
                    harness="codex",
                    harness_version="1.2.3",
                )
            ),
        )

    def test_validate_tool_event_envelope_with_files(self) -> None:
        envelope = parse_ndjson_message(
            b'{"schema_version":1,"event_id":"repo:evt-2","event_type":"tool_event","sent_at":"2026-04-23T12:34:56.123456Z","attempt_id":"repo:attempt-1","ownership_token":"token-1","payload":{"tool_name":"Read","category":"read","duration_ms":42,"success":true,"files":[{"path":"src/app.py","access":"read"},{"path":"src/config.py","access":"write"}],"payload_ref":".ait/objects/ab/cdef"}}\n'
        )

        self.assertEqual(
            envelope.payload,
            ToolEventPayload(
                tool_name="Read",
                category="read",
                duration_ms=42,
                success=True,
                files=(
                    ToolFile(path="src/app.py", access="read"),
                    ToolFile(path="src/config.py", access="write"),
                ),
                payload_ref=".ait/objects/ab/cdef",
            ),
        )

    def test_validate_attempt_heartbeat_requires_empty_payload(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-3",
                "event_type": EVENT_ATTEMPT_HEARTBEAT,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {},
            }
        )

        self.assertEqual(envelope.payload, AttemptHeartbeatPayload())

    def test_validate_attempt_finished_payload(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-4",
                "event_type": EVENT_ATTEMPT_FINISHED,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {
                    "exit_code": 0,
                    "raw_trace_ref": ".ait/objects/ab/trace",
                    "logs_ref": ".ait/objects/cd/logs",
                },
            }
        )

        self.assertEqual(
            envelope.payload,
            AttemptFinishedPayload(
                exit_code=0,
                raw_trace_ref=".ait/objects/ab/trace",
                logs_ref=".ait/objects/cd/logs",
            ),
        )

    def test_validate_attempt_finished_with_verification_metrics(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-finver",
                "event_type": EVENT_ATTEMPT_FINISHED,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {
                    "exit_code": 0,
                    "verification": {
                        "tests_run": 10,
                        "tests_passed": 10,
                        "tests_failed": 0,
                        "lint_passed": True,
                        "build_passed": True,
                    },
                },
            }
        )

        assert isinstance(envelope.payload, AttemptFinishedPayload)
        self.assertEqual(
            VerificationMetrics(
                tests_run=10,
                tests_passed=10,
                tests_failed=0,
                lint_passed=True,
                build_passed=True,
            ),
            envelope.payload.verification,
        )

    def test_attempt_finished_verification_rejects_negative_counts(self) -> None:
        with self.assertRaises(ProtocolError):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-finverneg",
                    "event_type": EVENT_ATTEMPT_FINISHED,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {
                        "exit_code": 0,
                        "verification": {"tests_run": -1},
                    },
                }
            )

    def test_attempt_finished_verification_rejects_unknown_key(self) -> None:
        with self.assertRaises(ProtocolError):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-finvertypo",
                    "event_type": EVENT_ATTEMPT_FINISHED,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {
                        "exit_code": 0,
                        "verification": {"tests_runn": 1},
                    },
                }
            )

    def test_validate_attempt_promoted_payload_requires_commit_set(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-5",
                "event_type": EVENT_ATTEMPT_PROMOTED,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {
                    "promotion_ref": "refs/heads/fix/oauth-expiry",
                    "commit_oids": ["abc123"],
                },
            }
        )

        self.assertEqual(
            envelope.payload,
            AttemptPromotedPayload(
                promotion_ref="refs/heads/fix/oauth-expiry",
                commit_oids=("abc123",),
            ),
        )

    def test_validate_attempt_discarded_payload(self) -> None:
        envelope = validate_envelope(
            {
                "schema_version": 1,
                "event_id": "repo:evt-6",
                "event_type": EVENT_ATTEMPT_DISCARDED,
                "sent_at": "2026-04-23T12:34:56Z",
                "attempt_id": "repo:attempt-1",
                "ownership_token": "token-1",
                "payload": {"reason": "user-requested"},
            }
        )

        self.assertEqual(
            envelope.payload,
            AttemptDiscardedPayload(reason="user-requested"),
        )

    def test_encode_ndjson_round_trips(self) -> None:
        original = ProtocolEnvelope(
            schema_version=1,
            event_id="repo:evt-7",
            event_type=EVENT_TOOL_EVENT,
            sent_at="2026-04-23T12:34:56Z",
            attempt_id="repo:attempt-1",
            ownership_token="token-1",
            payload=ToolEventPayload(
                tool_name="Write",
                category="write",
                duration_ms=5,
                success=False,
                files=(ToolFile(path="src/ait/protocol.py", access="write"),),
            ),
        )

        decoded = parse_ndjson_message(encode_ndjson_message(original))

        self.assertEqual(envelope_to_dict(decoded), envelope_to_dict(original))

    def test_rejects_unknown_envelope_key(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "unknown keys"):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-8",
                    "event_type": EVENT_ATTEMPT_HEARTBEAT,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {},
                    "extra": True,
                }
            )

    def test_rejects_invalid_timestamp(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "RFC3339 UTC"):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-9",
                    "event_type": EVENT_ATTEMPT_HEARTBEAT,
                    "sent_at": "2026-04-23 12:34:56",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {},
                }
            )

    def test_rejects_missing_ownership_token(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "ownership_token"):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-10",
                    "event_type": EVENT_ATTEMPT_HEARTBEAT,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "",
                    "payload": {},
                }
            )

    def test_rejects_tool_event_files_with_invalid_access(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "access must be one of"):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-11",
                    "event_type": EVENT_TOOL_EVENT,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {
                        "tool_name": "Edit",
                        "category": "write",
                        "duration_ms": 20,
                        "success": True,
                        "files": [{"path": "src/ait/app.py", "access": "touch"}],
                    },
                }
            )

    def test_rejects_attempt_promoted_without_commits(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "non-empty list"):
            validate_envelope(
                {
                    "schema_version": 1,
                    "event_id": "repo:evt-12",
                    "event_type": EVENT_ATTEMPT_PROMOTED,
                    "sent_at": "2026-04-23T12:34:56Z",
                    "attempt_id": "repo:attempt-1",
                    "ownership_token": "token-1",
                    "payload": {
                        "promotion_ref": "refs/heads/main",
                        "commit_oids": [],
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
