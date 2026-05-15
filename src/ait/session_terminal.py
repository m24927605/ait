from __future__ import annotations

from dataclasses import dataclass, field
import errno
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import time
from typing import Iterable

from ait.app import create_attempt, create_intent
from ait.db import connect_db, get_attempt, utc_now
from ait.events import process_event
from ait.ids import new_ulid
from ait.redaction import redact_text
from ait.runner_transcript import _strip_terminal_control
from ait.session_events import SessionEventStore, terminal_replay_text
from ait.session_room import SessionError, SessionStore
from ait.workspace_lease import update_workspace_lease


TERMINAL_DAEMON_STATUS = {
    "state": "pending",
    "ownership_model": "foreground",
    "detach_resume_supported": False,
    "reason": "daemon-owned session PTY ownership is scaffolded but not enabled",
}


@dataclass(slots=True)
class TerminalPane:
    pty_id: str
    response_id: str
    participant_id: str
    agent_id: str
    role: str
    turn_id: str
    process: subprocess.Popen[bytes]
    master_fd: int
    command: str
    cwd: Path
    context_ref: str
    context_manifest_ref: str
    command_ref: str
    attempt_id: str | None
    workspace_ref: str | None
    state: str = "running"
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    last_output_at: str | None = None
    exit_code: int | None = None
    cancellation_reason: str | None = None
    raw_trace_ref: str | None = None
    redacted_response_ref: str | None = None
    raw_output: bytearray = field(default_factory=bytearray)
    finalized: bool = False


