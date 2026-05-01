from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from ait.db import connect_db, insert_memory_retrieval_event, run_migrations, utc_now
from ait.db.repositories import NewMemoryFact, NewMemoryRetrievalEvent, upsert_memory_fact
from ait.memory_policy import (
    EXCLUDED_MARKER,
    MemoryPolicy,
    default_memory_policy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
    transcript_excluded,
)
from ait.redaction import has_redactions, redact_text
from ait.repo import resolve_repo_root
from ait.workspace import commit_message

from .models import (
    AgentMemoryStatus,
    MemoryAttempt,
    MemoryCandidate,
    MemoryHealth,
    MemoryImportResult,
    MemoryLintFix,
    MemoryLintIssue,
    MemoryLintResult,
    MemoryNote,
    MemorySearchResult,
    RelevantMemoryItem,
    RelevantMemoryRecall,
    RepoMemory,
)

from .common import _read_trace_text, _trace_excluded
from .notes import _active_memory_source_exists, add_memory_note

def add_attempt_memory_note(repo_root: str | Path, attempt_result) -> MemoryNote | None:
    root = resolve_repo_root(repo_root)
    attempt = dict(attempt_result.attempt)
    attempt_id = str(attempt.get("id") or "")
    if not attempt_id:
        return None
    source = f"attempt-memory:{attempt_id}"
    if _active_memory_source_exists(root, source):
        return None

    files = getattr(attempt_result, "files", {}) or {}
    changed_files = _policy_visible_files(
        root,
        tuple(str(path) for path in files.get("changed", ())),
    )
    commits = tuple(str(commit.get("commit_oid")) for commit in getattr(attempt_result, "commits", []) if commit.get("commit_oid"))
    intent = _attempt_memory_intent_fields(root, str(attempt.get("intent_id") or ""))
    verified_status = str(attempt.get("verified_status") or "pending")
    if verified_status in {"failed", "failed_interrupted", "needs_review"}:
        return None
    outcome = getattr(attempt_result, "outcome", None) or {}
    outcome_class = str(outcome.get("outcome_class") or "unclassified") if isinstance(outcome, dict) else "unclassified"
    outcome_confidence = str(outcome.get("confidence") or "") if isinstance(outcome, dict) else ""
    exit_code = attempt.get("result_exit_code")
    confidence = _attempt_memory_confidence(verified_status=verified_status, outcome_class=outcome_class)
    body = _attempt_memory_note_body(
        attempt=attempt,
        intent=intent,
        changed_files=changed_files,
        commits=commits,
        confidence=confidence,
        outcome_class=outcome_class,
        outcome_confidence=outcome_confidence,
        exit_code=exit_code,
    )
    note = add_memory_note(
        root,
        topic="attempt-memory",
        body=body,
        source=source,
    )
    add_memory_candidates_for_attempt(root, attempt_result)
    return note

def _attempt_memory_confidence(*, verified_status: str, outcome_class: str) -> str:
    if verified_status == "promoted" or outcome_class == "promoted":
        return "high"
    if verified_status == "succeeded" and outcome_class == "succeeded":
        return "high"
    if verified_status == "succeeded" and outcome_class == "succeeded_noop":
        return "medium"
    return "advisory"

def add_memory_candidates_for_attempt(repo_root: str | Path, attempt_result) -> tuple[MemoryNote, ...]:
    root = resolve_repo_root(repo_root)
    attempt = dict(attempt_result.attempt)
    attempt_id = str(attempt.get("id") or "")
    if not attempt_id:
        return ()
    source = f"memory-candidate:{attempt_id}"
    if _active_memory_source_exists(root, source):
        return ()
    if _active_memory_source_exists(root, f"durable-memory:{attempt_id}"):
        return ()
    raw_trace_ref = str(attempt.get("raw_trace_ref") or "")
    policy = load_memory_policy(root)
    trace_text = _read_trace_text(raw_trace_ref, repo_root=root, limit=12000)
    if _trace_excluded(trace_text, policy=policy):
        return ()
    verified_status = str(attempt.get("verified_status") or "pending")
    candidates = extract_memory_candidates(
        trace_text,
        attempt_id=attempt_id,
        source_ref=raw_trace_ref,
        verified_status=verified_status,
    )
    corroboration_messages = _candidate_corroboration_messages(root, attempt_result)
    notes: list[MemoryNote] = []
    for candidate in candidates:
        durable = (
            verified_status in {"succeeded", "promoted"}
            and candidate.confidence == "high"
            and _candidate_corroborated(candidate, corroboration_messages)
        )
        _upsert_memory_fact_for_candidate(
            root,
            attempt_id=attempt_id,
            candidate=candidate,
            durable=durable,
        )
        notes.append(
            add_memory_note(
                root,
                topic="durable-memory" if durable else "memory-candidate",
                body=_memory_candidate_note_body(candidate, durable=durable),
                source=(f"durable-memory:{attempt_id}" if durable else source),
            )
        )
    return tuple(notes)

