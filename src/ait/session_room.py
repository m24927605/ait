from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any

from ait.adapter_models import AdapterError
from ait.adapter_registry import get_adapter
from ait.adapter_wrapper import _find_real_binary
from ait.config import bootstrap_ait_dir, ensure_local_config
from ait.app import init_repo
from ait.db import NewMemoryFact, connect_db, upsert_memory_fact, utc_now
from ait.ids import new_ulid
from ait.memory import discover_live_memory_sources, read_live_memory_source
from ait.redaction import redact_text
from ait.repo import resolve_repo_root
from ait.runner import run_agent_command
from ait.review import create_deterministic_review


SESSION_SCHEMA_VERSION = 1
DEFAULT_SESSION_TIMEOUT_SECONDS = 60
DEFAULT_SESSION_PERMISSION_POLICY: dict[str, str] = {
    "claude_code_permission_mode": "plan",
    "codex_sandbox": "read-only",
    "codex_approval": "never",
}
_REAL_PANEL_COMMANDS: dict[str, tuple[str, ...]] = {
    "claude-code": ("claude", "-p"),
    "codex": ("codex", "exec"),
}


@dataclass(frozen=True, slots=True)
class SessionCommandResult:
    payload: dict[str, object]
    text: str
    exit_code: int = 0


class SessionError(ValueError):
    pass


