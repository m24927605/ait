from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import shlex

from ait.app import init_repo
from ait.db import AttemptRecord, connect_db, get_attempt
from ait.recent_activity import list_recent_activities
from ait.recovery import RecoverError
from ait.resume import ResumeError, ResumeResult, build_resume_result
from ait.session_room import SessionError, SessionStore


_CODEX_RESUME_RE = re.compile(r"\bcodex\s+resume\s+([A-Za-z0-9._:-]+)")


@dataclass(frozen=True, slots=True)
class AgentHint:
    agent_id: str
    command: str | None
    source: str
    note: str


@dataclass(frozen=True, slots=True)
class ContinueResult:
    selector: str
    repo_root: str | None
    target_type: str
    command: str | None
    reason: str
    session: dict[str, object] | None
    resume: ResumeResult | None
    agent_hints: tuple[AgentHint, ...]
    safe_actions: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "kind": "continue_plan",
            "selector": self.selector,
            "repo_root": self.repo_root,
            "target_type": self.target_type,
            "command": self.command,
            "reason": self.reason,
            "session": self.session,
            "resume": None if self.resume is None else self.resume.to_dict(),
            "agent_hints": [asdict(hint) for hint in self.agent_hints],
            "safe_actions": list(self.safe_actions),
            "blocking_reasons": list(self.blocking_reasons),
            "limitations": list(self.limitations),
        }
        return payload


@dataclass(frozen=True, slots=True)
class _Candidate:
    repo_root: Path
    target_type: str
    timestamp: str
    command: str | None
    reason: str
    session: dict[str, object] | None = None
    resume: ResumeResult | None = None
    attempt: AttemptRecord | None = None
    blocking_reasons: tuple[str, ...] = ()


def build_continue_result(
    repo_root: str | Path,
    *,
    selector: str = "latest",
) -> ContinueResult:
    roots, candidates = _rooted_continue_candidates(repo_root, selector=selector)
    if not candidates:
        return ContinueResult(
            selector=selector,
            repo_root=str(roots[0]) if roots else None,
            target_type="none",
            command=None,
            reason="AIT found no active session or recoverable attempt.",
            session=None,
            resume=None,
            agent_hints=(),
            safe_actions=(),
            blocking_reasons=("no AIT session or recoverable attempt matched the selector",),
            limitations=_limitations(),
        )

    chosen = _choose_candidate(candidates, selector=selector)
    hints = _agent_hints(chosen.repo_root, chosen)
    safe_actions = _safe_actions(chosen)
    return ContinueResult(
        selector=selector,
        repo_root=str(chosen.repo_root),
        target_type=chosen.target_type,
        command=chosen.command,
        reason=chosen.reason,
        session=chosen.session,
        resume=chosen.resume,
        agent_hints=hints,
        safe_actions=safe_actions,
        blocking_reasons=chosen.blocking_reasons,
        limitations=_limitations(),
    )


def _rooted_continue_candidates(
    repo_root: str | Path,
    *,
    selector: str,
) -> tuple[tuple[Path, ...], list[_Candidate]]:
    roots: list[Path] = []
    first_error: ValueError | None = None
    try:
        current_root = init_repo(repo_root).repo_root
        roots.append(current_root)
    except ValueError as exc:
        first_error = exc

    current_candidates = [
        candidate
        for root in roots
        for candidate in _continue_candidates(root, selector)
    ]
    if current_candidates or selector != "latest":
        return tuple(roots), current_candidates

    seen = {str(root) for root in roots}
    for activity in list_recent_activities():
        if not Path(activity.repo_root).exists():
            continue
        try:
            root = init_repo(activity.repo_root).repo_root
        except ValueError:
            continue
        key = str(root)
        if key in seen:
            continue
        roots.append(root)
        seen.add(key)
    if not roots and first_error is not None:
        raise first_error
    candidates = [
        candidate
        for root in roots
        for candidate in _continue_candidates(root, selector)
    ]
    return tuple(roots), candidates


def _continue_candidates(root: Path, selector: str) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    session = _load_session(root, selector)
    if session is not None:
        candidates.append(_session_candidate(root, session))
    attempt_candidate = _attempt_candidate(root, selector)
    if attempt_candidate is not None:
        candidates.append(attempt_candidate)
    return candidates


def _choose_candidate(candidates: list[_Candidate], *, selector: str) -> _Candidate:
    if selector != "latest":
        return candidates[0]
    return max(candidates, key=lambda item: (item.timestamp, _target_priority(item.target_type)))


def _target_priority(target_type: str) -> int:
    return {
        "session_attach": 3,
        "attempt_resume": 2,
        "session": 1,
    }.get(target_type, 0)


def _load_session(root: Path, selector: str) -> dict[str, object] | None:
    try:
        return SessionStore(root).load(selector)
    except SessionError:
        return None