def build_attach_plan(
    store: SessionStore,
    selector: str,
    *,
    agent: str | None = None,
) -> dict[str, object]:
    session = store.load(selector)
    participants = _active_participants(session, agent=agent)
    blocking_reasons: list[str] = []
    turn = store._current_turn_or_none(session)
    if turn is None:
        blocking_reasons.append("session has no turn; run `ait session ask latest \"...\"` first")
    plan_participants = []
    for participant in participants:
        context_ref = None
        context_manifest_ref = None
        if turn is not None:
            context_ref, context_manifest_ref = store._write_context(session, turn, participant)
        plan_participants.append(
            {
                "participant_id": participant.get("id"),
                "agent_id": participant.get("agent_id"),
                "role": participant.get("role"),
                "state": "ready" if turn is not None else "blocked",
                "command": _command_display(participant),
                "cwd_policy": _cwd_policy(participant),
                "context_ref": context_ref,
                "context_manifest_ref": context_manifest_ref,
                "will_start_pty": False,
            }
        )
    if not participants:
        blocking_reasons.append("session has no active participants")
    return {
        "schema_version": 1,
        "kind": "session_attach_plan",
        "session_id": session["id"],
        "turn_id": None if turn is None else turn.get("id"),
        "participants": plan_participants,
        "daemon_ownership": TERMINAL_DAEMON_STATUS,
        "safe_actions": [f"ait session attach {session['id']}"],
        "unsafe_actions": [
            {
                "command": "ait apply latest",
                "reason": "attach does not select or apply attempts",
            }
        ],
        "blocking_reasons": blocking_reasons,
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def run_foreground_attach(
    store: SessionStore,
    selector: str,
    *,
    agent: str | None = None,
    layout: str = "stacked",
    input_lines: Iterable[str] = (),
    terminate_on_detach: bool = False,
    render: bool = True,
) -> dict[str, object]:
    del layout
    session = store.load(selector)
    turn = store._current_turn(session)
    participants = _active_participants(session, agent=agent)
    if not participants:
        raise SessionError("session has no active participants")

    event_store = SessionEventStore(store.repo_root, store._session_dir(str(session["id"])), str(session["id"]))
    event_store.append(
        "attach_started",
        turn_id=turn["id"],
        actor={"type": "user", "id": "cli"},
        owner_pid=os.getpid(),
        foreground=True,
    )
    panes = [_start_pane(store, event_store, session, turn, participant) for participant in participants]
    _write_all_pane_records(store, event_store, session, panes)
    _drain_outputs(store, event_store, session, panes, quiet_seconds=0.15, render=render)

    scripted = list(input_lines)
    blocking_reasons: list[str] = []
    detach_requested = False
    detach_refused = False
    if scripted:
        for raw_line in scripted:
            outcome = _handle_input_line(
                store,
                event_store,
                session,
                panes,
                raw_line.rstrip("\n"),
                terminate_on_detach=terminate_on_detach,
                render=render,
            )
            blocking_reasons.extend(outcome.get("blocking_reasons", []))
            if outcome.get("detach_requested"):
                detach_requested = True
            if outcome.get("detach_refused"):
                detach_refused = True
            _drain_outputs(store, event_store, session, panes, quiet_seconds=0.15, render=render)
            if detach_requested and not detach_refused:
                break
    elif _stdin_is_interactive():
        detach_requested, detach_refused = _interactive_loop(
            store,
            event_store,
            session,
            panes,
            terminate_on_detach=terminate_on_detach,
            render=render,
            blocking_reasons=blocking_reasons,
        )
    else:
        blocking_reasons.append("stdin is not interactive; foreground PTYs were started and then safely cancelled")

    running = [pane for pane in panes if pane.state == "running" and pane.process.poll() is None]
    if running and detach_requested and not terminate_on_detach:
        detach_refused = True
        reason = "foreground detach refused while PTYs are running; rerun with --terminate-on-detach"
        blocking_reasons.append(reason)
        event_store.append(
            "attach_detached",
            turn_id=turn["id"],
            actor={"type": "user", "id": "cli"},
            state="refused",
            blocking_reasons=[reason],
        )
    elif detach_requested:
        event_store.append(
            "attach_detached",
            turn_id=turn["id"],
            actor={"type": "user", "id": "cli"},
            state="terminated" if terminate_on_detach else "detached",
        )

    cleanup_reason = None
    if running and (terminate_on_detach or not _stdin_is_interactive() or detach_refused):
        cleanup_reason = "terminate-on-detach" if terminate_on_detach else "foreground attach cleanup"
        for pane in running:
            _cancel_pane(store, event_store, session, pane, reason=cleanup_reason)

    _drain_outputs(store, event_store, session, panes, quiet_seconds=0.1, render=render)
    deadline = time.monotonic() + 2.0
    while any(pane.process.poll() is None for pane in panes) and time.monotonic() < deadline:
        _drain_outputs(store, event_store, session, panes, quiet_seconds=0.05, render=render)
    for pane in panes:
        if pane.process.poll() is None:
            _cancel_pane(store, event_store, session, pane, reason="forced foreground cleanup")
            try:
                pane.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    pane.process.kill()
                except OSError:
                    pass
                try:
                    pane.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        _finalize_pane(store, event_store, session, pane)
    _write_all_pane_records(store, event_store, session, panes)
    return {
        "schema_version": 1,
        "kind": "session_attach",
        "session_id": session["id"],
        "turn_id": turn["id"],
        "state": "completed",
        "detach": {
            "requested": detach_requested,
            "refused": detach_refused,
            "terminate_on_detach": terminate_on_detach,
            "cleanup_reason": cleanup_reason,
        },
        "panes": [_pane_payload(store, event_store, session, pane) for pane in panes],
        "daemon_ownership": TERMINAL_DAEMON_STATUS,
        "blocking_reasons": blocking_reasons,
        "unsafe_actions": [
            {
                "command": "ait apply latest",
                "reason": "terminal orchestration never applies changes directly",
            }
        ],
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def list_panes(store: SessionStore, selector: str) -> dict[str, object]:
    session = store.load(selector)
    event_store = SessionEventStore(store.repo_root, store._session_dir(str(session["id"])), str(session["id"]))
    panes = []
    for path in sorted((store._session_dir(str(session["id"])) / "ptys").glob("*.json")):
        try:
            pane = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(pane, dict):
            continue
        pane = _mark_stale_pane_if_needed(store, event_store, session, pane)
        panes.append(pane)
    return {
        "schema_version": 1,
        "kind": "session_panes",
        "session_id": session["id"],
        "panes": panes,
        "daemon_ownership": TERMINAL_DAEMON_STATUS,
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def send_to_panes(
    store: SessionStore,
    selector: str,
    *,
    to_agent: str | None = None,
    all_agents: bool = False,
    message: str,
) -> dict[str, object]:
    session = store.load(selector)
    pane_payload = list_panes(store, selector)
    panes = [item for item in pane_payload.get("panes", []) if isinstance(item, dict)]
    targets = panes if all_agents else [pane for pane in panes if _pane_matches(pane, to_agent or "")]
    blocking_reasons: list[str] = []
    if not targets:
        blocking_reasons.append("no matching PTY pane")
    running_targets = [pane for pane in targets if pane.get("state") in {"running", "detached"}]
    if running_targets:
        blocking_reasons.append("send requires daemon-owned PTYs; foreground-owned PTYs cannot be resumed safely yet")
    else:
        blocking_reasons.append("no running resumable PTY")
    return {
        "schema_version": 1,
        "kind": "session_send",
        "session_id": session["id"],
        "delivered": False,
        "message": message,
        "targets": [
            {
                "pty_id": pane.get("pty_id"),
                "participant_id": pane.get("participant_id"),
                "agent_id": pane.get("agent_id"),
                "state": pane.get("state"),
            }
            for pane in targets
        ],
        "daemon_ownership": TERMINAL_DAEMON_STATUS,
        "blocking_reasons": blocking_reasons,
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def kill_pane(store: SessionStore, selector: str, *, agent: str) -> dict[str, object]:
    session = store.load(selector)
    event_store = SessionEventStore(store.repo_root, store._session_dir(str(session["id"])), str(session["id"]))
    payload = list_panes(store, selector)
    panes = [item for item in payload.get("panes", []) if isinstance(item, dict) and _pane_matches(item, agent)]
    blocking_reasons: list[str] = []
    killed = []
    if not panes:
        blocking_reasons.append("no matching PTY pane")
    for pane in panes:
        if pane.get("state") not in {"running", "detached"}:
            blocking_reasons.append(f"PTY {pane.get('pty_id')} is not running")
            continue
        pid = pane.get("pid")
        if not isinstance(pid, int) or not _pid_alive(pid):
            pane["state"] = "crashed"
            pane["ended_at"] = utc_now()
            _write_pane_payload(store, str(session["id"]), pane)
            _update_response_state_from_pane_payload(store, str(session["id"]), pane)
            event_store.append(
                "pty_exited",
                turn_id=pane.get("turn_id"),
                pty_id=pane.get("pty_id"),
                participant_id=pane.get("participant_id"),
                agent_id=pane.get("agent_id"),
                response_id=pane.get("response_id"),
                exit_code=None,
                state="crashed",
                actor={"type": "ait", "id": "session-kill"},
            )
            blocking_reasons.append(f"PTY {pane.get('pty_id')} is stale")
            continue
        ownership = pane.get("ownership") if isinstance(pane.get("ownership"), dict) else {}
        if ownership.get("model") != "daemon":
            blocking_reasons.append(
                f"PTY {pane.get('pty_id')} is foreground-owned; kill requires daemon-owned PTY recovery metadata"
            )
            continue
        try:
            os.kill(pid, 15)
        except OSError as exc:
            blocking_reasons.append(str(exc))
            continue
        pane["state"] = "cancelled"
        pane["ended_at"] = utc_now()
        pane["cancellation_reason"] = "killed by user"
        _write_pane_payload(store, str(session["id"]), pane)
        _update_response_state_from_pane_payload(store, str(session["id"]), pane)
        event_store.append(
            "pty_cancelled",
            turn_id=pane.get("turn_id"),
            pty_id=pane.get("pty_id"),
            participant_id=pane.get("participant_id"),
            agent_id=pane.get("agent_id"),
            response_id=pane.get("response_id"),
            actor={"type": "user", "id": "cli"},
            cancellation_reason="killed by user",
        )
        killed.append(pane)
    return {
        "schema_version": 1,
        "kind": "session_kill",
        "session_id": session["id"],
        "killed": [
            {
                "pty_id": pane.get("pty_id"),
                "participant_id": pane.get("participant_id"),
                "agent_id": pane.get("agent_id"),
                "response_id": pane.get("response_id"),
            }
            for pane in killed
        ],
        "daemon_ownership": TERMINAL_DAEMON_STATUS,
        "blocking_reasons": blocking_reasons,
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def replay_session(store: SessionStore, selector: str, *, turn: str = "latest") -> dict[str, object]:
    session = store.load(selector)
    turn_id = None
    if turn == "latest":
        turn_id = str(session.get("current_turn_id") or "")
    elif turn and turn != "all":
        turn_id = turn
    if not turn_id:
        turn_id = None
    event_store = SessionEventStore(store.repo_root, store._session_dir(str(session["id"])), str(session["id"]))
    events = event_store.replay_events(turn_id=turn_id)
    return {
        "schema_version": 1,
        "kind": "session_replay",
        "session_id": session["id"],
        "turn_id": turn_id,
        "events": events,
        "text": terminal_replay_text(events),
        "deterministic_ordering": ["seq"],
        "redaction": "terminal payloads are sanitized and redacted during replay",
        "provenance_refs": [_events_ref(store, str(session["id"]))],
    }


def _start_pane(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    turn: dict[str, object],
    participant: dict[str, object],
) -> TerminalPane:
    response_id = f"rsp_{new_ulid()}"
    pty_id = f"pty_{new_ulid()}"
    context_ref, context_manifest_ref = store._write_context(session, turn, participant)
    command_ref = store._relative(store._session_dir(str(session["id"])) / "transcripts" / f"{response_id}.terminal.command.txt")
    command_display = _command_display(participant)
    store._write_text_ref(command_ref, command_display + "\n")
    cwd, attempt_id, workspace_ref = _prepare_cwd(store, session, participant, response_id)
    env = _terminal_env(
        store,
        session=session,
        turn=turn,
        participant=participant,
        response_id=response_id,
        context_ref=context_ref,
        workspace_ref=workspace_ref,
    )
    master_fd, slave_fd = pty.openpty()
    command, shell = _popen_command(participant)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            shell=shell,
        )
    finally:
        os.close(slave_fd)
    pane = TerminalPane(
        pty_id=pty_id,
        response_id=response_id,
        participant_id=str(participant["id"]),
        agent_id=str(participant["agent_id"]),
        role=str(participant.get("role") or "panelist"),
        turn_id=str(turn["id"]),
        process=process,
        master_fd=master_fd,
        command=command_display,
        cwd=cwd,
        context_ref=context_ref,
        context_manifest_ref=context_manifest_ref,
        command_ref=command_ref,
        attempt_id=attempt_id,
        workspace_ref=workspace_ref,
    )
    _write_response_record(store, session, pane)
    event_store.append(
        "pty_started",
        turn_id=turn["id"],
        pty_id=pty_id,
        participant_id=pane.participant_id,
        agent_id=pane.agent_id,
        response_id=response_id,
        pid=process.pid,
        state="running",
        context_manifest_ref=context_manifest_ref,
        command_ref=command_ref,
        actor={"type": "ait", "id": "session-attach"},
    )
    size = shutil.get_terminal_size(fallback=(80, 24))
    event_store.append(
        "pty_resize",
        turn_id=turn["id"],
        pty_id=pty_id,
        participant_id=pane.participant_id,
        agent_id=pane.agent_id,
        response_id=response_id,
        cols=size.columns,
        rows=size.lines,
        actor={"type": "ait", "id": "session-attach"},
    )
    return pane


def _prepare_cwd(
    store: SessionStore,
    session: dict[str, object],
    participant: dict[str, object],
    response_id: str,
) -> tuple[Path, str | None, str | None]:
    role = str(participant.get("role") or "panelist")
    if role == "implementer":
        intent = create_intent(
            store.repo_root,
            title=f"{session.get('title')}: terminal {participant.get('agent_id')}",
            description=f"AIT session {session['id']} terminal implementer workspace",
            kind="session-terminal-implementer",
        )
        attempt = create_attempt(
            store.repo_root,
            intent_id=intent.intent_id,
            agent_id=_attempt_agent_id(str(participant.get("agent_id") or "")),
        )
        update_workspace_lease(
            attempt.workspace_ref,
            owner_pid=os.getpid(),
            owner_command="ait session attach",
            state="active",
            clear_preserve_reason=True,
        )
        return Path(attempt.workspace_ref), attempt.attempt_id, attempt.workspace_ref
    root = store._session_dir(str(session["id"])) / ("reviewer-runs" if role == "reviewer" else "terminal-runs") / response_id
    root.mkdir(parents=True, exist_ok=True)
    return root, None, None


def _terminal_env(
    store: SessionStore,
    *,
    session: dict[str, object],
    turn: dict[str, object],
    participant: dict[str, object],
    response_id: str,
    context_ref: str,
    workspace_ref: str | None,
) -> dict[str, str]:
    env = {
        **os.environ,
        "AIT_SESSION_ID": str(session["id"]),
        "AIT_TURN_ID": str(turn["id"]),
        "AIT_PARTICIPANT_ID": str(participant["id"]),
        "AIT_RESPONSE_ID": response_id,
        "AIT_CONTEXT_FILE": str((store.repo_root / context_ref).resolve()),
        "AIT_CONTEXT_HINT": "session terminal context is redacted and attributed",
        "AIT_REPO_ROOT": str(store.repo_root),
    }
    if workspace_ref is not None:
        env["AIT_WORKSPACE_REF"] = workspace_ref
    return env


def _popen_command(participant: dict[str, object]) -> tuple[str | list[str], bool]:
    command_template = participant.get("command_template")
    if isinstance(command_template, str) and command_template.strip():
        return command_template, True
    agent = str(participant.get("agent_id") or "fake:agent")
    if agent.startswith("fake:"):
        return [sys.executable, "-u", "-c", _fake_pty_agent_code(agent)], False
    return _default_local_command(agent), True


def _fake_pty_agent_code(agent: str) -> str:
    seconds = _fake_sleep_seconds(agent)
    lines = [
        "import os, sys, time",
        f"agent = {agent!r}",
        "print(f'{agent} ready pid={os.getpid()}', flush=True)",
    ]
    if "secret" in agent:
        lines.append("print('TOKEN=super-secret-token-value', flush=True)")
    if "ansi" in agent:
        lines.append("print('\\x1b[31mred\\x1b[0m clean', flush=True)")
    if seconds is not None:
        lines.extend(
            [
                f"time.sleep({seconds})",
                "print(f'{agent} completed sleep', flush=True)",
            ]
        )
    lines.extend(
        [
            "for raw in sys.stdin:",
            "    text = raw.rstrip('\\n')",
            "    print(f'{agent} received {text}', flush=True)",
        ]
    )
    return "\n".join(lines)


def _fake_sleep_seconds(agent: str) -> float | None:
    parts = agent.split(":")
    if "sleep" not in parts:
        return None
    for part in reversed(parts):
        try:
            return min(float(part), 30.0)
        except ValueError:
            continue
    return 30.0


def _default_local_command(agent: str) -> str:
    safe_agent = agent.replace("'", "'\"'\"'")
    return f"printf '%s\\n' '{safe_agent} has no terminal command configured; exiting.'"


def _command_display(participant: dict[str, object]) -> str:
    command_template = participant.get("command_template")
    if isinstance(command_template, str) and command_template.strip():
        return command_template.strip()
    agent = str(participant.get("agent_id") or "")
    if agent.startswith("fake:"):
        return f"ait fake pty {agent}"
    return _default_local_command(agent)


def _cwd_policy(participant: dict[str, object]) -> str:
    role = str(participant.get("role") or "panelist")
    if role == "implementer":
        return "isolated_attempt_workspace"
    if role == "reviewer":
        return "session_local_reviewer_workspace"
    return "session_local_advisory_workspace"


def _interactive_loop(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    panes: list[TerminalPane],
    *,
    terminate_on_detach: bool,
    render: bool,
    blocking_reasons: list[str],
) -> tuple[bool, bool]:
    detach_requested = False
    detach_refused = False
    while any(pane.process.poll() is None for pane in panes):
        _drain_outputs(store, event_store, session, panes, quiet_seconds=0.05, render=render)
        sys.stdout.write("input> ")
        sys.stdout.flush()
        readable, _, _ = select.select([sys.stdin], [], [], 0.1)
        if not readable:
            continue
        line = sys.stdin.readline()
        if line == "":
            blocking_reasons.append("stdin closed; foreground PTYs were safely cancelled")
            break
        outcome = _handle_input_line(
            store,
            event_store,
            session,
            panes,
            line.rstrip("\n"),
            terminate_on_detach=terminate_on_detach,
            render=render,
        )
        blocking_reasons.extend(outcome.get("blocking_reasons", []))
        detach_requested = bool(outcome.get("detach_requested"))
        detach_refused = bool(outcome.get("detach_refused"))
        if detach_requested:
            break
    return detach_requested, detach_refused


def _handle_input_line(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    panes: list[TerminalPane],
    line: str,
    *,
    terminate_on_detach: bool,
    render: bool,
) -> dict[str, object]:
    del render
    if not line.strip():
        return {"blocking_reasons": []}
    if line.startswith("/to "):
        _, target, message = line.split(" ", 2) if line.count(" ") >= 2 else ("/to", "", "")
        if not target or not message:
            return {"blocking_reasons": ["/to requires <agent-or-participant-id> and message"]}
        pane = _find_running_pane(panes, target)
        if pane is None:
            return {"blocking_reasons": [f"no running participant matches {target}"]}
        _route_input(store, event_store, session, pane, message, route="to")
        event_store.append(
            "route_changed",
            turn_id=pane.turn_id,
            pty_id=pane.pty_id,
            participant_id=pane.participant_id,
            agent_id=pane.agent_id,
            response_id=pane.response_id,
            route="to",
            actor={"type": "user", "id": "cli"},
        )
        return {"blocking_reasons": []}
    if line.startswith("/all "):
        message = line[len("/all ") :]
        targets = [pane for pane in panes if pane.state == "running" and pane.process.poll() is None]
        for pane in targets:
            _route_input(store, event_store, session, pane, message, route="all")
        event_store.append(
            "route_changed",
            turn_id=str(session.get("current_turn_id") or ""),
            route="all",
            participant_count=len(targets),
            actor={"type": "user", "id": "cli"},
        )
        return {"blocking_reasons": []}
    if line.startswith("/kill "):
        target = line[len("/kill ") :].strip()
        pane = _find_running_pane(panes, target)
        if pane is None:
            return {"blocking_reasons": [f"no running participant matches {target}"]}
        _cancel_pane(store, event_store, session, pane, reason="killed by user")
        return {"blocking_reasons": []}
    if line == "/detach":
        running = [pane for pane in panes if pane.state == "running" and pane.process.poll() is None]
        if running and not terminate_on_detach:
            return {
                "detach_requested": True,
                "detach_refused": True,
                "blocking_reasons": ["foreground detach refused while PTYs are running; use --terminate-on-detach"],
            }
        return {"detach_requested": True, "blocking_reasons": []}
    return {"blocking_reasons": ["terminal input must use /to, /all, /kill, or /detach"]}


def _route_input(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: TerminalPane,
    message: str,
    *,
    route: str,
) -> None:
    payload = (message + "\n").encode("utf-8")
    os.write(pane.master_fd, payload)
    event_store.append_payload_event(
        "pty_input",
        payload,
        turn_id=pane.turn_id,
        pty_id=pane.pty_id,
        participant_id=pane.participant_id,
        agent_id=pane.agent_id,
        response_id=pane.response_id,
        route=route,
        actor={"type": "user", "id": "cli"},
    )
    _write_pane_record(store, event_store, session, pane)


def _cancel_pane(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: TerminalPane,
    *,
    reason: str,
) -> None:
    if pane.state != "cancelled":
        pane.state = "cancelled"
        pane.cancellation_reason = reason
        event_store.append(
            "pty_cancelled",
            turn_id=pane.turn_id,
            pty_id=pane.pty_id,
            participant_id=pane.participant_id,
            agent_id=pane.agent_id,
            response_id=pane.response_id,
            actor={"type": "user", "id": "cli"} if reason == "killed by user" else {"type": "ait", "id": "session-attach"},
            cancellation_reason=reason,
        )
    try:
        pane.process.terminate()
    except OSError:
        pass
    _write_pane_record(store, event_store, session, pane)


def _drain_outputs(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    panes: list[TerminalPane],
    *,
    quiet_seconds: float,
    render: bool,
) -> None:
    quiet_until = time.monotonic() + quiet_seconds
    while time.monotonic() < quiet_until:
        active = [pane for pane in panes if not pane.finalized]
        if not active:
            return
        fds = [pane.master_fd for pane in active if pane.master_fd >= 0]
        if not fds:
            break
        readable, _, _ = select.select(fds, [], [], 0.02)
        if not readable:
            for pane in active:
                if pane.process.poll() is not None:
                    _finalize_pane(store, event_store, session, pane)
            continue
        quiet_until = time.monotonic() + quiet_seconds
        for fd in readable:
            pane = next(item for item in active if item.master_fd == fd)
            try:
                data = os.read(fd, 4096)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                data = b""
            if data:
                pane.raw_output.extend(data)
                pane.last_output_at = utc_now()
                event_store.append_payload_event(
                    "pty_output",
                    data,
                    turn_id=pane.turn_id,
                    pty_id=pane.pty_id,
                    participant_id=pane.participant_id,
                    agent_id=pane.agent_id,
                    response_id=pane.response_id,
                )
                if render:
                    _render_output(pane, data)
                _write_pane_record(store, event_store, session, pane)
            elif pane.process.poll() is not None:
                _finalize_pane(store, event_store, session, pane)


def _render_output(pane: TerminalPane, data: bytes) -> None:
    text = data.decode("utf-8", errors="replace")
    if not text:
        return
    for line in text.splitlines():
        print(f"[{pane.agent_id}] {line}")


def _finalize_pane(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: TerminalPane,
) -> None:
    if pane.finalized:
        return
    returncode = pane.process.poll()
    if returncode is None:
        return
    pane.exit_code = returncode
    pane.ended_at = utc_now()
    if pane.state == "running":
        pane.state = "completed" if returncode == 0 else "failed"
    raw_ref, redacted_ref = _write_terminal_transcripts(store, session, pane)
    pane.raw_trace_ref = raw_ref
    pane.redacted_response_ref = redacted_ref
    event_store.append(
        "pty_exited",
        turn_id=pane.turn_id,
        pty_id=pane.pty_id,
        participant_id=pane.participant_id,
        agent_id=pane.agent_id,
        response_id=pane.response_id,
        exit_code=returncode,
        state=pane.state,
        raw_trace_ref=raw_ref,
        redacted_response_ref=redacted_ref,
        actor={"type": "ait", "id": "session-attach"},
    )
    _write_response_record(store, session, pane, raw_ref=raw_ref, redacted_ref=redacted_ref)
    _write_pane_record(store, event_store, session, pane, raw_ref=raw_ref, redacted_ref=redacted_ref)
    _finish_attempt_if_needed(store, pane, raw_ref=raw_ref)
    try:
        os.close(pane.master_fd)
    except OSError:
        pass
    pane.master_fd = -1
    pane.finalized = True


def _write_terminal_transcripts(
    store: SessionStore,
    session: dict[str, object],
    pane: TerminalPane,
) -> tuple[str, str]:
    raw_text = pane.raw_output.decode("utf-8", errors="replace")
    raw_ref = store._relative(store._session_dir(str(session["id"])) / "transcripts" / f"{pane.response_id}.terminal.raw")
    redacted_ref = store._relative(store._session_dir(str(session["id"])) / "transcripts" / f"{pane.response_id}.terminal.redacted.md")
    store._write_text_ref(raw_ref, raw_text)
    sanitized = _strip_terminal_control(raw_text)
    redacted, _ = redact_text(sanitized)
    store._write_text_ref(redacted_ref, redacted)
    return raw_ref, redacted_ref


def _write_response_record(
    store: SessionStore,
    session: dict[str, object],
    pane: TerminalPane,
    *,
    raw_ref: str | None = None,
    redacted_ref: str | None = None,
) -> None:
    response = {
        "schema_version": 1,
        "id": pane.response_id,
        "session_id": session["id"],
        "turn_id": pane.turn_id,
        "participant_id": pane.participant_id,
        "agent_id": pane.agent_id,
        "adapter_name": pane.agent_id.split(":", 1)[0],
        "role": pane.role,
        "state": pane.state,
        "invocation_id": f"inv_{pane.pty_id.removeprefix('pty_')}",
        "command_ref": pane.command_ref,
        "context_manifest_ref": pane.context_manifest_ref,
        "context_ref": pane.context_ref,
        "stdout_ref": raw_ref,
        "stderr_ref": None,
        "raw_trace_ref": raw_ref,
        "redacted_response_ref": redacted_ref,
        "exit_code": pane.exit_code,
        "started_at": pane.started_at,
        "ended_at": pane.ended_at,
        "timeout_seconds": None,
        "cancellation_reason": pane.cancellation_reason,
        "provenance": {
            "captured_by": "ait-session-terminal",
            "pty_id": pane.pty_id,
            "pid": pane.process.pid,
            "cwd_ref": _path_ref(store, pane.cwd),
            "workspace_ref": pane.workspace_ref,
            "ownership_model": "foreground",
            "no_auto_apply": True,
        },
        "trust_class": _trust_class_for_role(pane.role),
        "proposal_ids": [],
        "attempt_id": pane.attempt_id,
        "review_id": None,
        "metadata_json": {"terminal": True},
    }
    store._write_json_ref(store._response_ref(str(session["id"]), pane.response_id), response)
    turn = store._current_turn(session)
    response_ids = [str(item) for item in turn.get("response_ids", [])]
    if pane.response_id not in response_ids:
        turn["response_ids"] = [*response_ids, pane.response_id]
        store._write_json_ref(store._turn_ref(str(session["id"]), str(turn["id"])), turn)


def _trust_class_for_role(role: str) -> str:
    if role == "implementer":
        return "attempt_result"
    if role == "reviewer":
        return "review_evidence"
    return "advisory"


def _write_all_pane_records(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    panes: list[TerminalPane],
) -> None:
    for pane in panes:
        _write_pane_record(store, event_store, session, pane)


def _write_pane_record(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: TerminalPane,
    *,
    raw_ref: str | None = None,
    redacted_ref: str | None = None,
) -> None:
    _write_pane_payload(store, str(session["id"]), _pane_payload(store, event_store, session, pane, raw_ref=raw_ref, redacted_ref=redacted_ref))


def _pane_payload(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: TerminalPane,
    *,
    raw_ref: str | None = None,
    redacted_ref: str | None = None,
) -> dict[str, object]:
    resolved_raw_ref = raw_ref or pane.raw_trace_ref
    resolved_redacted_ref = redacted_ref or pane.redacted_response_ref
    return {
        "schema_version": 1,
        "pty_id": pane.pty_id,
        "session_id": session["id"],
        "turn_id": pane.turn_id,
        "participant_id": pane.participant_id,
        "agent_id": pane.agent_id,
        "response_id": pane.response_id,
        "pid": pane.process.pid,
        "state": pane.state,
        "role": pane.role,
        "started_at": pane.started_at,
        "ended_at": pane.ended_at,
        "last_output_at": pane.last_output_at,
        "exit_code": pane.exit_code,
        "cancellation_reason": pane.cancellation_reason,
        "context_ref": pane.context_ref,
        "context_manifest_ref": pane.context_manifest_ref,
        "command_ref": pane.command_ref,
        "attempt_id": pane.attempt_id,
        "workspace_ref": pane.workspace_ref,
        "provenance_refs": {
            "events_ref": event_store.events_path.relative_to(store.repo_root).as_posix(),
            "raw_trace_ref": resolved_raw_ref,
            "redacted_response_ref": resolved_redacted_ref,
        },
        "ownership": {
            "model": "foreground",
            "owner_pid": os.getpid(),
            "detach_resume_supported": False,
        },
    }


def _write_pane_payload(store: SessionStore, session_id: str, payload: dict[str, object]) -> None:
    pty_id = str(payload.get("pty_id") or "")
    if not pty_id:
        return
    ref = store._relative(store._session_dir(session_id) / "ptys" / f"{pty_id}.json")
    store._write_json_ref(ref, payload)


def _mark_stale_pane_if_needed(
    store: SessionStore,
    event_store: SessionEventStore,
    session: dict[str, object],
    pane: dict[str, object],
) -> dict[str, object]:
    if pane.get("state") not in {"running", "detached"}:
        return pane
    pid = pane.get("pid")
    if isinstance(pid, int) and _pid_alive(pid):
        return pane
    pane["state"] = "crashed"
    pane["ended_at"] = utc_now()
    _write_pane_payload(store, str(session["id"]), pane)
    _update_response_state_from_pane_payload(store, str(session["id"]), pane)
    event_store.append(
        "pty_exited",
        turn_id=pane.get("turn_id"),
        pty_id=pane.get("pty_id"),
        participant_id=pane.get("participant_id"),
        agent_id=pane.get("agent_id"),
        response_id=pane.get("response_id"),
        exit_code=None,
        state="crashed",
        actor={"type": "ait", "id": "session-panes"},
    )
    return pane


def _update_response_state_from_pane_payload(store: SessionStore, session_id: str, pane: dict[str, object]) -> None:
    response_id = pane.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        return
    path = store.repo_root / store._response_ref(session_id, response_id)
    if not path.exists():
        return
    try:
        response = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(response, dict):
        return
    response["state"] = pane.get("state")
    response["ended_at"] = pane.get("ended_at")
    if pane.get("cancellation_reason"):
        response["cancellation_reason"] = pane.get("cancellation_reason")
    store._write_json_ref(store._response_ref(session_id, response_id), response)


def _finish_attempt_if_needed(store: SessionStore, pane: TerminalPane, *, raw_ref: str | None) -> None:
    if pane.attempt_id is None:
        return
    conn = connect_db(store.repo_root / ".ait" / "state.sqlite3")
    try:
        attempt = get_attempt(conn, pane.attempt_id)
        if attempt is None:
            return
        process_event(
            conn,
            {
                "schema_version": 1,
                "event_id": f"ait-session-terminal-finish:{pane.attempt_id}:{new_ulid()}",
                "event_type": "attempt_finished",
                "sent_at": utc_now(),
                "attempt_id": pane.attempt_id,
                "ownership_token": attempt.ownership_token,
                "payload": {
                    "exit_code": int(pane.exit_code or 0),
                    "raw_trace_ref": raw_ref,
                },
            },
        )
        update_workspace_lease(
            attempt.workspace_ref,
            state="succeeded" if pane.exit_code == 0 else "failed",
            owner_pid=os.getpid(),
            owner_command="ait session attach",
        )
    finally:
        conn.close()


def _active_participants(session: dict[str, object], *, agent: str | None = None) -> list[dict[str, object]]:
    participants = [
        dict(item)
        for item in session.get("participants", [])
        if isinstance(item, dict) and item.get("state") == "active"
    ]
    if agent:
        participants = [item for item in participants if item.get("agent_id") == agent or item.get("id") == agent]
    return participants


def _find_running_pane(panes: list[TerminalPane], target: str) -> TerminalPane | None:
    for pane in panes:
        if pane.state == "running" and pane.process.poll() is None and target in {pane.agent_id, pane.participant_id, pane.pty_id}:
            return pane
    return None


def _pane_matches(pane: dict[str, object], target: str) -> bool:
    return target in {str(pane.get("agent_id")), str(pane.get("participant_id")), str(pane.get("pty_id"))}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stdin_is_interactive() -> bool:
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _events_ref(store: SessionStore, session_id: str) -> str:
    return store._relative(store._session_dir(session_id) / "streams" / "events.jsonl")


def _path_ref(store: SessionStore, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(store.repo_root).as_posix()
    except ValueError:
        return str(path)


def _attempt_agent_id(agent_id: str) -> str:
    if agent_id.count(":") == 1:
        return agent_id
    safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in agent_id.strip()).strip("-")
    return f"session:{safe or 'terminal'}"