class SessionStore:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = resolve_repo_root(repo_root)
        self.ait_dir = bootstrap_ait_dir(self.repo_root)
        self.sessions_dir = self.ait_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.repo_id = _repo_id(self.repo_root)

    def start(
        self,
        title: str,
        *,
        agents: tuple[str, ...] = (),
        agent_commands: dict[str, str] | None = None,
        permission_policy: dict[str, str] | None = None,
    ) -> dict[str, object]:
        if not title.strip():
            raise SessionError("session title must not be empty")
        now = utc_now()
        session_id = f"ses_{new_ulid()}"
        participants = [
            _participant_payload(
                session_id=session_id,
                agent=agent,
                role="panelist",
                ordinal=index + 1,
                now=now,
                command_template=(agent_commands or {}).get(agent),
            )
            for index, agent in enumerate(agents)
        ]
        resolved_permission_policy = _normalize_session_permission_policy(permission_policy)
        session = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": session_id,
            "repo_id": self.repo_id,
            "title": title,
            "description": None,
            "state": "active",
            "default_mode": "panel",
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "created_by_actor": {"type": "user", "id": "cli"},
            "root_intent_id": None,
            "participants": participants,
            "turn_count": 0,
            "current_turn_id": None,
            "policy_ref": None,
            "redaction_policy_ref": "ait.redaction.SECRET_PATTERNS",
            "summary_ref": None,
            "metadata_json": {"permission_policy": resolved_permission_policy},
            "permission_policy": resolved_permission_policy,
        }
        session_dir = self._session_dir(session_id)
        for child in (
            "turns",
            "responses",
            "decisions",
            "summaries",
            "contexts",
            "transcripts",
            "allocations",
            "streams",
            "ptys",
            "terminal-runs",
            "reviewer-runs",
        ):
            (session_dir / child).mkdir(parents=True, exist_ok=True)
        self._write_session(session)
        self._append_event(session_id, {"kind": "session_started", "session_id": session_id, "created_at": now})
        self._append_index(session)
        return session

    def add_turn(self, selector: str, message: str) -> tuple[dict[str, object], dict[str, object]]:
        if not message.strip():
            raise SessionError("session turn message must not be empty")
        session = self.load(selector)
        ordinal = int(session.get("turn_count", 0)) + 1
        turn_id = f"turn_{ordinal:04d}"
        now = utc_now()
        session_dir = self._session_dir(str(session["id"]))
        raw_ref = self._relative(session_dir / "turns" / f"{turn_id}-user.txt")
        redacted, changed = redact_text(message)
        redacted_ref = self._relative(session_dir / "turns" / f"{turn_id}-user-redacted.txt")
        self._write_text_ref(raw_ref, message if message.endswith("\n") else message + "\n")
        self._write_text_ref(redacted_ref, redacted if redacted.endswith("\n") else redacted + "\n")
        active_participants = [
            item for item in session.get("participants", [])
            if isinstance(item, dict) and item.get("state") == "active"
        ]
        turn = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": turn_id,
            "session_id": session["id"],
            "ordinal": ordinal,
            "mode": session.get("default_mode", "panel"),
            "user_input_ref": raw_ref,
            "user_input_redacted_ref": redacted_ref,
            "state": "queued",
            "created_at": now,
            "dispatched_at": None,
            "completed_at": None,
            "participants_snapshot": active_participants,
            "context_policy_ref": None,
            "response_ids": [],
            "summary_id": None,
            "blocking_reasons": [],
            "redaction_result": {"user_input_redacted": changed},
        }
        self._write_json_ref(self._turn_ref(str(session["id"]), turn_id), turn)
        session["turn_count"] = ordinal
        session["current_turn_id"] = turn_id
        session["updated_at"] = now
        self._write_session(session)
        self._append_event(str(session["id"]), {"kind": "turn_added", "turn_id": turn_id, "created_at": now})
        return session, turn

    def list_sessions(self) -> list[dict[str, object]]:
        sessions: list[dict[str, object]] = []
        for path in sorted(self.sessions_dir.glob("ses_*/session.json")):
            try:
                sessions.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        sessions.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return sessions

    def load(self, selector: str = "latest") -> dict[str, object]:
        if selector == "latest":
            sessions = self.list_sessions()
            if not sessions:
                raise SessionError("no AIT session exists")
            return sessions[0]
        matches = [item for item in self.list_sessions() if str(item.get("id")) == selector or str(item.get("id", "")).startswith(selector)]
        if not matches:
            raise SessionError(f"session not found: {selector}")
        if len(matches) > 1:
            raise SessionError(f"ambiguous session selector: {selector}")
        return matches[0]

    def show(self, selector: str = "latest") -> dict[str, object]:
        session = self.load(selector)
        return self.state_payload(session)

    def participant_list(self, selector: str) -> dict[str, object]:
        session = self.load(selector)
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "kind": "session_participants",
            "session_id": session["id"],
            "participants": list(session.get("participants", [])),
            "next_action": _next_action(f"ait session ask {session['id']} \"...\""),
        }

    def participant_add(
        self,
        selector: str,
        *,
        agent: str,
        role: str = "panelist",
        command_template: str | None = None,
    ) -> dict[str, object]:
        session = self.load(selector)
        participants = [dict(item) for item in session.get("participants", []) if isinstance(item, dict)]
        now = utc_now()
        participant = _participant_payload(
            session_id=str(session["id"]),
            agent=agent,
            role=role,
            ordinal=len(participants) + 1,
            now=now,
            state="active",
            command_template=command_template,
        )
        participants.append(participant)
        session["participants"] = participants
        session["updated_at"] = now
        self._write_session(session)
        self._append_event(str(session["id"]), {"kind": "participant_added", "participant_id": participant["id"], "created_at": now})
        return self.state_payload(session)

    def participant_remove(
        self,
        selector: str,
        *,
        participant_id: str | None = None,
        agent: str | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        session = self.load(selector)
        participants = [dict(item) for item in session.get("participants", []) if isinstance(item, dict)]
        match = None
        for item in participants:
            if participant_id and item.get("id") == participant_id:
                match = item
                break
            if agent and item.get("agent_id") == agent:
                match = item
                break
        if match is None:
            raise SessionError("participant not found")
        now = utc_now()
        match["state"] = "removed"
        match["removed_at"] = now
        match["removed_by_actor"] = {"type": "user", "id": "cli"}
        match["remove_reason"] = reason or ""
        session["participants"] = participants
        session["updated_at"] = now
        self._write_session(session)
        self._append_event(str(session["id"]), {"kind": "participant_removed", "participant_id": match["id"], "created_at": now})
        return self.state_payload(session)

    def run_panel(
        self,
        selector: str,
        *,
        timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS,
        retry_response_id: str | None = None,
        mode: str = "panel",
    ) -> dict[str, object]:
        session = self.load(selector)
        turn = self._current_turn(session)
        participants = [
            dict(item)
            for item in session.get("participants", [])
            if isinstance(item, dict) and item.get("state") == "active"
        ]
        if retry_response_id is not None:
            original = self._load_response(str(session["id"]), retry_response_id)
            participants = [
                item for item in participants if item.get("id") == original.get("participant_id")
            ]
            if not participants:
                raise SessionError("original response participant is not active")
        if not participants:
            raise SessionError("session has no active participants")
        now = utc_now()
        turn["state"] = "running"
        turn["mode"] = mode
        turn["dispatched_at"] = now
        self._write_json_ref(self._turn_ref(str(session["id"]), str(turn["id"])), turn)
        response_ids = list(turn.get("response_ids", []))
        for participant in participants:
            response = self._invoke_panel_participant(
                session=session,
                turn=turn,
                participant=participant,
                timeout_seconds=timeout_seconds,
                retry_response_id=retry_response_id,
            )
            response_ids.append(str(response["id"]))
        completed = [self._load_response(str(session["id"]), response_id) for response_id in response_ids]
        turn["response_ids"] = response_ids
        turn["state"] = "partial" if any(item.get("state") in {"failed", "timed_out", "cancelled"} for item in completed) else "completed"
        turn["completed_at"] = utc_now()
        summary = self._write_summary(session, turn, completed)
        turn["summary_id"] = summary["id"]
        self._write_json_ref(self._turn_ref(str(session["id"]), str(turn["id"])), turn)
        session["state"] = "awaiting_decision"
        session["updated_at"] = utc_now()
        session["summary_ref"] = summary["body_ref"]
        self._write_session(session)
        return self.state_payload(session)

    def retry_response(self, selector: str, response_id: str, *, timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS) -> dict[str, object]:
        return self.run_panel(selector, timeout_seconds=timeout_seconds, retry_response_id=response_id)

    def cancel(self, selector: str, *, response_id: str | None = None) -> dict[str, object]:
        session = self.load(selector)
        turn = self._current_turn(session)
        targets = list(turn.get("response_ids", []))
        if response_id is not None:
            targets = [response_id]
        now = utc_now()
        for target in targets:
            try:
                response = self._load_response(str(session["id"]), target)
            except SessionError:
                continue
            if response.get("state") in {"completed", "failed", "timed_out", "cancelled"}:
                continue
            response["state"] = "cancelled"
            response["cancellation_reason"] = "cancelled by user"
            response["ended_at"] = now
            self._write_json_ref(self._response_ref(str(session["id"]), str(response["id"])), response)
        self._append_event(str(session["id"]), {"kind": "session_cancel", "response_id": response_id, "created_at": now})
        return self.state_payload(session)

    def decision_accept(self, selector: str, *, accept_id: str, promote_memory: bool = False) -> dict[str, object]:
        session = self.load(selector)
        turn = self._current_turn(session)
        now = utc_now()
        decision_id = f"dec_{new_ulid()}"
        promoted_fact_id = None
        if promote_memory:
            promoted_fact_id = self._promote_decision_memory(session, turn, source_id=accept_id)
        decision = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": decision_id,
            "session_id": session["id"],
            "turn_id": turn["id"],
            "actor": {"type": "user", "id": "cli"},
            "decision_type": "accept_response",
            "selected_response_id": accept_id if str(accept_id).startswith("rsp_") else None,
            "selected_proposal_id": None,
            "accepted_summary": accept_id if str(accept_id).startswith("sum_") else None,
            "state": "accepted",
            "rationale": "",
            "created_at": now,
            "links": {"source_id": accept_id},
            "memory_promotion_status": "accepted" if promoted_fact_id else ("requested" if promote_memory else "not_requested"),
            "memory_fact_id": promoted_fact_id,
            "attempt_id": None,
            "review_id": None,
            "apply_status": "not_applied",
        }
        self._write_json_ref(self._relative(self._session_dir(str(session["id"])) / "decisions" / f"{decision_id}.json"), decision)
        session["state"] = "active"
        session["updated_at"] = now
        self._write_session(session)
        return self.state_payload(session)

    def create_attempt_from_response(
        self,
        selector: str,
        *,
        source_id: str,
        agent: str | None = None,
    ) -> dict[str, object]:
        session = self.load(selector)
        source = self._load_response(str(session["id"]), source_id)
        if source.get("attempt_id"):
            payload = self.state_payload(session)
            payload["attempt"] = {
                "source_response_id": source_id,
                "attempt_id": source["attempt_id"],
                "created": False,
                "reason": "source response already links to an isolated attempt",
            }
            return payload
        response_id = f"rsp_{new_ulid()}"
        body = _read_ref_text(self.repo_root, str(source.get("redacted_response_ref") or ""))
        target_agent = agent or str(source.get("agent_id") or "session:attempt")
        code = (
            "from pathlib import Path\n"
            "path = Path('session-attempts') / 'from-response.txt'\n"
            "path.parent.mkdir(parents=True, exist_ok=True)\n"
            f"path.write_text({body!r}, encoding='utf-8')\n"
        )
        result = run_agent_command(
            self.repo_root,
            intent_title=f"{session.get('title')}: attempt from {source_id}",
            command=[sys.executable, "-c", code],
            agent_id=target_agent,
            adapter_name="shell",
            kind="session-attempt-from-response",
            description=f"AIT session {session['id']} attempt from response {source_id}",
            auto_commit=True,
            with_context=False,
            capture_command_output=True,
        )
        turn = self._current_turn(session)
        response = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": response_id,
            "session_id": session["id"],
            "turn_id": turn["id"],
            "participant_id": _participant_for_agent(session, target_agent),
            "agent_id": target_agent,
            "adapter_name": "shell",
            "role": "implementer",
            "state": "completed" if result.exit_code == 0 else "failed",
            "invocation_id": f"inv_{new_ulid()}",
            "command_ref": None,
            "context_manifest_ref": None,
            "stdout_ref": None,
            "stderr_ref": None,
            "raw_trace_ref": result.attempt.attempt.get("raw_trace_ref"),
            "redacted_response_ref": None,
            "exit_code": result.exit_code,
            "started_at": result.attempt.attempt.get("started_at"),
            "ended_at": result.attempt.attempt.get("ended_at"),
            "timeout_seconds": None,
            "cancellation_reason": None,
            "provenance": {
                "captured_by": "ait-session-attempt",
                "source_response_id": source_id,
                "workspace_ref": result.workspace_ref,
                "changed_files": list(result.attempt.files.get("changed", ())),
            },
            "trust_class": "attempt_result",
            "proposal_ids": [],
            "attempt_id": result.attempt_id,
            "review_id": None,
            "metadata_json": {},
        }
        response.update(
            self._persist_response_output(
                str(session["id"]),
                response_id,
                stdout=result.command_stdout or "",
                stderr=result.command_stderr or "",
            )
        )
        self._write_json_ref(self._response_ref(str(session["id"]), response_id), response)
        turn["response_ids"] = [*list(turn.get("response_ids", [])), response_id]
        self._write_json_ref(self._turn_ref(str(session["id"]), str(turn["id"])), turn)
        payload = self.state_payload(session)
        payload["attempt"] = {
            "source_response_id": source_id,
            "attempt_id": result.attempt_id,
            "created": True,
            "auto_apply": False,
        }
        return payload

    def allocation_plan(
        self,
        selector: str,
        *,
        agents: tuple[str, ...],
        strategy: str = "adaptive",
        packages: tuple[str, ...] = (),
    ) -> dict[str, object]:
        session = self.load(selector)
        turn = self._current_turn_or_none(session)
        now = utc_now()
        plan_id = f"alloc_{new_ulid()}"
        parsed_packages = _parse_packages(packages)
        if not parsed_packages:
            parsed_packages = {
                _slug(agent or f"agent-{index + 1}"): ("**/*",)
                for index, agent in enumerate(agents)
            }
        work_packages = []
        agent_list = list(agents) or [
            str(item.get("agent_id"))
            for item in session.get("participants", [])
            if isinstance(item, dict) and item.get("state") == "active"
        ]
        confidence = "medium"
        blocking_reasons: list[str] = []
        if not agent_list:
            confidence = "low"
            blocking_reasons.append("no agents available for allocation")
        for index, (name, scopes) in enumerate(parsed_packages.items()):
            agent = agent_list[index % len(agent_list)] if agent_list else ""
            work_packages.append(
                {
                    "id": f"pkg_{new_ulid()}",
                    "session_id": session["id"],
                    "allocation_plan_id": plan_id,
                    "title": name,
                    "scope_paths": list(scopes),
                    "excluded_paths": [],
                    "role": "implementer",
                    "assigned_participant_id": _participant_for_agent(session, agent),
                    "assigned_agent_id": agent,
                    "state": "proposed",
                    "depends_on_package_ids": [],
                    "risk_level": "medium",
                    "expected_outputs": ["isolated attempt", "review evidence"],
                    "attempt_id": None,
                    "review_id": None,
                    "overlap_status": "unknown",
                    "created_at": now,
                    "updated_at": now,
                    "rationale": f"assigned by {strategy} strategy using repo-local session evidence",
                }
            )
        plan = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": plan_id,
            "session_id": session["id"],
            "turn_id": None if turn is None else turn["id"],
            "strategy": strategy,
            "state": "blocked" if blocking_reasons else "draft",
            "created_by": {"type": "ait", "id": "session-allocation"},
            "created_at": now,
            "input_refs": {
                "session_id": session["id"],
                "turn_id": None if turn is None else turn["id"],
            },
            "scoring_factors": [
                "user_goal",
                "active_participants",
                "path_scope",
                "role_capabilities",
                "overlap_risk",
                "no_telemetry",
            ],
            "work_packages": work_packages,
            "recommended_next_action": None if blocking_reasons else f"ait session allocation accept {session['id']} --plan {plan_id}",
            "safe_actions": [] if blocking_reasons else [f"ait session allocation accept {session['id']} --plan {plan_id}"],
            "unsafe_actions": ["ait apply latest"],
            "blocking_reasons": blocking_reasons,
            "confidence": confidence,
            "rationale_ref": None,
            "no_invocation": True,
            "no_repo_mutation": True,
        }
        self._write_json_ref(self._allocation_ref(str(session["id"]), plan_id), plan)
        return plan

    def allocation_accept(self, selector: str, *, plan_id: str) -> dict[str, object]:
        session = self.load(selector)
        plan = self._load_allocation(str(session["id"]), plan_id)
        if plan.get("state") == "blocked":
            raise SessionError("cannot accept blocked allocation plan")
        plan["state"] = "accepted"
        plan["accepted_at"] = utc_now()
        self._write_json_ref(self._allocation_ref(str(session["id"]), str(plan["id"])), plan)
        self._append_event(str(session["id"]), {"kind": "allocation_accepted", "allocation_plan_id": plan["id"], "created_at": utc_now()})
        return self.state_payload(session, allocation=plan)

    def run_role(
        self,
        selector: str,
        *,
        implementers: tuple[str, ...],
        reviewers: tuple[str, ...] = (),
        allocation_plan_id: str | None = None,
        packages: tuple[str, ...] = (),
    ) -> dict[str, object]:
        session = self.load(selector)
        turn = self._current_turn(session)
        parsed_packages = _parse_packages(packages)
        assignments: list[tuple[str, str, tuple[str, ...]]] = []
        if allocation_plan_id:
            plan = self._load_allocation(str(session["id"]), allocation_plan_id)
            if plan.get("state") != "accepted":
                raise SessionError("allocation plan must be accepted before role dispatch")
            for package in plan.get("work_packages", []):
                if isinstance(package, dict):
                    assignments.append((
                        str(package.get("assigned_agent_id") or ""),
                        str(package.get("title") or "package"),
                        tuple(str(path) for path in package.get("scope_paths", [])),
                    ))
        else:
            for index, agent in enumerate(implementers):
                package_name = f"package-{index + 1}"
                scopes = ("session-output.txt",)
                if parsed_packages:
                    package_name, scopes = list(parsed_packages.items())[index % len(parsed_packages)]
                assignments.append((agent, package_name, scopes))
        if not assignments:
            raise SessionError("role mode requires at least one implementer or accepted allocation")
        response_ids = list(turn.get("response_ids", []))
        attempts: list[dict[str, object]] = []
        for agent, package_name, scopes in assignments:
            response = self._run_implementer(session, turn, agent=agent, package_name=package_name, scopes=scopes)
            response_ids.append(str(response["id"]))
            attempts.append(response)
        review_responses: list[dict[str, object]] = []
        for attempt_response in attempts:
            attempt_id = attempt_response.get("attempt_id")
            if not attempt_id:
                continue
            for reviewer in reviewers:
                review_response = self._run_reviewer(session, turn, reviewer=reviewer, target_attempt_id=str(attempt_id))
                response_ids.append(str(review_response["id"]))
                review_responses.append(review_response)
        integration = self._write_integration_plan(session, attempts)
        turn["mode"] = "role"
        turn["response_ids"] = response_ids
        turn["state"] = "partial" if integration.get("status") == "blocked" else "completed"
        turn["blocking_reasons"] = list(integration.get("blocking_reasons", []))
        turn["completed_at"] = utc_now()
        self._write_json_ref(self._turn_ref(str(session["id"]), str(turn["id"])), turn)
        session["state"] = "awaiting_decision"
        session["updated_at"] = utc_now()
        self._write_session(session)
        payload = self.state_payload(session)
        payload["integration"] = integration
        payload["attempt_responses"] = attempts
        payload["review_responses"] = review_responses
        return payload

    def responses(self, selector: str) -> list[dict[str, object]]:
        session = self.load(selector)
        responses = []
        for path in sorted((self._session_dir(str(session["id"])) / "responses").glob("*.json")):
            responses.append(json.loads(path.read_text(encoding="utf-8")))
        return responses

    def export_markdown(self, selector: str) -> str:
        session = self.load(selector)
        lines = [
            f"# AIT Session: {session.get('title')}",
            "",
            f"- Session: `{session.get('id')}`",
            f"- State: `{session.get('state')}`",
            "",
        ]
        for turn in self._turns(str(session["id"])):
            lines.extend([
                f"## Turn {turn.get('ordinal')}: `{turn.get('id')}`",
                "",
                "User:",
                "",
                _read_ref_text(self.repo_root, str(turn.get("user_input_redacted_ref") or "")).rstrip(),
                "",
            ])
            for response_id in turn.get("response_ids", []):
                response = self._load_response(str(session["id"]), str(response_id))
                body = _read_ref_text(self.repo_root, str(response.get("redacted_response_ref") or "")).rstrip()
                lines.extend([
                    f"### {response.get('agent_id')} · `{response.get('id')}` · {response.get('state')}",
                    "",
                    body,
                    "",
                ])
            if turn.get("summary_id"):
                summary = self._load_summary(str(session["id"]), str(turn["summary_id"]))
                lines.extend([
                    "### AIT Summary",
                    "",
                    _read_ref_text(self.repo_root, str(summary.get("body_ref") or "")).rstrip(),
                    "",
                ])
        return "\n".join(lines).rstrip() + "\n"

    def state_payload(self, session: dict[str, object], *, allocation: dict[str, object] | None = None) -> dict[str, object]:
        turn = self._current_turn_or_none(session)
        response_ids = [] if turn is None else list(turn.get("response_ids", []))
        responses = []
        for response_id in response_ids:
            try:
                response = self._load_response(str(session["id"]), str(response_id))
            except SessionError:
                continue
            responses.append(_response_summary(response))
        blocking_reasons = [] if turn is None else list(turn.get("blocking_reasons", []))
        has_attempt = any(item.get("attempt_id") for item in responses)
        recommended = f"ait session ask {session['id']} \"...\""
        if turn is not None and responses:
            recommended = f"ait session decision {session['id']} --accept {responses[0]['response_id']}"
        payload = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "kind": "session_state",
            "session_id": session["id"],
            "state": session.get("state"),
            "mode": None if turn is None else turn.get("mode"),
            "current_turn_id": session.get("current_turn_id"),
            "participants": [
                {
                    "participant_id": item.get("id"),
                    "agent_id": item.get("agent_id"),
                    "role": item.get("role"),
                    "state": item.get("state"),
                }
                for item in session.get("participants", [])
                if isinstance(item, dict)
            ],
            "permission_policy": _session_permission_policy(session),
            "responses": responses,
            "summary": None if turn is None or not turn.get("summary_id") else self._load_summary(str(session["id"]), str(turn["summary_id"])),
            "next_action": _next_action(recommended),
            "safe_actions": _safe_actions(session, has_attempt=has_attempt),
            "unsafe_actions": [
                {"command": "ait apply latest", "reason": "session decisions do not apply changes directly"}
            ] if not has_attempt else [
                {"command": "ait apply latest", "reason": "use the explicit attempt id after review gate checks"}
            ],
            "blocking_reasons": blocking_reasons,
            "partial_failures": [
                item for item in responses if item.get("state") in {"failed", "timed_out", "cancelled"}
            ],
            "provenance_refs": [self._relative(self._session_dir(str(session["id"])) / "events.jsonl")],
        }
        if allocation is not None:
            payload["allocation"] = allocation
        return payload

    def _invoke_panel_participant(
        self,
        *,
        session: dict[str, object],
        turn: dict[str, object],
        participant: dict[str, object],
        timeout_seconds: int,
        retry_response_id: str | None,
    ) -> dict[str, object]:
        response_id = f"rsp_{new_ulid()}"
        started = utc_now()
        context_ref, context_manifest_ref = self._write_context(session, turn, participant)
        response = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": response_id,
            "session_id": session["id"],
            "turn_id": turn["id"],
            "participant_id": participant["id"],
            "agent_id": participant["agent_id"],
            "adapter_name": participant.get("adapter_name", "fake"),
            "role": participant.get("role", "panelist"),
            "state": "invoked",
            "invocation_id": f"inv_{new_ulid()}",
            "command_ref": None,
            "context_manifest_ref": context_manifest_ref,
            "context_ref": context_ref,
            "stdout_ref": None,
            "stderr_ref": None,
            "raw_trace_ref": None,
            "redacted_response_ref": None,
            "exit_code": None,
            "started_at": started,
            "ended_at": None,
            "timeout_seconds": timeout_seconds,
            "cancellation_reason": None,
            "provenance": {
                "retry_of_response_id": retry_response_id,
                "captured_by": "ait-session-panel",
            },
            "trust_class": "advisory",
            "proposal_ids": [],
            "attempt_id": None,
            "review_id": None,
            "metadata_json": {},
        }
        command_template = participant.get("command_template")
        if isinstance(command_template, str) and command_template.strip():
            command_ref = self._relative(self._session_dir(str(session["id"])) / "transcripts" / f"{response_id}.command.txt")
            self._write_text_ref(command_ref, command_template.strip() + "\n")
            response["command_ref"] = command_ref
            stdout, stderr, exit_code, state = self._invoke_local_command(
                command_template,
                context_ref=context_ref,
                session_id=str(session["id"]),
                response_id=response_id,
                timeout_seconds=timeout_seconds,
            )
        else:
            agent_id = str(participant["agent_id"])
            if agent_id.startswith("fake:"):
                stdout, stderr, exit_code, state = _invoke_agent(agent_id, timeout_seconds=timeout_seconds)
            else:
                prompt = self._panel_agent_prompt(session, turn, participant, context_ref=context_ref)
                stdout, stderr, exit_code, state, command = self._invoke_real_panel_agent(
                    agent_id,
                    prompt=prompt,
                    context_ref=context_ref,
                    permission_policy=_session_permission_policy(session),
                    session_id=str(session["id"]),
                    response_id=response_id,
                    timeout_seconds=timeout_seconds,
                )
                command_ref = self._relative(self._session_dir(str(session["id"])) / "transcripts" / f"{response_id}.command.txt")
                self._write_text_ref(command_ref, " ".join(shlex.quote(part) for part in command) + "\n")
                response["command_ref"] = command_ref
        response.update(self._persist_response_output(str(session["id"]), response_id, stdout=stdout, stderr=stderr))
        response["exit_code"] = exit_code
        response["state"] = state
        response["ended_at"] = utc_now()
        self._write_json_ref(self._response_ref(str(session["id"]), response_id), response)
        self._append_event(str(session["id"]), {"kind": "response_recorded", "response_id": response_id, "created_at": response["ended_at"]})
        return response

    def _run_implementer(
        self,
        session: dict[str, object],
        turn: dict[str, object],
        *,
        agent: str,
        package_name: str,
        scopes: tuple[str, ...],
    ) -> dict[str, object]:
        response_id = f"rsp_{new_ulid()}"
        target_path = _path_for_scope(scopes[0] if scopes else f"{package_name}.txt")
        code = (
            "from pathlib import Path\n"
            f"path = Path({target_path!r})\n"
            "path.parent.mkdir(parents=True, exist_ok=True)\n"
            f"path.write_text('implemented by {agent} for {package_name}\\n', encoding='utf-8')\n"
        )
        result = run_agent_command(
            self.repo_root,
            intent_title=f"{session.get('title')}: {package_name}",
            command=[sys.executable, "-c", code],
            agent_id=agent,
            adapter_name="shell",
            kind="session-role-implementer",
            description=f"AIT session {session['id']} package {package_name}",
            auto_commit=True,
            with_context=True,
            capture_command_output=True,
        )
        response = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": response_id,
            "session_id": session["id"],
            "turn_id": turn["id"],
            "participant_id": _participant_for_agent(session, agent),
            "agent_id": agent,
            "adapter_name": "shell",
            "role": "implementer",
            "state": "completed" if result.exit_code == 0 else "failed",
            "invocation_id": f"inv_{new_ulid()}",
            "command_ref": None,
            "context_manifest_ref": None,
            "stdout_ref": None,
            "stderr_ref": None,
            "raw_trace_ref": result.attempt.attempt.get("raw_trace_ref"),
            "redacted_response_ref": None,
            "exit_code": result.exit_code,
            "started_at": result.attempt.attempt.get("started_at"),
            "ended_at": result.attempt.attempt.get("ended_at"),
            "timeout_seconds": None,
            "cancellation_reason": None,
            "provenance": {
                "captured_by": "ait-session-role",
                "workspace_ref": result.workspace_ref,
                "changed_files": list(result.attempt.files.get("changed", ())),
                "commits": [item.get("commit_oid") for item in result.attempt.commits],
            },
            "trust_class": "attempt_result",
            "proposal_ids": [],
            "attempt_id": result.attempt_id,
            "review_id": None,
            "package_name": package_name,
            "scope_paths": list(scopes),
            "metadata_json": {},
        }
        response.update(
            self._persist_response_output(
                str(session["id"]),
                response_id,
                stdout=result.command_stdout or "",
                stderr=result.command_stderr or "",
            )
        )
        self._write_json_ref(self._response_ref(str(session["id"]), response_id), response)
        return response

    def _run_reviewer(
        self,
        session: dict[str, object],
        turn: dict[str, object],
        *,
        reviewer: str,
        target_attempt_id: str,
    ) -> dict[str, object]:
        result = create_deterministic_review(self.repo_root, target_attempt_id)
        response_id = f"rsp_{new_ulid()}"
        body = (
            f"Review target: {target_attempt_id}\n"
            f"Review: {result.review.id}\n"
            f"Risk: {result.assessment.risk_level} ({result.assessment.risk_score})\n"
        )
        response = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": response_id,
            "session_id": session["id"],
            "turn_id": turn["id"],
            "participant_id": _participant_for_agent(session, reviewer),
            "agent_id": reviewer,
            "adapter_name": "review",
            "role": "reviewer",
            "state": "completed",
            "invocation_id": f"inv_{new_ulid()}",
            "command_ref": None,
            "context_manifest_ref": None,
            "stdout_ref": None,
            "stderr_ref": None,
            "raw_trace_ref": None,
            "redacted_response_ref": None,
            "exit_code": 0,
            "started_at": utc_now(),
            "ended_at": utc_now(),
            "timeout_seconds": None,
            "cancellation_reason": None,
            "provenance": {
                "captured_by": "ait-session-review",
                "target_attempt_id": target_attempt_id,
                "artifact_ref": result.review.artifact_ref,
                "baseline_ref": result.review.baseline_ref,
            },
            "trust_class": "review_evidence",
            "proposal_ids": [],
            "attempt_id": None,
            "review_id": result.review.id,
            "metadata_json": {},
        }
        response.update(self._persist_response_output(str(session["id"]), response_id, stdout=body, stderr=""))
        self._write_json_ref(self._response_ref(str(session["id"]), response_id), response)
        return response

    def _write_context(
        self,
        session: dict[str, object],
        turn: dict[str, object],
        participant: dict[str, object],
    ) -> tuple[str, str]:
        session_id = str(session["id"])
        turn_id = str(turn["id"])
        participant_id = str(participant["id"])
        context_path = self._session_dir(session_id) / "contexts" / f"{turn_id}-{participant_id}.md"
        manifest_path = self._session_dir(session_id) / "contexts" / f"{turn_id}-{participant_id}-manifest.json"
        user_text = _read_ref_text(self.repo_root, str(turn.get("user_input_redacted_ref") or ""))
        live_sources = discover_live_memory_sources(self.repo_root)
        source_manifest = []
        policy_exclusions = []
        memory_lines = []
        for source in live_sources:
            item = source.to_dict()
            if source.allowed_by_policy and source.exists:
                text, redacted, bytes_used = read_live_memory_source(source, max_chars=1200)
                item["bytes_used"] = bytes_used
                item["redacted"] = redacted
                if text:
                    memory_lines.append(f"- {source.source_id}: {text[:400].strip()}")
            else:
                policy_exclusions.append(item)
            source_manifest.append(item)
        advisory_refs = [
            response["id"]
            for response in self.responses(session_id)
            if response.get("turn_id") != turn_id and response.get("trust_class") == "advisory"
        ]
        accepted_decision_refs = self._accepted_decision_refs(session_id)
        context_text = "\n".join(
            [
                f"# AIT session context for {participant.get('agent_id')}",
                "",
                "Trust classes:",
                "- trusted_baseline: accepted AIT evidence and allowed live source text",
                "- advisory_response: prior agent response, attributed and not fact",
                "",
                "User turn:",
                user_text.strip(),
                "",
                "Live federated memory:",
                *memory_lines,
                "",
                "Prior advisory response refs:",
                *[f"- {item}" for item in advisory_refs],
                "",
                "Accepted session decision refs:",
                *[f"- {item}" for item in accepted_decision_refs],
                "",
            ]
        )
        redacted_context, changed = redact_text(context_text)
        context_path.write_text(redacted_context, encoding="utf-8")
        manifest = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": f"ctx_{new_ulid()}",
            "session_id": session_id,
            "turn_id": turn_id,
            "participant_id": participant_id,
            "agent_id": participant.get("agent_id"),
            "context_ref": self._relative(context_path),
            "created_at": utc_now(),
            "trusted_baseline_refs": [item.get("source_id") for item in source_manifest if item.get("allowed_by_policy")],
            "live_memory_source_manifest": source_manifest,
            "accepted_decision_refs": accepted_decision_refs,
            "prior_response_refs": advisory_refs,
            "advisory_response_refs": advisory_refs,
            "policy_exclusions": policy_exclusions,
            "redaction_result": {"context_redacted": changed},
            "budget_chars": len(redacted_context),
            "content_sha256": hashlib.sha256(redacted_context.encode("utf-8")).hexdigest(),
            "write_mode": "session_context_artifact",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self._relative(context_path), self._relative(manifest_path)

    def _accepted_decision_refs(self, session_id: str) -> list[str]:
        refs: list[str] = []
        for path in sorted((self._session_dir(session_id) / "decisions").glob("*.json")):
            try:
                decision = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if decision.get("state") == "accepted":
                refs.append(str(decision.get("id")))
        return refs

    def _invoke_local_command(
        self,
        command_template: str,
        *,
        context_ref: str,
        session_id: str,
        response_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str, int | None, str]:
        run_dir = self._session_dir(session_id) / "local-runs" / response_id
        run_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "AIT_CONTEXT_FILE": str((self.repo_root / context_ref).resolve()),
            "AIT_SESSION_ID": session_id,
            "AIT_RESPONSE_ID": response_id,
            "AIT_REPO_ROOT": str(self.repo_root),
        }
        try:
            completed = subprocess.run(
                command_template,
                cwd=run_dir,
                env=env,
                shell=True,
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return exc.stdout or "", exc.stderr or "timed out\n", None, "timed_out"
        return completed.stdout or "", completed.stderr or "", completed.returncode, "completed" if completed.returncode == 0 else "failed"

    def _invoke_real_panel_agent(
        self,
        agent_id: str,
        *,
        prompt: str,
        context_ref: str,
        permission_policy: dict[str, str],
        session_id: str,
        response_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str, int | None, str, tuple[str, ...]]:
        adapter_name = _adapter_for_agent(agent_id)
        command = _real_panel_command(adapter_name, self.repo_root, permission_policy)
        if command is None:
            return (
                "",
                f"real panel/council invocation is not configured for agent {agent_id}\n",
                127,
                "failed",
                (agent_id,),
            )
        run_dir = self._session_dir(session_id) / "local-runs" / response_id
        run_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "AIT_CONTEXT_FILE": str((self.repo_root / context_ref).resolve()),
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before answering.",
            "AIT_SESSION_ID": session_id,
            "AIT_RESPONSE_ID": response_id,
            "AIT_REPO_ROOT": str(self.repo_root),
            "AIT_SESSION_MODE": "panel",
            "AIT_PANEL_ADVISORY_ONLY": "1",
        }
        try:
            completed = subprocess.run(
                list(command),
                cwd=self.repo_root if adapter_name in _REAL_PANEL_COMMANDS else run_dir,
                env=env,
                input=prompt,
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return exc.stdout or "", exc.stderr or "timed out\n", None, "timed_out", command
        except OSError as exc:
            return "", f"real panel/council invocation failed: {exc}\n", 127, "failed", command
        return (
            completed.stdout or "",
            completed.stderr or "",
            completed.returncode,
            "completed" if completed.returncode == 0 else "failed",
            command,
        )

    def _panel_agent_prompt(
        self,
        session: dict[str, object],
        turn: dict[str, object],
        participant: dict[str, object],
        *,
        context_ref: str,
    ) -> str:
        user_text = _read_ref_text(self.repo_root, str(turn.get("user_input_redacted_ref") or "")).strip()
        context_path = (self.repo_root / context_ref).resolve()
        return "\n".join(
            [
                f"You are {participant.get('agent_id')} in AIT session {session.get('id')}.",
                "This is panel/council mode: respond with advisory analysis only.",
                "Do not edit files, do not apply changes, and do not mutate the repository.",
                f"Read the repo-local handoff context from AIT_CONTEXT_FILE: {context_path}",
                "",
                "User turn:",
                user_text,
                "",
            ]
        )

    def _persist_response_output(
        self,
        session_id: str,
        response_id: str,
        *,
        stdout: str,
        stderr: str,
    ) -> dict[str, object]:
        transcript_dir = self._session_dir(session_id) / "transcripts"
        stdout_ref = self._relative(transcript_dir / f"{response_id}.stdout.txt")
        stderr_ref = self._relative(transcript_dir / f"{response_id}.stderr.txt")
        raw_trace_ref = self._relative(transcript_dir / f"{response_id}.raw.txt")
        redacted_ref = self._relative(transcript_dir / f"{response_id}.redacted.md")
        self._write_text_ref(stdout_ref, stdout)
        self._write_text_ref(stderr_ref, stderr)
        raw = "\n".join([stdout, stderr]).strip() + "\n"
        self._write_text_ref(raw_trace_ref, raw)
        redacted, changed = redact_text(raw)
        self._write_text_ref(redacted_ref, redacted)
        return {
            "stdout_ref": stdout_ref,
            "stderr_ref": stderr_ref,
            "raw_trace_ref": raw_trace_ref,
            "redacted_response_ref": redacted_ref,
            "redaction_result": {"response_redacted": changed},
        }

    def _write_summary(
        self,
        session: dict[str, object],
        turn: dict[str, object],
        responses: list[dict[str, object]],
    ) -> dict[str, object]:
        summary_id = f"sum_{new_ulid()}"
        completed = [item for item in responses if item.get("state") == "completed"]
        failed = [item for item in responses if item.get("state") != "completed"]
        lines = [
            f"Source responses: {', '.join(str(item.get('id')) for item in responses)}",
            f"Completed: {len(completed)}",
            f"Partial failures: {len(failed)}",
            "Agreement: review individual responses before creating an attempt.",
            "Next: record a session decision or create an isolated attempt.",
        ]
        body = "\n".join(lines) + "\n"
        body_ref = self._relative(self._session_dir(str(session["id"])) / "summaries" / f"{summary_id}.md")
        json_ref = self._relative(self._session_dir(str(session["id"])) / "summaries" / f"{summary_id}.json")
        self._write_text_ref(body_ref, body)
        summary = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": summary_id,
            "session_id": session["id"],
            "turn_ids": [turn["id"]],
            "source_response_ids": [item.get("id") for item in responses],
            "summary_kind": "turn_summary",
            "body_ref": body_ref,
            "json_ref": json_ref,
            "created_by": {"type": "ait", "id": "deterministic-summary"},
            "created_at": utc_now(),
            "deterministic_ordering": ["turn", "participant", "response"],
            "redaction_result": {"summary_redacted": False},
            "agreements": ["responses remain attributable"],
            "conflicts": [],
        }
        self._write_text_ref(json_ref, json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return summary

    def _write_integration_plan(self, session: dict[str, object], attempts: list[dict[str, object]]) -> dict[str, object]:
        seen: dict[str, str] = {}
        overlap: list[str] = []
        for response in attempts:
            changed = response.get("provenance", {}).get("changed_files", []) if isinstance(response.get("provenance"), dict) else []
            for path in changed:
                text = str(path)
                if text in seen:
                    overlap.append(text)
                seen[text] = str(response.get("attempt_id"))
        plan = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": f"integration_{new_ulid()}",
            "session_id": session["id"],
            "status": "blocked" if overlap else "ready",
            "attempt_ids": [item.get("attempt_id") for item in attempts],
            "changed_files": sorted(seen),
            "overlap_files": sorted(set(overlap)),
            "blocking_reasons": [f"overlapping files: {', '.join(sorted(set(overlap)))}"] if overlap else [],
            "recommended_next_action": "review integration plan before ait apply",
            "auto_apply": False,
        }
        ref = self._relative(self._session_dir(str(session["id"])) / "summaries" / f"{plan['id']}.json")
        self._write_text_ref(ref, json.dumps(plan, indent=2, sort_keys=True) + "\n")
        plan["artifact_ref"] = ref
        return plan

    def _promote_decision_memory(self, session: dict[str, object], turn: dict[str, object], *, source_id: str) -> str:
        body = f"Accepted session decision from {source_id} in {session['id']}."
        source_trace_ref = str(turn.get("user_input_redacted_ref") or "")
        if str(source_id).startswith("rsp_"):
            try:
                source = self._load_response(str(session["id"]), source_id)
                source_trace_ref = str(source.get("redacted_response_ref") or source_trace_ref)
                source_body = _read_ref_text(self.repo_root, str(source.get("redacted_response_ref") or "")).strip()
                if source_body:
                    body = source_body[:1200]
            except SessionError:
                pass
        now = utc_now()
        init_result = init_repo(self.repo_root)
        fact_id = f"mem:{new_ulid()}"
        conn = connect_db(init_result.db_path)
        try:
            upsert_memory_fact(
                conn,
                NewMemoryFact(
                    id=fact_id,
                    kind="decision",
                    topic=f"session:{session['id']}",
                    body=body,
                    summary=f"Accepted session decision {source_id}",
                    status="accepted",
                    confidence="manual",
                    source_trace_ref=source_trace_ref,
                    valid_from=now,
                    created_at=now,
                    updated_at=now,
                    human_review_state="approved",
                    provenance="manual",
                ),
            )
        finally:
            conn.close()
        return fact_id

    def _current_turn(self, session: dict[str, object]) -> dict[str, object]:
        turn = self._current_turn_or_none(session)
        if turn is None:
            raise SessionError("session has no turn; run `ait session ask latest \"...\"` first")
        return turn

    def _current_turn_or_none(self, session: dict[str, object]) -> dict[str, object] | None:
        turn_id = session.get("current_turn_id")
        if not turn_id:
            return None
        return json.loads((self.repo_root / self._turn_ref(str(session["id"]), str(turn_id))).read_text(encoding="utf-8"))

    def _turns(self, session_id: str) -> list[dict[str, object]]:
        turns = []
        for path in sorted((self._session_dir(session_id) / "turns").glob("*-turn.json")):
            turns.append(json.loads(path.read_text(encoding="utf-8")))
        return turns

    def _load_response(self, session_id: str, response_id: str) -> dict[str, object]:
        path = self.repo_root / self._response_ref(session_id, response_id)
        if not path.exists():
            raise SessionError(f"response not found: {response_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_summary(self, session_id: str, summary_id: str) -> dict[str, object]:
        path = self._session_dir(session_id) / "summaries" / f"{summary_id}.json"
        if not path.exists():
            raise SessionError(f"summary not found: {summary_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_allocation(self, session_id: str, plan_id: str) -> dict[str, object]:
        path = self.repo_root / self._allocation_ref(session_id, plan_id)
        if not path.exists():
            raise SessionError(f"allocation plan not found: {plan_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_session(self, session: dict[str, object]) -> None:
        self._write_json_ref(self._relative(self._session_dir(str(session["id"])) / "session.json"), session)

    def _append_event(self, session_id: str, event: dict[str, object]) -> None:
        event = {"schema_version": SESSION_SCHEMA_VERSION, **event}
        path = self._session_dir(session_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _append_index(self, session: dict[str, object]) -> None:
        path = self.sessions_dir / "index.jsonl"
        row = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": session["id"],
            "title": session["title"],
            "created_at": session["created_at"],
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / _safe_name(session_id)

    def _turn_ref(self, session_id: str, turn_id: str) -> str:
        return self._relative(self._session_dir(session_id) / "turns" / f"{turn_id}-turn.json")

    def _response_ref(self, session_id: str, response_id: str) -> str:
        return self._relative(self._session_dir(session_id) / "responses" / f"{response_id}.json")

    def _allocation_ref(self, session_id: str, plan_id: str) -> str:
        return self._relative(self._session_dir(session_id) / "allocations" / f"{plan_id}.json")

    def _write_json_ref(self, ref: str, payload: dict[str, object]) -> None:
        self._write_text_ref(ref, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _write_text_ref(self, ref: str, text: str) -> None:
        path = self.repo_root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def _relative(self, path: Path) -> str:
        return path.resolve(strict=False).relative_to(self.repo_root).as_posix()


def start_session(
    repo_root: str | Path,
    title: str,
    *,
    agents: tuple[str, ...],
    agent_commands: dict[str, str] | None = None,
    permission_policy: dict[str, str] | None = None,
) -> SessionCommandResult:
    store = SessionStore(repo_root)
    session = store.start(title, agents=agents, agent_commands=agent_commands, permission_policy=permission_policy)
    payload = store.state_payload(session)
    return SessionCommandResult(payload=payload, text=f"Started AIT session {session['id']}\n")


def ask_session(repo_root: str | Path, selector: str, message: str) -> SessionCommandResult:
    store = SessionStore(repo_root)
    session, turn = store.add_turn(selector, message)
    payload = store.state_payload(session)
    return SessionCommandResult(payload=payload, text=f"Added turn {turn['id']} to {session['id']}\n")


def _repo_id(repo_root: Path) -> str:
    ensure_local_config(repo_root)
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "unborn:" + hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:24]


def _participant_payload(
    *,
    session_id: str,
    agent: str,
    role: str,
    ordinal: int,
    now: str,
    state: str = "active",
    command_template: str | None = None,
) -> dict[str, object]:
    safe = _slug(agent)
    return {
        "id": f"part_{ordinal:03d}_{safe}",
        "session_id": session_id,
        "agent_id": agent,
        "adapter_name": _adapter_for_agent(agent),
        "role": role,
        "display_name": agent,
        "command_template": command_template,
        "capabilities": {
            "can_respond": True,
            "can_create_attempt": role == "implementer",
            "can_review_attempt": role == "reviewer",
            "can_read_prior_responses": False,
            "can_receive_advisory_context": True,
            "can_stream": True,
            "can_use_interactive_tty": True,
        },
        "permissions": {
            "can_respond": True,
            "can_create_attempt": role == "implementer",
            "can_review_attempt": role == "reviewer",
        },
        "state": state,
        "added_at": now,
        "removed_at": None,
        "removed_by_actor": None,
        "remove_reason": None,
    }


def _adapter_for_agent(agent: str) -> str:
    if agent.startswith("fake:"):
        return "fake"
    return agent.split(":", 1)[0] or "shell"


def session_permission_policy(
    *,
    claude_permission_mode: str | None = None,
    codex_sandbox: str | None = None,
    codex_approval: str | None = None,
) -> dict[str, str]:
    return _normalize_session_permission_policy(
        {
            key: value
            for key, value in {
                "claude_code_permission_mode": claude_permission_mode,
                "codex_sandbox": codex_sandbox,
                "codex_approval": codex_approval,
            }.items()
            if value is not None
        }
    )


def _session_permission_policy(session: dict[str, object]) -> dict[str, str]:
    direct = session.get("permission_policy")
    if isinstance(direct, dict):
        return _normalize_session_permission_policy({str(k): str(v) for k, v in direct.items()})
    metadata = session.get("metadata_json")
    if isinstance(metadata, dict) and isinstance(metadata.get("permission_policy"), dict):
        policy = metadata["permission_policy"]
        return _normalize_session_permission_policy({str(k): str(v) for k, v in policy.items()})
    return dict(DEFAULT_SESSION_PERMISSION_POLICY)


def _normalize_session_permission_policy(policy: dict[str, str] | None) -> dict[str, str]:
    resolved = dict(DEFAULT_SESSION_PERMISSION_POLICY)
    if policy:
        resolved.update({key: value for key, value in policy.items() if value})
    if resolved["claude_code_permission_mode"] not in {"plan", "default", "acceptEdits", "auto", "dontAsk", "bypassPermissions"}:
        raise SessionError(f"unsupported Claude Code permission mode: {resolved['claude_code_permission_mode']}")
    if resolved["codex_sandbox"] not in {"read-only", "workspace-write", "danger-full-access"}:
        raise SessionError(f"unsupported Codex sandbox mode: {resolved['codex_sandbox']}")
    if resolved["codex_approval"] not in {"untrusted", "on-request", "never"}:
        raise SessionError(f"unsupported Codex approval policy: {resolved['codex_approval']}")
    return resolved


def _real_panel_command(adapter_name: str, repo_root: Path, permission_policy: dict[str, str]) -> tuple[str, ...] | None:
    try:
        adapter = get_adapter(adapter_name)
    except AdapterError:
        return None
    template = _REAL_PANEL_COMMANDS.get(adapter.name)
    if template is None:
        if not adapter.command_name:
            return None
        template = (adapter.command_name,)
    command_name = template[0]
    binary = _resolve_real_panel_binary(command_name, repo_root)
    suffix = _permission_command_suffix(adapter.name, permission_policy)
    if binary is None:
        return (command_name, *template[1:], *suffix)
    return (binary, *template[1:], *suffix)


def _permission_command_suffix(adapter_name: str, permission_policy: dict[str, str]) -> tuple[str, ...]:
    if adapter_name == "claude-code":
        return ("--permission-mode", permission_policy["claude_code_permission_mode"])
    if adapter_name == "codex":
        return (
            "--sandbox",
            permission_policy["codex_sandbox"],
            "-",
        )
    return ()


def _resolve_real_panel_binary(command_name: str, repo_root: Path) -> str | None:
    wrapper_path = repo_root / ".ait" / "bin" / command_name
    if wrapper_path.exists():
        try:
            return _find_real_binary(command_name, wrapper_path)
        except AdapterError:
            pass
    return shutil.which(command_name)


def _invoke_agent(agent: str, *, timeout_seconds: int) -> tuple[str, str, int | None, str]:
    if agent.startswith("fake:fail"):
        return f"{agent} failed\n", "fake failure\n", 1, "failed"
    if agent.startswith("fake:cancel"):
        return f"{agent} partial output before cancellation\n", "cancelled\n", None, "cancelled"
    if agent.startswith("fake:sleep"):
        seconds = _fake_sleep_seconds(agent)
        if seconds > timeout_seconds:
            return f"{agent} started\n", "timed out\n", None, "timed_out"
        return f"{agent} completed after {seconds}s\n", "", 0, "completed"
    if agent.startswith("fake:secret"):
        return "TOKEN=super-secret-token-value\n", "", 0, "completed"
    if agent.startswith("fake:"):
        return f"fake response from {agent}\n", "", 0, "completed"
    return "", f"unsupported fake agent path: {agent}\n", 127, "failed"


def _fake_sleep_seconds(agent: str) -> int:
    parts = agent.split(":")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return DEFAULT_SESSION_TIMEOUT_SECONDS + 1


def _parse_agents(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def parse_agent_options(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    agents: list[str] = []
    for value in values:
        agents.extend(_parse_agents(value))
    return tuple(agents)


def parse_agent_command_options(values: list[str] | None) -> dict[str, str]:
    commands: dict[str, str] = {}
    for value in values or ():
        if "=" not in value:
            raise SessionError("--agent-command must use agent=command")
        agent, command = value.split("=", 1)
        agent = agent.strip()
        command = command.strip()
        if not agent or not command:
            raise SessionError("--agent-command must include both agent and command")
        commands[agent] = command
    return commands


def _parse_packages(values: tuple[str, ...] | list[str] | None) -> dict[str, tuple[str, ...]]:
    packages: dict[str, tuple[str, ...]] = {}
    for value in values or ():
        if "=" not in value:
            packages[_slug(value)] = (value,)
            continue
        name, raw_paths = value.split("=", 1)
        paths = tuple(item.strip() for item in raw_paths.split(",") if item.strip())
        packages[name.strip() or _slug(raw_paths)] = paths or ("**/*",)
    return packages


def _path_for_scope(scope: str) -> str:
    path = scope.strip() or "session-output.txt"
    if any(char in path for char in "*?[]"):
        base = path.split("*", 1)[0].rstrip("/")
        if not base or base.endswith("."):
            return "session-output.txt"
        return f"{base}/session-output.txt"
    if path.endswith("/"):
        return f"{path}session-output.txt"
    return path


def _participant_for_agent(session: dict[str, object], agent: str) -> str | None:
    for item in session.get("participants", []):
        if isinstance(item, dict) and item.get("agent_id") == agent and item.get("state") == "active":
            return str(item.get("id"))
    return None


def _response_summary(response: dict[str, object]) -> dict[str, object]:
    return {
        "response_id": response.get("id"),
        "participant_id": response.get("participant_id"),
        "agent_id": response.get("agent_id"),
        "role": response.get("role"),
        "state": response.get("state"),
        "trust_class": response.get("trust_class"),
        "attempt_id": response.get("attempt_id"),
        "review_id": response.get("review_id"),
        "context_manifest_ref": response.get("context_manifest_ref"),
        "command_ref": response.get("command_ref"),
        "provenance_refs": {
            "stdout_ref": response.get("stdout_ref"),
            "stderr_ref": response.get("stderr_ref"),
            "raw_trace_ref": response.get("raw_trace_ref"),
            "redacted_response_ref": response.get("redacted_response_ref"),
        },
    }


def _safe_actions(session: dict[str, object], *, has_attempt: bool) -> list[str]:
    actions = [
        f"ait session ask {session['id']} \"...\"",
        f"ait session export {session['id']} --format md",
    ]
    if has_attempt:
        actions.append("ait review report --attempt <attempt-id> --format json")
    return actions


def _next_action(command: str) -> dict[str, object]:
    return {"recommended_command": command, "reason": "session state is ready for the next explicit user decision"}


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return text[:40] or "agent"


def _read_ref_text(repo_root: Path, ref: str) -> str:
    if not ref:
        return ""
    path = repo_root / ref
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