def _upsert_memory_fact_for_candidate(
    repo_root: Path,
    *,
    attempt_id: str,
    candidate: MemoryCandidate,
    durable: bool,
) -> None:
    now = utc_now()
    fact_id = f"{attempt_id}:memory-fact:{uuid.uuid5(uuid.NAMESPACE_URL, attempt_id + ':' + candidate.body).hex}"
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id=fact_id,
                kind=_memory_fact_kind(candidate.kind),
                topic=candidate.topic,
                body=candidate.body,
                summary=_memory_fact_summary(candidate.body),
                status="accepted" if durable else "candidate",
                confidence="medium" if durable else "low",
                source_attempt_id=attempt_id,
                source_trace_ref=candidate.source_ref,
                human_review_state="pending" if durable else "pending",
                provenance="commit" if durable else "transcript",
                valid_from=now,
                created_at=now,
                updated_at=now,
            ),
        )
    finally:
        conn.close()

def extract_memory_candidates(
    text: str,
    *,
    attempt_id: str,
    source_ref: str,
    verified_status: str,
) -> tuple[MemoryCandidate, ...]:
    del verified_status
    candidates: list[MemoryCandidate] = []
    seen: set[str] = set()
    skip_next_role_payload = False
    for line in text.splitlines():
        raw = line.strip()
        if raw.lower() in {"user", "exec"}:
            skip_next_role_payload = True
            continue
        if skip_next_role_payload:
            skip_next_role_payload = False
            continue
        cleaned = _candidate_line(line)
        if not cleaned:
            continue
        seen_key = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        if seen_key in seen:
            continue
        kind = _candidate_kind(cleaned)
        if kind is None:
            continue
        seen.add(seen_key)
        candidates.append(
            MemoryCandidate(
                kind=kind,
                topic=_candidate_topic(kind),
                body=cleaned,
                confidence="high",
                status="candidate",
                reason="durable marker in transcript",
                source_ref=source_ref or attempt_id,
            )
        )
    return tuple(candidates)

def _policy_visible_files(root: Path, paths: tuple[str, ...]) -> tuple[str, ...]:
    policy = load_memory_policy(root)
    return tuple(path for path in paths if not path_excluded(path, policy))

