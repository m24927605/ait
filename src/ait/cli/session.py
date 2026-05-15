from __future__ import annotations

from ._shared import *

from ait.session_room import (
    SessionError,
    SessionStore,
    ask_session,
    parse_agent_command_options,
    parse_agent_options,
    start_session,
)
from ait.session_terminal import (
    build_attach_plan,
    kill_pane,
    list_panes,
    replay_session,
    run_foreground_attach,
    send_to_panes,
)


def handle(args, repo_root: Path, parser=None) -> int:
    try:
        result = _handle(args, repo_root)
    except SessionError as exc:
        if getattr(args, "format", "text") == "json":
            print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    if isinstance(result, int):
        return result
    payload, text = result
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


def _handle(args, repo_root: Path) -> tuple[dict[str, object], str] | int:
    store = SessionStore(repo_root)
    command = args.session_command
    if command == "start":
        result = start_session(
            repo_root,
            args.title,
            agents=parse_agent_options(args.agents),
            agent_commands=parse_agent_command_options(args.agent_command),
        )
        return result.payload, result.text
    if command == "ask":
        result = ask_session(repo_root, args.selector, args.message)
        return result.payload, result.text
    if command == "show":
        payload = store.show(args.selector)
        return payload, _format_session_text(payload)
    if command == "list":
        sessions = store.list_sessions()
        payload = {"schema_version": 1, "kind": "session_list", "sessions": [_session_summary(item) for item in sessions]}
        return payload, _format_session_list(payload)
    if command == "responses":
        responses = store.responses(args.selector)
        payload = {"schema_version": 1, "kind": "session_responses", "session_id": store.load(args.selector)["id"], "responses": responses}
        if args.format == "jsonl":
            for response in responses:
                print(json.dumps(response, sort_keys=True))
            return 0
        return payload, _format_responses_text(payload)
    if command == "export":
        rendered = store.export_markdown(args.selector)
        payload = {"schema_version": 1, "kind": "session_export", "format": args.format, "content": rendered}
        return payload, rendered
    if command == "attach":
        if args.format == "json":
            payload = build_attach_plan(store, args.selector, agent=args.agent)
            return payload, _format_attach_plan_text(payload)
        payload = run_foreground_attach(
            store,
            args.selector,
            agent=args.agent,
            layout=args.layout,
            input_lines=tuple(args.attach_input or ()),
            terminate_on_detach=args.terminate_on_detach,
            render=True,
        )
        return payload, _format_attach_text(payload)
    if command == "panes":
        payload = list_panes(store, args.selector)
        return payload, _format_panes_text(payload)
    if command == "send":
        if bool(args.send_to) == bool(args.send_all):
            raise SessionError("session send requires exactly one of --to or --all")
        if not args.message:
            raise SessionError("session send requires a message")
        payload = send_to_panes(
            store,
            args.selector,
            to_agent=args.send_to,
            all_agents=args.send_all,
            message=args.message,
        )
        return payload, _format_send_text(payload)
    if command == "kill":
        payload = kill_pane(store, args.selector, agent=args.agent)
        return payload, _format_kill_text(payload)
    if command == "replay":
        payload = replay_session(store, args.selector, turn=args.turn)
        return payload, str(payload.get("text") or "")
    if command == "run":
        if args.mode in {"panel", "council", "sequential"}:
            payload = store.run_panel(args.selector, timeout_seconds=args.timeout, mode=args.mode)
        elif args.mode == "role":
            payload = store.run_role(
                args.selector,
                implementers=tuple(args.implementer or ()),
                reviewers=tuple(args.reviewer or ()),
                allocation_plan_id=args.allocation,
                packages=tuple(args.package or ()),
            )
        else:
            raise SessionError(f"session mode not implemented yet: {args.mode}")
        return payload, _format_session_text(payload)
    if command == "panel":
        payload = store.show(args.selector)
        return payload, _format_panel_text(payload)
    if command == "summarize":
        payload = store.show(args.selector)
        return payload, _format_summary_text(payload)
    if command == "decision":
        payload = store.decision_accept(args.selector, accept_id=args.accept, promote_memory=args.promote_memory)
        return payload, _format_session_text(payload)
    if command == "attempt":
        payload = store.create_attempt_from_response(args.selector, source_id=args.from_response, agent=args.agent)
        return payload, _format_session_text(payload)
    if command == "retry":
        payload = store.retry_response(args.selector, args.response, timeout_seconds=args.timeout)
        return payload, _format_session_text(payload)
    if command == "cancel":
        payload = store.cancel(args.selector, response_id=args.response)
        return payload, _format_session_text(payload)
    if command == "participant":
        return _handle_participant(args, store)
    if command == "allocate":
        payload = store.allocation_plan(
            args.selector,
            agents=parse_agent_options(args.agents),
            strategy=args.strategy,
            packages=tuple(args.package or ()),
        )
        return payload, _format_allocation_text(payload)
    if command == "allocation":
        if args.allocation_command == "accept":
            payload = store.allocation_accept(args.selector, plan_id=args.plan)
            return payload, _format_session_text(payload)
        if args.allocation_command == "show":
            session = store.load(args.selector)
            payload = store._load_allocation(str(session["id"]), args.plan)
            return payload, _format_allocation_text(payload)
    return 1


def _handle_participant(args, store: SessionStore) -> tuple[dict[str, object], str]:
    if args.participant_command == "list":
        payload = store.participant_list(args.selector)
        return payload, _format_participants_text(payload)
    if args.participant_command == "add":
        payload = store.participant_add(
            args.selector,
            agent=args.agent,
            role=args.role,
            command_template=args.participant_command_template,
        )
        return payload, _format_session_text(payload)
    if args.participant_command == "remove":
        payload = store.participant_remove(
            args.selector,
            participant_id=args.participant_id,
            agent=args.agent,
            reason=args.reason,
        )
        return payload, _format_session_text(payload)
    raise SessionError("unknown participant command")