def _session_candidate(root: Path, session: dict[str, object]) -> _Candidate:
    store = SessionStore(root)
    turn = store._current_turn_or_none(session)
    participants = [
        item
        for item in session.get("participants", [])
        if isinstance(item, dict) and item.get("state") == "active"
    ]
    session_id = str(session["id"])
    timestamp = str(session.get("updated_at") or session.get("created_at") or "")
    if turn is not None and participants:
        return _Candidate(
            repo_root=root,
            target_type="session_attach",
            timestamp=timestamp,
            command=f"ait session attach {shlex.quote(session_id)}",
            reason="latest AIT session has an active turn and attachable participants",
            session=_session_summary(session, turn=turn, participants=participants),
        )
    blocking_reasons: list[str] = []
    if turn is None:
        blocking_reasons.append("session has no turn yet")
    if not participants:
        blocking_reasons.append("session has no active participants")
    return _Candidate(
        repo_root=root,
        target_type="session",
        timestamp=timestamp,
        command=f"ait session show {shlex.quote(session_id)}",
        reason="latest AIT session exists but is not directly attachable",
        session=_session_summary(session, turn=turn, participants=participants),
        blocking_reasons=tuple(blocking_reasons),
    )


def _session_summary(
    session: dict[str, object],
    *,
    turn: dict[str, object] | None,
    participants: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "session_id": session.get("id"),
        "title": session.get("title"),
        "state": session.get("state"),
        "current_turn_id": None if turn is None else turn.get("id"),
        "updated_at": session.get("updated_at"),
        "participants": [
            {
                "participant_id": item.get("id"),
                "agent_id": item.get("agent_id"),
                "role": item.get("role"),
                "state": item.get("state"),
            }
            for item in participants
        ],
    }


def _attempt_candidate(root: Path, selector: str) -> _Candidate | None:
    try:
        resume = build_resume_result(root, attempt_selector=selector)
    except (RecoverError, ResumeError, ValueError):
        return None
    attempt = _load_attempt(root, resume.attempt_id)
    timestamp = ""
    if attempt is not None:
        timestamp = max(
            value
            for value in (attempt.started_at, attempt.ended_at, attempt.heartbeat_at)
            if value
        )
    return _Candidate(
        repo_root=root,
        target_type="attempt_resume",
        timestamp=timestamp,
        command=f"ait resume {shlex.quote(resume.attempt_id)}",
        reason="recoverable AIT attempt workspace is available",
        resume=resume,
        attempt=attempt,
    )


def _load_attempt(root: Path, attempt_id: str) -> AttemptRecord | None:
    init_result = init_repo(root)
    conn = connect_db(init_result.db_path)
    try:
        return get_attempt(conn, attempt_id)
    finally:
        conn.close()


def _agent_hints(root: Path, candidate: _Candidate) -> tuple[AgentHint, ...]:
    if candidate.target_type == "session_attach" and candidate.session is not None:
        return tuple(
            AgentHint(
                agent_id=str(item.get("agent_id") or ""),
                command=candidate.command,
                source="ait-session",
                note="AIT owns the foreground attach flow for this session.",
            )
            for item in candidate.session.get("participants", [])
            if isinstance(item, dict) and item.get("agent_id")
        )
    if candidate.resume is None or candidate.attempt is None:
        return ()
    workspace = candidate.resume.workspace_ref
    attempt = candidate.attempt
    harness = attempt.agent_harness or attempt.agent_id.split(":", 1)[0]
    agent_id = attempt.agent_id
    if harness == "claude-code":
        return (
            AgentHint(
                agent_id=agent_id,
                command=f"cd {shlex.quote(workspace)} && claude --continue",
                source="agent-harness",
                note="Use this if Claude Code still has its own local conversation state.",
            ),
        )
    if harness == "codex":
        resume_id = _codex_resume_id(root, attempt.raw_trace_ref)
        if resume_id:
            return (
                AgentHint(
                    agent_id=agent_id,
                    command=f"cd {shlex.quote(workspace)} && codex resume {shlex.quote(resume_id)}",
                    source="raw-trace",
                    note="AIT found a native Codex resume command in the saved trace.",
                ),
            )
        return (
            AgentHint(
                agent_id=agent_id,
                command=None,
                source="agent-harness",
                note="AIT did not find a native Codex resume id; resume from the worktree with `ait resume`.",
            ),
        )
    if harness == "aider":
        return (
            AgentHint(
                agent_id=agent_id,
                command=f"cd {shlex.quote(workspace)} && aider",
                source="agent-harness",
                note="Reopens Aider in the recovered worktree; Aider history depends on its own local state.",
            ),
        )
    return (
        AgentHint(
            agent_id=agent_id,
            command=f"cd {shlex.quote(workspace)}",
            source="workspace",
            note="AIT can restore the worktree even when the agent CLI cannot resume its own process.",
        ),
    )


def _codex_resume_id(root: Path, raw_trace_ref: str | None) -> str | None:
    if not raw_trace_ref:
        return None
    trace_path = root / raw_trace_ref
    if not trace_path.exists():
        return None
    try:
        trace = trace_path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return None
    match = _CODEX_RESUME_RE.search(trace)
    if match is None:
        return None
    return match.group(1)


def _safe_actions(candidate: _Candidate) -> tuple[str, ...]:
    actions: list[str] = []
    if candidate.command:
        actions.append(candidate.command)
    if candidate.resume is not None:
        actions.extend(candidate.resume.finish_steps)
    return tuple(actions)


def _limitations() -> tuple[str, ...]:
    return (
        "AIT can restore local session metadata and attempt worktrees, but it cannot resurrect an OS terminal process after that process is killed.",
        "Native agent resume depends on each agent CLI preserving its own local conversation state.",
    )