def _attempt_memory_intent_fields(root: Path, intent_id: str) -> dict[str, str]:
    if not intent_id:
        return {}
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        row = conn.execute(
            """
            SELECT title, kind, description
            FROM intents
            WHERE id = ?
            """,
            (intent_id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "title": str(row["title"]),
            "kind": str(row["kind"] or ""),
            "description": str(row["description"] or ""),
        }
    finally:
        conn.close()

def _attempt_memory_note_body(
    *,
    attempt: dict[str, object],
    intent: dict[str, str],
    changed_files: tuple[str, ...],
    commits: tuple[str, ...],
    confidence: str,
    outcome_class: str,
    outcome_confidence: str,
    exit_code: object,
) -> str:
    attempt_id = str(attempt.get("id") or "")
    intent_id = str(attempt.get("intent_id") or "")
    agent_id = str(attempt.get("agent_id") or "")
    verified_status = str(attempt.get("verified_status") or "pending")
    reported_status = str(attempt.get("reported_status") or "created")
    raw_trace_ref = str(attempt.get("raw_trace_ref") or "")
    intent_title = intent.get("title", "")
    intent_kind = intent.get("kind", "")
    intent_description = intent.get("description", "")
    changed_text = ", ".join(changed_files) if changed_files else "none"
    commits_text = ", ".join(commits) if commits else "none"
    return "\n".join(
        [
            "AIT attempt memory",
            f"attempt_id={attempt_id}",
            f"intent_id={intent_id}",
            f"intent_title={intent_title}",
            f"intent_kind={intent_kind}",
            f"intent_description={intent_description}",
            f"agent_id={agent_id}",
            f"reported_status={reported_status}",
            f"verified_status={verified_status}",
            f"outcome_class={outcome_class}",
            f"outcome_confidence={outcome_confidence}",
            f"exit_code={exit_code}",
            f"confidence={confidence}",
            f"changed_files={changed_text}",
            f"commit_oids={commits_text}",
            f"raw_trace_ref={raw_trace_ref}",
            "",
            (
                "Reusable summary: "
                f"{agent_id} completed {intent_title or 'an attempt'} with status {verified_status}. "
                f"Changed files: {changed_text}. Commits: {commits_text}."
            ),
        ]
    )

def _memory_candidate_note_body(candidate: MemoryCandidate, *, durable: bool) -> str:
    status = "accepted" if durable else candidate.status
    return "\n".join(
        [
            "AIT memory candidate",
            f"kind={candidate.kind}",
            f"topic={candidate.topic}",
            f"confidence={candidate.confidence}",
            f"status={status}",
            f"reason={candidate.reason}",
            f"source_ref={candidate.source_ref}",
            "",
            candidate.body,
        ]
    )

def _candidate_line(line: str) -> str:
    cleaned = " ".join(line.strip().lstrip("-•>› ").split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.startswith(
        (
            "token usage:",
            "to continue this session",
            "ait agent transcript",
            "attempt-id:",
            "command:",
            "exit-code:",
            "redacted:",
            "stdout:",
            "stderr:",
        )
    ):
        return ""
    if lowered.startswith(("/bin/", "python ", "node ", "npm ", "pnpm ", "yarn ")):
        return ""
    if " && " in lowered and (" > " in lowered or "printf " in lowered):
        return ""
    if lowered in {"hi", "hello", "你是誰?", "你是誰"}:
        return ""
    return cleaned[:600]

def _candidate_corroboration_messages(root: Path, attempt_result) -> tuple[str, ...]:
    messages: list[str] = []
    workspace_ref = str(dict(getattr(attempt_result, "attempt", {}) or {}).get("workspace_ref") or "")
    for commit in getattr(attempt_result, "commits", ()) or ():
        if isinstance(commit, dict):
            for key in ("message", "commit_message", "subject", "summary"):
                value = commit.get(key)
                if value:
                    messages.append(str(value).lower())
            commit_oid = str(commit.get("commit_oid") or "")
            if workspace_ref and commit_oid:
                try:
                    messages.append(commit_message(workspace_ref, commit_oid).lower())
                except Exception:
                    continue
    return tuple(messages)

def _candidate_corroborated(candidate: MemoryCandidate, corroboration_messages: tuple[str, ...]) -> bool:
    if not corroboration_messages:
        return False
    snippet = candidate.body[:60].lower()
    return bool(snippet) and any(snippet in message for message in corroboration_messages)

def _candidate_kind(line: str) -> str | None:
    lowered = line.lower()
    if not re.match(r"^(decision|rule|workflow|test|failure|open question)\s*:", lowered):
        return None
    markers: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("decision", ("decision:",)),
        ("constraint", ("rule:",)),
        ("workflow", ("workflow:",)),
        ("test", ("test:",)),
        ("failure", ("failure:",)),
        ("open-question", ("open question:",)),
    )
    for kind, candidates in markers:
        if any(marker in lowered or marker in line for marker in candidates):
            return kind
    return None

def _candidate_topic(kind: str) -> str:
    return {
        "decision": "architecture",
        "constraint": "project-rule",
        "workflow": "workflow",
        "test": "testing",
        "failure": "failure",
        "open-question": "open-question",
    }.get(kind, "project-knowledge")

def _memory_fact_kind(candidate_kind: str) -> str:
    return {
        "constraint": "rule",
        "decision": "decision",
        "workflow": "workflow",
        "test": "workflow",
        "failure": "failure",
        "open-question": "current_state",
    }.get(candidate_kind, "entity")

def _memory_fact_summary(body: str) -> str:
    compacted = " ".join(body.split())
    return compacted[:160]
