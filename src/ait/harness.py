"""Minimal client harness for the ait daemon.

A harness is any process (AI agent, script, wrapper) doing coding work
under an existing attempt. It uses this module to report lifecycle and
tool events to the daemon so that `EvidenceSummary` accumulates the
observed counters and `evidence_files` records file paths touched.

This implementation is intentionally small. It is not a full-featured
SDK; it just shows the wire protocol working end to end so you can
drive real cycles through the daemon.

Typical usage::

    from ait.harness import AitHarness

    with AitHarness.open(
        attempt_id="<attempt-id-or-suffix>",
        ownership_token="<token>",
        socket_path=Path(".ait/daemon.sock"),
        agent={
            "agent_id": "myhar:worker-1",
            "harness": "myhar",
            "harness_version": "0.1",
        },
    ) as harness:
        harness.record_tool(
            tool_name="Read",
            category="read",
            duration_ms=5,
            success=True,
            files=[{"path": "foo.py", "access": "read"}],
        )
        harness.record_tool(
            tool_name="Edit",
            category="write",
            duration_ms=12,
            success=True,
            files=[{"path": "foo.py", "access": "write"}],
        )
        harness.finish(exit_code=0)

The harness does not create attempts or commits itself; use the `ait`
CLI (`ait attempt new`, `ait attempt commit`, `ait attempt promote`)
for those lifecycle operations. The harness is only responsible for
streaming tool activity into the daemon while work is in progress.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from ait.ids import new_ulid

PROTOCOL_SCHEMA_VERSION = 1


class HarnessError(RuntimeError):
    """Raised on daemon error responses or protocol failures."""


@dataclass
class AitHarness:
    attempt_id: str
    ownership_token: str
    socket_path: Path
    agent: Mapping[str, str]
    _sock: socket.socket | None = field(default=None, repr=False)
    _file: Any | None = field(default=None, repr=False)
    _started: bool = field(default=False, init=False)
    _finished: bool = field(default=False, init=False)

    @classmethod
    def open(
        cls,
        *,
        attempt_id: str,
        ownership_token: str,
        socket_path: str | Path,
        agent: Mapping[str, str],
    ) -> "AitHarness":
        harness = cls(
            attempt_id=attempt_id,
            ownership_token=ownership_token,
            socket_path=Path(socket_path),
            agent=dict(agent),
        )
        harness._connect()
        return harness

    def __enter__(self) -> "AitHarness":
        if not self._started:
            self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if not self._finished:
                self.finish(exit_code=0 if exc is None else 1)
        finally:
            self.close()

    def start(self) -> None:
        self._send(
            event_type="attempt_started",
            payload={"agent": dict(self.agent)},
        )
        self._started = True

    def heartbeat(self) -> None:
        self._send(event_type="attempt_heartbeat", payload={})

    def record_tool(
        self,
        *,
        tool_name: str,
        category: str,
        duration_ms: int,
        success: bool,
        files: Sequence[Mapping[str, str]] = (),
        payload_ref: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "category": category,
            "duration_ms": int(duration_ms),
            "success": bool(success),
        }
        if files:
            payload["files"] = [dict(entry) for entry in files]
        if payload_ref is not None:
            payload["payload_ref"] = payload_ref
        self._send(event_type="tool_event", payload=payload)

    def finish(
        self,
        *,
        exit_code: int,
        raw_trace_ref: str | None = None,
        logs_ref: str | None = None,
        tests_run: int | None = None,
        tests_passed: int | None = None,
        tests_failed: int | None = None,
        lint_passed: bool | None = None,
        build_passed: bool | None = None,
    ) -> None:
        payload: dict[str, Any] = {"exit_code": int(exit_code)}
        if raw_trace_ref is not None:
            payload["raw_trace_ref"] = raw_trace_ref
        if logs_ref is not None:
            payload["logs_ref"] = logs_ref
        verification: dict[str, Any] = {}
        if tests_run is not None:
            verification["tests_run"] = int(tests_run)
        if tests_passed is not None:
            verification["tests_passed"] = int(tests_passed)
        if tests_failed is not None:
            verification["tests_failed"] = int(tests_failed)
        if lint_passed is not None:
            verification["lint_passed"] = bool(lint_passed)
        if build_passed is not None:
            verification["build_passed"] = bool(build_passed)
        if verification:
            payload["verification"] = verification
        self._send(event_type="attempt_finished", payload=payload)
        self._finished = True

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(self.socket_path))
        self._sock = sock
        self._file = sock.makefile("rwb")

    def _send(self, *, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._sock is None or self._file is None:
            raise HarnessError("harness socket is not open")
        envelope = {
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "event_id": f"harness:{new_ulid()}",
            "event_type": event_type,
            "sent_at": _iso_now(),
            "attempt_id": self.attempt_id,
            "ownership_token": self.ownership_token,
            "payload": dict(payload),
        }
        self._file.write((json.dumps(envelope, sort_keys=True) + "\n").encode("utf-8"))
        self._file.flush()
        raw = self._file.readline()
        if not raw:
            raise HarnessError(f"daemon closed the connection before responding to {event_type}")
        response = json.loads(raw.decode("utf-8"))
        if not response.get("ok", False):
            raise HarnessError(
                f"daemon rejected {event_type}: {response.get('error', 'unknown error')}"
            )
        return response


def _iso_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
