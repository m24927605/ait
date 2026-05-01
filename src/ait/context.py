from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from ait.db import (
    AttemptRecord,
    EvidenceSummaryRecord,
    connect_db,
    get_evidence_summary,
    get_intent,
    list_attempt_commits,
    list_evidence_files,
    list_intent_attempts,
)
from ait.idresolver import resolve_intent_id
from ait.memory_policy import EXCLUDED_MARKER, default_memory_policy, transcript_excluded
from ait.redaction import redact_text
from ait.repo import resolve_repo_root


@dataclass(frozen=True, slots=True)
class ContextAttempt:
    id: str
    ordinal: int
    agent_id: str
    reported_status: str
    verified_status: str
    started_at: str
    ended_at: str | None
    result_exit_code: int | None
    workspace_ref: str
    tool_calls: int
    commands_run: int
    file_reads: int
    file_writes: int
    duration_ms: int
    files: dict[str, tuple[str, ...]]
    commit_oids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentContext:
    intent: dict[str, object]
    attempts: tuple[ContextAttempt, ...]
    files: dict[str, tuple[str, ...]] = field(default_factory=dict)
    recommended: tuple[str, ...] = ()


def build_agent_context(repo_root: str | Path, *, intent_id: str) -> AgentContext:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        return build_agent_context_with_connection(conn, intent_id=intent_id)
    finally:
        conn.close()


def build_agent_context_with_connection(
    conn: sqlite3.Connection,
    *,
    intent_id: str,
) -> AgentContext:
    intent_id = resolve_intent_id(conn, intent_id)
    intent = get_intent(conn, intent_id)
    if intent is None:
        raise ValueError(f"Unknown intent: {intent_id}")

    attempts = list_intent_attempts(conn, intent_id)
    context_attempts = tuple(
        _context_attempt(conn, attempt)
        for attempt in sorted(attempts, key=lambda item: item.started_at, reverse=True)
    )
    files = _aggregate_files(context_attempts)
    return AgentContext(
        intent=intent.__dict__,
        attempts=context_attempts,
        files=files,
        recommended=_recommendations(context_attempts),
    )


def render_agent_context_text(context: AgentContext) -> str:
    intent = context.intent
    title = _context_safe_text(str(intent["title"]))
    kind = _context_safe_text(str(intent.get("kind") or ""))
    description = _context_safe_text(str(intent.get("description") or ""))
    lines = [
        f"Intent: {title}",
        f"Intent ID: {intent['id']}",
        f"Status: {intent['status']}",
    ]
    if kind:
        lines.append(f"Kind: {kind}")
    if description:
        lines.append(f"Description: {description}")

    lines.append("")
    lines.append("Attempts:")
    if not context.attempts:
        lines.append("- none")
    for attempt in context.attempts:
        lines.append(
            "- "
            f"{attempt.id} ordinal={attempt.ordinal} agent={attempt.agent_id} "
            f"reported={attempt.reported_status} verified={attempt.verified_status} "
            f"exit={attempt.result_exit_code}"
        )
        if attempt.commit_oids:
            lines.append(f"  commits: {', '.join(attempt.commit_oids)}")
        changed = attempt.files.get("changed", ())
        touched = attempt.files.get("touched", ())
        read = attempt.files.get("read", ())
        if changed:
            lines.append(f"  files.changed: {', '.join(changed)}")
        if touched:
            lines.append(f"  files.touched: {', '.join(touched)}")
        if read:
            lines.append(f"  files.read: {', '.join(read)}")
        lines.append(
            "  observed: "
            f"tool_calls={attempt.tool_calls}, commands={attempt.commands_run}, "
            f"reads={attempt.file_reads}, writes={attempt.file_writes}, "
            f"duration_ms={attempt.duration_ms}"
        )

    lines.append("")
    lines.append("Evidence:")
    if not context.files:
        lines.append("- none")
    for kind in sorted(context.files):
        lines.append(f"- files.{kind}: {', '.join(context.files[kind])}")

    lines.append("")
    lines.append("Recommended:")
    if not context.recommended:
        lines.append("- no prior attempt evidence; inspect the repository normally")
    for item in context.recommended:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _context_safe_text(value: str) -> str:
    redacted, _ = redact_text(value)
    if transcript_excluded(redacted, default_memory_policy()):
        return EXCLUDED_MARKER
    return redacted


def _context_attempt(conn: sqlite3.Connection, attempt: AttemptRecord) -> ContextAttempt:
    evidence = get_evidence_summary(conn, attempt.id)
    files = list_evidence_files(conn, attempt.id)
    commits = tuple(commit.commit_oid for commit in list_attempt_commits(conn, attempt.id))
    return ContextAttempt(
        id=attempt.id,
        ordinal=attempt.ordinal,
        agent_id=attempt.agent_id,
        reported_status=attempt.reported_status,
        verified_status=attempt.verified_status,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        result_exit_code=attempt.result_exit_code,
        workspace_ref=attempt.workspace_ref,
        tool_calls=_evidence_int(evidence, "observed_tool_calls"),
        commands_run=_evidence_int(evidence, "observed_commands_run"),
        file_reads=_evidence_int(evidence, "observed_file_reads"),
        file_writes=_evidence_int(evidence, "observed_file_writes"),
        duration_ms=_evidence_int(evidence, "observed_duration_ms"),
        files=files,
        commit_oids=commits,
    )


def _aggregate_files(attempts: tuple[ContextAttempt, ...]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = {}
    for attempt in attempts:
        for kind, paths in attempt.files.items():
            grouped.setdefault(kind, set()).update(paths)
    return {kind: tuple(sorted(paths)) for kind, paths in grouped.items()}


def _recommendations(attempts: tuple[ContextAttempt, ...]) -> tuple[str, ...]:
    items: list[str] = []
    succeeded = [attempt for attempt in attempts if attempt.verified_status == "succeeded"]
    failed = [attempt for attempt in attempts if attempt.verified_status == "failed"]
    if succeeded:
        latest = succeeded[0]
        items.append(f"inspect latest succeeded attempt first: {latest.id}")
    if failed:
        latest = failed[0]
        items.append(f"review latest failed attempt before retrying: {latest.id}")
    if any(attempt.verified_status == "succeeded" for attempt in attempts):
        items.append("rebase the attempt before promote if the target branch moved")
    return tuple(items)


def _evidence_int(evidence: EvidenceSummaryRecord | None, attr: str) -> int:
    if evidence is None:
        return 0
    return int(getattr(evidence, attr))