def _session_summary(session: dict[str, object]) -> dict[str, object]:
    return {
        "session_id": session.get("id"),
        "title": session.get("title"),
        "state": session.get("state"),
        "current_turn_id": session.get("current_turn_id"),
        "updated_at": session.get("updated_at"),
    }


def _format_session_list(payload: dict[str, object]) -> str:
    sessions = payload.get("sessions", [])
    if not sessions:
        return "No AIT sessions.\n"
    lines = ["AIT sessions"]
    for item in sessions:
        if isinstance(item, dict):
            lines.append(f"{item.get('session_id')}  {item.get('state')}  {item.get('title')}")
    return "\n".join(lines) + "\n"


def _format_session_text(payload: dict[str, object]) -> str:
    lines = [
        f"AIT session {payload.get('session_id')}",
        f"State: {payload.get('state')}",
        f"Turn: {payload.get('current_turn_id') or 'none'}",
    ]
    responses = payload.get("responses", [])
    if isinstance(responses, list) and responses:
        lines.append("Responses:")
        for item in responses:
            if isinstance(item, dict):
                lines.append(
                    f"  [{item.get('agent_id')}] {item.get('state')} · {item.get('response_id')} · {item.get('trust_class')}"
                )
    next_action = payload.get("next_action")
    if isinstance(next_action, dict):
        lines.append(f"Next: {next_action.get('recommended_command')}")
    return "\n".join(lines) + "\n"


def _format_panel_text(payload: dict[str, object]) -> str:
    lines = [_format_session_text(payload).rstrip()]
    for response in payload.get("responses", []):
        if isinstance(response, dict):
            lines.append(f"\n[{response.get('agent_id')}] {response.get('state')} · {response.get('response_id')}")
            refs = response.get("provenance_refs")
            if isinstance(refs, dict):
                lines.append(f"  redacted: {refs.get('redacted_response_ref')}")
    return "\n".join(lines) + "\n"


def _format_summary_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return "No summary available.\n"
    return json.dumps(summary, indent=2) + "\n"


def _format_responses_text(payload: dict[str, object]) -> str:
    lines = [f"Responses for {payload.get('session_id')}"]
    for response in payload.get("responses", []):
        if isinstance(response, dict):
            lines.append(f"{response.get('id')}  {response.get('agent_id')}  {response.get('state')}")
    return "\n".join(lines) + "\n"


def _format_participants_text(payload: dict[str, object]) -> str:
    lines = [f"Participants for {payload.get('session_id')}"]
    for participant in payload.get("participants", []):
        if isinstance(participant, dict):
            lines.append(f"{participant.get('id')}  {participant.get('agent_id')}  {participant.get('role')}  {participant.get('state')}")
    return "\n".join(lines) + "\n"


def _format_allocation_text(payload: dict[str, object]) -> str:
    lines = [
        f"Allocation plan {payload.get('id')}",
        f"State: {payload.get('state')}",
        f"Confidence: {payload.get('confidence')}",
    ]
    for package in payload.get("work_packages", []):
        if isinstance(package, dict):
            lines.append(f"  {package.get('title')}: {package.get('assigned_agent_id')} -> {', '.join(package.get('scope_paths', []))}")
    next_action = payload.get("recommended_next_action")
    if next_action:
        lines.append(f"Next: {next_action}")
    return "\n".join(lines) + "\n"


def _format_attach_plan_text(payload: dict[str, object]) -> str:
    lines = [f"Attach plan for {payload.get('session_id')}"]
    for participant in payload.get("participants", []):
        if isinstance(participant, dict):
            lines.append(
                f"{participant.get('participant_id')}  {participant.get('agent_id')}  {participant.get('state')}  {participant.get('cwd_policy')}"
            )
    for reason in payload.get("blocking_reasons", []):
        lines.append(f"Blocked: {reason}")
    return "\n".join(lines) + "\n"


def _format_attach_text(payload: dict[str, object]) -> str:
    lines = [f"Attached session {payload.get('session_id')}"]
    for pane in payload.get("panes", []):
        if isinstance(pane, dict):
            lines.append(f"{pane.get('pty_id')}  {pane.get('agent_id')}  {pane.get('state')}  {pane.get('response_id')}")
    for reason in payload.get("blocking_reasons", []):
        lines.append(f"Blocked: {reason}")
    return "\n".join(lines) + "\n"


def _format_panes_text(payload: dict[str, object]) -> str:
    lines = [f"Panes for {payload.get('session_id')}"]
    panes = payload.get("panes", [])
    if not panes:
        lines.append("No PTY panes.")
    for pane in panes:
        if isinstance(pane, dict):
            lines.append(
                f"{pane.get('pty_id')}  {pane.get('agent_id')}  {pane.get('state')}  pid={pane.get('pid')}  response={pane.get('response_id')}"
            )
    return "\n".join(lines) + "\n"


def _format_send_text(payload: dict[str, object]) -> str:
    lines = [f"Send for {payload.get('session_id')}: {'delivered' if payload.get('delivered') else 'blocked'}"]
    for reason in payload.get("blocking_reasons", []):
        lines.append(f"Blocked: {reason}")
    return "\n".join(lines) + "\n"


def _format_kill_text(payload: dict[str, object]) -> str:
    lines = [f"Kill for {payload.get('session_id')}"]
    for pane in payload.get("killed", []):
        if isinstance(pane, dict):
            lines.append(f"Killed {pane.get('agent_id')} {pane.get('pty_id')}")
    for reason in payload.get("blocking_reasons", []):
        lines.append(f"Blocked: {reason}")
    return "\n".join(lines) + "\n"
