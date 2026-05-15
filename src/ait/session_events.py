from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ait.db import utc_now
from ait.ids import new_ulid
from ait.redaction import redact_text
from ait.transcript import strip_terminal_control


STREAM_EVENT_KINDS = {
    "pty_started",
    "pty_output",
    "pty_input",
    "pty_resize",
    "pty_exited",
    "pty_cancelled",
    "attach_started",
    "attach_detached",
    "route_changed",
}


class SessionEventStore:
    def __init__(self, repo_root: str | Path, session_dir: str | Path, session_id: str) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.session_dir = Path(session_dir).resolve()
        self.session_id = session_id
        self.streams_dir = self.session_dir / "streams"
        self.payloads_dir = self.streams_dir / "payloads"
        self.events_path = self.streams_dir / "events.jsonl"
        self.streams_dir.mkdir(parents=True, exist_ok=True)
        self.payloads_dir.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, **fields: object) -> dict[str, object]:
        if kind not in STREAM_EVENT_KINDS:
            raise ValueError(f"unknown session stream event kind: {kind}")
        event = {
            "schema_version": 1,
            "event_id": f"evt_{new_ulid()}",
            "session_id": self.session_id,
            "seq": self._next_seq(),
            "kind": kind,
            "created_at": utc_now(),
            **fields,
        }
        self._append_json_line(event)
        return event

    def append_payload_event(
        self,
        kind: str,
        payload: bytes,
        **fields: object,
    ) -> dict[str, object]:
        if kind not in {"pty_output", "pty_input"}:
            raise ValueError("payload events are only supported for pty_input/pty_output")
        event_id = f"evt_{new_ulid()}"
        payload_ref = self._relative(self.payloads_dir / f"{event_id}.bin")
        payload_path = self.repo_root / payload_ref
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(payload)
        event = {
            "schema_version": 1,
            "event_id": event_id,
            "session_id": self.session_id,
            "seq": self._next_seq(),
            "kind": kind,
            "created_at": utc_now(),
            "payload_ref": payload_ref,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "byte_count": len(payload),
            "redacted": False,
            **fields,
        }
        self._append_json_line(event)
        return event

    def read_events(self) -> list[dict[str, object]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, object]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events

    def replay_events(self, *, turn_id: str | None = None) -> list[dict[str, object]]:
        replayed: list[dict[str, object]] = []
        for event in self.read_events():
            if turn_id is not None and event.get("turn_id") != turn_id:
                continue
            item = dict(event)
            payload_ref = item.get("payload_ref")
            if isinstance(payload_ref, str):
                raw = self._read_payload(payload_ref)
                text = raw.decode("utf-8", errors="replace")
                text = strip_terminal_control(text)
                text, redacted = redact_text(text)
                item["text"] = text
                item["redacted"] = bool(redacted)
                item.pop("payload_ref", None)
                item.pop("payload_sha256", None)
            replayed.append(item)
        replayed.sort(key=lambda entry: int(entry.get("seq", 0)))
        return replayed

    def _read_payload(self, payload_ref: str) -> bytes:
        try:
            return (self.repo_root / payload_ref).read_bytes()
        except OSError:
            return b""

    def _append_json_line(self, event: dict[str, object]) -> None:
        tmp = self.events_path.with_name(f"{self.events_path.name}.{os.getpid()}.tmp")
        existing = ""
        if self.events_path.exists():
            existing = self.events_path.read_text(encoding="utf-8")
        tmp.write_text(existing + json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.events_path)

    def _next_seq(self) -> int:
        seq = 0
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    try:
                        seq = max(seq, int(item.get("seq", 0)))
                    except (TypeError, ValueError):
                        continue
        return seq + 1

    def _relative(self, path: Path) -> str:
        return path.resolve(strict=False).relative_to(self.repo_root).as_posix()


def terminal_replay_text(events: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for event in events:
        kind = event.get("kind")
        label = event.get("agent_id") or event.get("participant_id") or event.get("pty_id")
        if kind == "pty_output":
            text = str(event.get("text") or "")
            if text:
                for line in text.splitlines():
                    lines.append(f"[{label}] {line}")
        elif kind == "pty_input":
            text = str(event.get("text") or "")
            lines.append(f"[user -> {label}] {text.rstrip()}")
        elif kind in {"pty_cancelled", "pty_exited", "route_changed", "attach_started", "attach_detached"}:
            lines.append(f"[ait] {kind} {label or ''}".rstrip())
    return "\n".join(lines) + ("\n" if lines else "")
