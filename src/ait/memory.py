from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from ait.db import connect_db, run_migrations, utc_now
from ait.db.repositories import get_attempt_outcome
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


@dataclass(frozen=True, slots=True)
class MemoryNote:
    id: str
    topic: str | None
    body: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MemoryAttempt:
    intent_title: str
    intent_status: str
    attempt_id: str
    agent_id: str
    verified_status: str
    result_exit_code: int | None
    started_at: str
    changed_files: tuple[str, ...]
    commit_oids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    kind: str
    id: str
    score: float
    title: str
    text: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    kind: str
    topic: str
    body: str
    confidence: str
    status: str
    reason: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class RelevantMemoryItem:
    kind: str
    id: str
    source: str
    topic: str
    score: float
    text: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RelevantMemoryRecall:
    query: str
    selected: tuple[RelevantMemoryItem, ...]
    skipped: tuple[dict[str, object], ...]
    budget_chars: int
    rendered_chars: int
    compacted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "selected": [item.to_dict() for item in self.selected],
            "skipped": list(self.skipped),
            "budget_chars": self.budget_chars,
            "rendered_chars": self.rendered_chars,
            "compacted": self.compacted,
        }


@dataclass(frozen=True, slots=True)
class RepoMemory:
    repo_root: str
    recent_attempts: tuple[MemoryAttempt, ...]
    hot_files: tuple[str, ...]
    notes: tuple[MemoryNote, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "recent_attempts": [asdict(attempt) for attempt in self.recent_attempts],
            "hot_files": list(self.hot_files),
            "notes": [asdict(note) for note in self.notes],
            "recommendations": list(self.recommendations),
        }


@dataclass(frozen=True, slots=True)
class MemoryImportResult:
    imported: tuple[MemoryNote, ...]
    skipped: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "imported": [asdict(note) for note in self.imported],
            "skipped": list(self.skipped),
        }


@dataclass(frozen=True, slots=True)
class AgentMemoryStatus:
    initialized: bool
    imported_sources: tuple[str, ...]
    candidate_paths: tuple[str, ...]
    pending_paths: tuple[str, ...]
    state_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "initialized": self.initialized,
            "imported_sources": list(self.imported_sources),
            "candidate_paths": list(self.candidate_paths),
            "pending_paths": list(self.pending_paths),
            "state_path": self.state_path,
        }


@dataclass(frozen=True, slots=True)
class MemoryLintIssue:
    code: str
    severity: str
    note_id: str
    source: str
    topic: str | None
    detail: str
    fixable: bool
    fixed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryLintFix:
    note_id: str
    action: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryLintResult:
    checked: int
    issues: tuple[MemoryLintIssue, ...]
    fixes: tuple[MemoryLintFix, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "issue_count": len(self.issues),
            "fix_count": len(self.fixes),
            "issues": [issue.to_dict() for issue in self.issues],
            "fixes": [fix.to_dict() for fix in self.fixes],
        }


@dataclass(frozen=True, slots=True)
class MemoryHealth:
    status: str
    checked: int
    issue_count: int
    error_count: int
    warning_count: int
    info_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


AGENT_MEMORY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "claude": (
        "CLAUDE.md",
        ".claude/memory.md",
        ".claude/CLAUDE.md",
    ),
    "codex": (
        "AGENTS.md",
        ".codex/memory.md",
        ".codex/AGENTS.md",
    ),
    "cursor": (
        ".cursor/rules",
        ".cursor/rules.md",
        ".cursorrules",
    ),
}


def build_repo_memory(
    repo_root: str | Path,
    *,
    limit: int = 8,
    path_filter: str | None = None,
    topic: str | None = None,
    promoted_only: bool = False,
) -> RepoMemory:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return build_repo_memory_with_connection(
            conn,
            repo_root=root,
            limit=limit,
            path_filter=path_filter,
            topic=topic,
            promoted_only=promoted_only,
            policy=policy,
        )
    finally:
        conn.close()


def build_repo_memory_with_connection(
    conn: sqlite3.Connection,
    *,
    repo_root: str | Path,
    limit: int = 8,
    path_filter: str | None = None,
    topic: str | None = None,
    promoted_only: bool = False,
    policy: MemoryPolicy | None = None,
) -> RepoMemory:
    resolved_policy = policy or default_memory_policy()
    attempts = tuple(
        _recent_attempts(
            conn,
            limit=limit,
            path_filter=path_filter,
            promoted_only=promoted_only,
            policy=resolved_policy,
        )
    )
    hot_files = _hot_files(conn, limit=10, path_filter=path_filter, policy=resolved_policy)
    notes = _memory_notes(conn, limit=limit, topic=topic)
    return RepoMemory(
        repo_root=str(Path(repo_root).resolve()),
        recent_attempts=attempts,
        hot_files=hot_files,
        notes=notes,
        recommendations=_recommendations(attempts, hot_files, notes),
    )


def render_repo_memory_text(memory: RepoMemory, *, budget_chars: int | None = None) -> str:
    lines = [
        "AIT Long-Term Repo Memory",
        f"Repo: {memory.repo_root}",
        "",
        "Curated Notes:",
    ]
    if not memory.notes:
        lines.append("- none")
    for note in memory.notes:
        body, redacted = redact_text(note.body)
        topic = note.topic if note.topic else "general"
        lines.append(f"- {note.id} topic={topic} source={note.source}")
        lines.append(f"  {body}")
        if redacted:
            lines.append("  redacted: true")

    lines.extend(
        [
            "",
            "Recent Attempts:",
        ]
    )
    if not memory.recent_attempts:
        lines.append("- none recorded yet")
    for attempt in memory.recent_attempts:
        lines.append(
            "- "
            f"{attempt.attempt_id} intent={attempt.intent_title!r} "
            f"agent={attempt.agent_id} verified={attempt.verified_status} "
            f"exit={attempt.result_exit_code}"
        )
        if attempt.changed_files:
            lines.append(f"  changed: {', '.join(attempt.changed_files)}")
        if attempt.commit_oids:
            lines.append(f"  commits: {', '.join(attempt.commit_oids)}")

    lines.append("")
    lines.append("Hot Files:")
    if not memory.hot_files:
        lines.append("- none")
    for file_path in memory.hot_files:
        lines.append(f"- {file_path}")

    lines.append("")
    lines.append("Recommended Memory Use:")
    for recommendation in memory.recommendations:
        lines.append(f"- {recommendation}")
    text = "\n".join(lines) + "\n"
    if budget_chars is None or budget_chars <= 0 or len(text) <= budget_chars:
        return text
    marker = "\n[ait memory compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker


def add_memory_note(
    repo_root: str | Path,
    *,
    body: str,
    topic: str | None = None,
    source: str = "manual",
) -> MemoryNote:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        note = MemoryNote(
            id=f"note:{uuid.uuid4().hex}",
            topic=topic,
            body=body,
            source=source,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        with conn:
            conn.execute(
                """
                INSERT INTO memory_notes(id, created_at, updated_at, topic, body, source, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (note.id, note.created_at, note.updated_at, note.topic, note.body, note.source),
            )
        return note
    finally:
        conn.close()


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
    outcome = getattr(attempt_result, "outcome", None) or {}
    outcome_class = str(outcome.get("outcome_class") or "unclassified") if isinstance(outcome, dict) else "unclassified"
    outcome_confidence = str(outcome.get("confidence") or "") if isinstance(outcome, dict) else ""
    exit_code = attempt.get("result_exit_code")
    confidence = "high" if verified_status in {"succeeded", "promoted"} else "advisory"
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
    outcome_class = _attempt_result_outcome_class(root, attempt_id)
    candidates = extract_memory_candidates(
        trace_text,
        attempt_id=attempt_id,
        source_ref=raw_trace_ref,
        verified_status=verified_status,
    )
    notes: list[MemoryNote] = []
    for candidate in candidates:
        durable = (
            verified_status in {"succeeded", "promoted"}
            and outcome_class in {"succeeded", "promoted"}
            and candidate.confidence == "high"
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


def _attempt_result_outcome_class(repo_root: Path, attempt_id: str) -> str:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        outcome = get_attempt_outcome(conn, attempt_id)
    finally:
        conn.close()
    if outcome is None:
        return "succeeded"
    return outcome.outcome_class


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
        if not cleaned or cleaned in seen:
            continue
        kind = _candidate_kind(cleaned)
        if kind is None:
            continue
        seen.add(cleaned)
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


def import_agent_memory(
    repo_root: str | Path,
    *,
    source: str = "auto",
    paths: tuple[str, ...] = (),
    topic: str = "agent-memory",
    max_chars: int = 6000,
) -> MemoryImportResult:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    source_names = tuple(AGENT_MEMORY_CANDIDATES) if source == "auto" else (source,)
    if source != "auto" and source not in AGENT_MEMORY_CANDIDATES:
        source_names = (source,)
    candidates = _agent_memory_candidates(root, source_names=source_names, paths=paths)
    imported: list[MemoryNote] = []
    skipped: list[dict[str, str]] = []
    existing = _existing_import_bodies(root)
    for source_name, relative_path, path in candidates:
        if relative_path in {item["path"] for item in skipped}:
            continue
        if path_excluded(relative_path, policy):
            skipped.append({"path": relative_path, "source": source_name, "reason": "excluded by memory policy"})
            continue
        if not path.exists():
            skipped.append({"path": relative_path, "source": source_name, "reason": "not found"})
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                child_relative = child.relative_to(root).as_posix()
                if path_excluded(child_relative, policy):
                    skipped.append({"path": child_relative, "source": source_name, "reason": "excluded by memory policy"})
                    continue
                _import_one_agent_memory_file(
                    root,
                    source_name=source_name,
                    relative_path=child_relative,
                    path=child,
                    topic=topic,
                    max_chars=max_chars,
                    existing=existing,
                    imported=imported,
                    skipped=skipped,
                )
            continue
        _import_one_agent_memory_file(
            root,
            source_name=source_name,
            relative_path=relative_path,
            path=path,
            topic=topic,
            max_chars=max_chars,
            existing=existing,
            imported=imported,
            skipped=skipped,
        )
    return MemoryImportResult(imported=tuple(imported), skipped=tuple(skipped))


def ensure_agent_memory_imported(repo_root: str | Path) -> MemoryImportResult:
    root = resolve_repo_root(repo_root)
    state_path = _agent_memory_import_state_path(root)
    signature = _agent_memory_signature(root)
    state = _read_agent_memory_import_state(state_path)
    status = agent_memory_status(root)
    if state.get("signature") == signature and status.initialized and not status.pending_paths:
        return MemoryImportResult(imported=(), skipped=())
    result = import_agent_memory(root)
    _write_agent_memory_import_state(state_path, signature=signature, result=result)
    return result


def agent_memory_status(repo_root: str | Path) -> AgentMemoryStatus:
    root = resolve_repo_root(repo_root)
    candidates = _existing_agent_memory_files(root)
    imported_sources = _existing_agent_memory_sources(root)
    imported_paths = {
        source.split(":", 2)[2]
        for source in imported_sources
        if source.startswith("agent-memory:") and len(source.split(":", 2)) == 3
    }
    candidate_paths = tuple(relative_path for _, relative_path, _ in candidates)
    pending_paths = tuple(path for path in candidate_paths if path not in imported_paths)
    return AgentMemoryStatus(
        initialized=bool(imported_sources) or not candidate_paths,
        imported_sources=imported_sources,
        candidate_paths=candidate_paths,
        pending_paths=pending_paths,
        state_path=str(_agent_memory_import_state_path(root)),
    )


def _existing_agent_memory_sources(root: Path) -> tuple[str, ...]:
    db_path = root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return ()
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        rows = conn.execute(
            """
            SELECT source
            FROM memory_notes
            WHERE active = 1 AND topic = 'agent-memory' AND source LIKE 'agent-memory:%'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        return tuple(str(row["source"]) for row in rows)
    finally:
        conn.close()


def _active_memory_source_exists(root: Path, source: str) -> bool:
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        row = conn.execute(
            """
            SELECT 1
            FROM memory_notes
            WHERE active = 1 AND source = ?
            LIMIT 1
            """,
            (source,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


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


def _candidate_kind(line: str) -> str | None:
    lowered = line.lower()
    markers: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("decision", ("決定", "decision:", "decide ", "decided ")),
        ("constraint", ("以後", "規則", "不要", "必須", "不能", "must ", "should ", "do not ", "don't ")),
        ("workflow", ("流程", "步驟", "workflow", "run ", "使用 ", "use ")),
        ("test", ("測試", "pytest", "test command", "驗收")),
        ("failure", ("失敗", "failed because", "root cause", "原因")),
        ("open-question", ("待確認", "open question", "todo:", "follow up")),
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


def list_memory_notes(
    repo_root: str | Path,
    *,
    topic: str | None = None,
    limit: int = 100,
) -> tuple[MemoryNote, ...]:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return _memory_notes(conn, limit=limit, topic=topic)
    finally:
        conn.close()


def remove_memory_note(repo_root: str | Path, *, note_id: str) -> bool:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        with conn:
            cursor = conn.execute(
                """
                UPDATE memory_notes
                SET active = 0, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (utc_now(), note_id),
            )
        return cursor.rowcount > 0
    finally:
        conn.close()


def lint_memory_notes(
    repo_root: str | Path,
    *,
    fix: bool = False,
    max_chars: int = 6000,
) -> MemoryLintResult:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        notes = _all_active_memory_notes(conn)
        duplicate_ids = _duplicate_memory_note_ids(notes)
        issues: list[MemoryLintIssue] = []
        fixes: list[MemoryLintFix] = []
        for note in notes:
            detected = _lint_one_memory_note(conn, note, duplicate_ids=duplicate_ids, max_chars=max_chars)
            for issue in detected:
                fixed_issue = issue
                if fix and issue.fixable:
                    applied = _apply_memory_lint_fix(conn, note, issue, max_chars=max_chars)
                    if applied is not None:
                        fixes.append(applied)
                        fixed_issue = MemoryLintIssue(
                            code=issue.code,
                            severity=issue.severity,
                            note_id=issue.note_id,
                            source=issue.source,
                            topic=issue.topic,
                            detail=issue.detail,
                            fixable=issue.fixable,
                            fixed=True,
                        )
                issues.append(fixed_issue)
        return MemoryLintResult(checked=len(notes), issues=tuple(issues), fixes=tuple(fixes))
    finally:
        conn.close()


def memory_health_from_lint(result: MemoryLintResult) -> MemoryHealth:
    error_count = len([issue for issue in result.issues if issue.severity == "error"])
    warning_count = len([issue for issue in result.issues if issue.severity == "warning"])
    info_count = len([issue for issue in result.issues if issue.severity == "info"])
    if error_count:
        status = "error"
    elif warning_count:
        status = "warning"
    elif info_count:
        status = "info"
    else:
        status = "ok"
    return MemoryHealth(
        status=status,
        checked=result.checked,
        issue_count=len(result.issues),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def render_memory_lint_result(result: MemoryLintResult) -> str:
    lines = [
        "AIT memory lint",
        f"Checked: {result.checked}",
        f"Issues: {len(result.issues)}",
        f"Fixes: {len(result.fixes)}",
    ]
    if result.issues:
        lines.append("Issues:")
        for issue in result.issues:
            fixed = " fixed=true" if issue.fixed else ""
            lines.append(
                f"- {issue.severity} {issue.code} note={issue.note_id} "
                f"source={issue.source} fixable={issue.fixable}{fixed}: {issue.detail}"
            )
    if result.fixes:
        lines.append("Fixes:")
        for fix in result.fixes:
            lines.append(f"- {fix.action} note={fix.note_id}: {fix.detail}")
    return "\n".join(lines) + "\n"


def _agent_memory_import_state_path(root: Path) -> Path:
    return root / ".ait" / "memory" / "agent-import-state.json"


def _all_active_memory_notes(conn: sqlite3.Connection) -> tuple[MemoryNote, ...]:
    rows = conn.execute(
        """
        SELECT id, topic, body, source, created_at, updated_at
        FROM memory_notes
        WHERE active = 1
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    return tuple(
        MemoryNote(
            id=str(row["id"]),
            topic=str(row["topic"]) if row["topic"] is not None else None,
            body=str(row["body"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    )


def _duplicate_memory_note_ids(notes: tuple[MemoryNote, ...]) -> set[str]:
    seen: dict[tuple[str | None, str], str] = {}
    duplicates: set[str] = set()
    for note in notes:
        key = (note.topic, _normalized_memory_body(note.body))
        if key in seen:
            duplicates.add(note.id)
        else:
            seen[key] = note.id
    return duplicates


def _normalized_memory_body(body: str) -> str:
    return " ".join(body.split()).strip().lower()


def _lint_one_memory_note(
    conn: sqlite3.Connection,
    note: MemoryNote,
    *,
    duplicate_ids: set[str],
    max_chars: int,
) -> tuple[MemoryLintIssue, ...]:
    issues: list[MemoryLintIssue] = []
    redacted, redacted_changed = redact_text(note.body)
    if note.id in duplicate_ids:
        issues.append(_memory_lint_issue(note, "duplicate", "error", "body duplicates an earlier active note", True))
    if max_chars > 0 and len(note.body) > max_chars:
        issues.append(
            _memory_lint_issue(note, "too_long", "warning", f"body has {len(note.body)} chars over {max_chars}", True)
        )
    if redacted_changed and redacted != note.body:
        issues.append(_memory_lint_issue(note, "possible_secret", "error", "body matches a redaction pattern", True))
    if note.source.startswith(("agent-memory:", "attempt-memory:")) and "confidence=" not in note.body:
        issues.append(_memory_lint_issue(note, "missing_confidence", "warning", "managed memory lacks confidence=", False))
    if _low_information_memory_body(note.body):
        issues.append(_memory_lint_issue(note, "low_information", "info", "body is too short or repetitive", False))
    if note.source.startswith("attempt-memory:") and not _attempt_memory_source_exists(conn, note.source):
        issues.append(_memory_lint_issue(note, "stale_attempt_memory", "warning", "source attempt no longer exists", False))
    return tuple(issues)


def _memory_lint_issue(
    note: MemoryNote,
    code: str,
    severity: str,
    detail: str,
    fixable: bool,
) -> MemoryLintIssue:
    return MemoryLintIssue(
        code=code,
        severity=severity,
        note_id=note.id,
        source=note.source,
        topic=note.topic,
        detail=detail,
        fixable=fixable,
    )


def _low_information_memory_body(body: str) -> bool:
    terms = _terms(body)
    if len(body.strip()) < 20 or len(terms) < 3:
        return True
    if terms and max(terms.count(term) for term in set(terms)) / len(terms) > 0.8:
        return True
    return False


def _attempt_memory_source_exists(conn: sqlite3.Connection, source: str) -> bool:
    attempt_id = source.removeprefix("attempt-memory:")
    if not attempt_id:
        return False
    row = conn.execute("SELECT 1 FROM attempts WHERE id = ? LIMIT 1", (attempt_id,)).fetchone()
    return row is not None


def _apply_memory_lint_fix(
    conn: sqlite3.Connection,
    note: MemoryNote,
    issue: MemoryLintIssue,
    *,
    max_chars: int,
) -> MemoryLintFix | None:
    if issue.code == "duplicate":
        with conn:
            conn.execute(
                "UPDATE memory_notes SET active = 0, updated_at = ? WHERE id = ?",
                (utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="deactivate", detail="deactivated duplicate note")
    if issue.code == "possible_secret":
        redacted, _ = redact_text(note.body)
        with conn:
            conn.execute(
                "UPDATE memory_notes SET body = ?, updated_at = ? WHERE id = ?",
                (redacted, utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="redact", detail="redacted matching secret pattern")
    if issue.code == "too_long" and max_chars > 0:
        marker = "\n[ait memory lint compacted]\n"
        keep = max(0, max_chars - len(marker))
        compacted = note.body[:keep].rstrip() + marker
        with conn:
            conn.execute(
                "UPDATE memory_notes SET body = ?, updated_at = ? WHERE id = ?",
                (compacted, utc_now(), note.id),
            )
        return MemoryLintFix(note_id=note.id, action="compact", detail=f"compacted body to {len(compacted)} chars")
    return None


def _agent_memory_signature(root: Path) -> list[dict[str, object]]:
    signature: list[dict[str, object]] = []
    for source_name, relative_path, path in _existing_agent_memory_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append(
            {
                "source": source_name,
                "path": relative_path,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
        )
    return signature


def _existing_agent_memory_files(root: Path) -> tuple[tuple[str, str, Path], ...]:
    policy = load_memory_policy(root)
    files: list[tuple[str, str, Path]] = []
    seen: set[str] = set()
    candidates = _agent_memory_candidates(
        root,
        source_names=tuple(AGENT_MEMORY_CANDIDATES),
        paths=(),
    )
    for source_name, relative_path, path in candidates:
        if not path.exists():
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                child_relative = child.relative_to(root).as_posix()
                if child_relative in seen or path_excluded(child_relative, policy):
                    continue
                files.append((source_name, child_relative, child))
                seen.add(child_relative)
            continue
        if relative_path in seen or path_excluded(relative_path, policy):
            continue
        files.append((source_name, relative_path, path))
        seen.add(relative_path)
    return tuple(files)


def _read_agent_memory_import_state(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_agent_memory_import_state(
    path: Path,
    *,
    signature: list[dict[str, object]],
    result: MemoryImportResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "signature": signature,
                "last_result": result.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _agent_memory_candidates(
    root: Path,
    *,
    source_names: tuple[str, ...],
    paths: tuple[str, ...],
) -> tuple[tuple[str, str, Path], ...]:
    candidates: list[tuple[str, str, Path]] = []
    if paths:
        source_name = source_names[0] if len(source_names) == 1 else "custom"
        for raw_path in paths:
            path = Path(raw_path)
            resolved = path if path.is_absolute() else root / path
            relative = _relative_to_root(resolved, root)
            candidates.append((source_name, relative, resolved))
        return tuple(candidates)
    for source_name in source_names:
        for pattern in AGENT_MEMORY_CANDIDATES.get(source_name, ()):
            path = root / pattern
            candidates.append((source_name, pattern, path))
    return tuple(candidates)


def _import_one_agent_memory_file(
    root: Path,
    *,
    source_name: str,
    relative_path: str,
    path: Path,
    topic: str,
    max_chars: int,
    existing: set[str],
    imported: list[MemoryNote],
    skipped: list[dict[str, str]],
) -> None:
    if not _looks_like_memory_text_file(path):
        skipped.append({"path": relative_path, "source": source_name, "reason": "unsupported file type"})
        return
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        skipped.append({"path": relative_path, "source": source_name, "reason": str(exc)})
        return
    body = _agent_memory_note_body(
        source_name=source_name,
        relative_path=relative_path,
        text=raw,
        max_chars=max_chars,
    )
    if not body.strip():
        skipped.append({"path": relative_path, "source": source_name, "reason": "empty"})
        return
    if body in existing:
        skipped.append({"path": relative_path, "source": source_name, "reason": "already imported"})
        return
    note = add_memory_note(
        root,
        topic=topic,
        body=body,
        source=f"agent-memory:{source_name}:{relative_path}",
    )
    existing.add(body)
    imported.append(note)


def _agent_memory_note_body(
    *,
    source_name: str,
    relative_path: str,
    text: str,
    max_chars: int,
) -> str:
    redacted, _ = redact_text(text)
    compacted = redacted.strip()
    if max_chars > 0 and len(compacted) > max_chars:
        compacted = compacted[:max_chars].rstrip() + "\n[ait memory import compacted]"
    if not compacted:
        return ""
    return (
        f"Imported agent memory\n"
        f"source={source_name}\n"
        f"path={relative_path}\n"
        f"confidence=advisory\n\n"
        f"{compacted}"
    )


def _existing_import_bodies(repo_root: Path) -> set[str]:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        rows = conn.execute(
            """
            SELECT body
            FROM memory_notes
            WHERE active = 1 AND source LIKE 'agent-memory:%'
            """
        ).fetchall()
        return {str(row["body"]) for row in rows}
    finally:
        conn.close()


def _looks_like_memory_text_file(path: Path) -> bool:
    if path.name in {"AGENTS.md", "CLAUDE.md", ".cursorrules"}:
        return True
    return path.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def search_repo_memory(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 8,
    ranker: str = "vector",
    policy: MemoryPolicy | None = None,
) -> tuple[MemorySearchResult, ...]:
    root = resolve_repo_root(repo_root)
    resolved_policy = policy or load_memory_policy(root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return search_repo_memory_with_connection(
            conn,
            query=query,
            limit=limit,
            ranker=ranker,
            repo_root=root,
            policy=resolved_policy,
        )
    finally:
        conn.close()


def search_repo_memory_with_connection(
    conn: sqlite3.Connection,
    *,
    query: str,
    limit: int = 8,
    ranker: str = "vector",
    repo_root: str | Path | None = None,
    policy: MemoryPolicy | None = None,
) -> tuple[MemorySearchResult, ...]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return ()
    documents = _search_documents(
        conn,
        repo_root=Path(repo_root).resolve() if repo_root else Path.cwd(),
        policy=policy or default_memory_policy(),
    )
    literal_results = _score_documents_literal(documents, normalized_query)
    if ranker == "vector":
        query_terms = _terms(query)
        if not query_terms:
            results = literal_results
            results.sort(key=lambda result: (-result.score, result.kind, result.id))
            return tuple(results[:limit])
        results = _score_documents_vector(documents, query_terms)
        if _should_prefer_literal(query) or not results:
            results = _merge_search_results(literal_results, results)
    elif ranker == "lexical":
        query_terms = _terms(query)
        results = [
            result
            for result in (
                _score_document_lexical(document, query_terms)
                for document in documents
            )
            if result is not None
        ]
        if _should_prefer_literal(query) or not results:
            results = _merge_search_results(literal_results, results)
    else:
        raise ValueError("memory search ranker must be 'vector' or 'lexical'")
    results.sort(key=lambda result: (-result.score, result.kind, result.id))
    return tuple(results[:limit])


def render_memory_search_results(results: tuple[MemorySearchResult, ...]) -> str:
    if not results:
        return "No memory search results.\n"
    lines = ["AIT Memory Search Results"]
    for result in results:
        lines.append(
            f"- {result.kind} {result.id} score={result.score:.2f} title={result.title!r}"
        )
        if result.text:
            lines.append(f"  {result.text}")
        if result.metadata:
            fields = ", ".join(f"{key}={value}" for key, value in result.metadata.items())
            lines.append(f"  metadata: {fields}")
    return "\n".join(lines) + "\n"


def build_relevant_memory_recall(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 6,
    budget_chars: int = 4000,
    include_unhealthy: bool = False,
) -> RelevantMemoryRecall:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    candidates = search_repo_memory(root, query, limit=max(limit * 3, 12), policy=policy)
    blocked_notes = (
        _lint_note_codes_by_severity(root, severities=policy.recall_lint_block_severities)
        if not include_unhealthy
        else {}
    )
    selected: list[RelevantMemoryItem] = []
    skipped: list[dict[str, object]] = []
    for result in candidates:
        source = str(result.metadata.get("source", ""))
        if result.kind != "note":
            skipped.append({"kind": result.kind, "id": result.id, "reason": "not a memory note"})
            continue
        if recall_source_blocked(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source blocked by memory policy",
                }
            )
            continue
        if not recall_source_allowed(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source not allowed by memory policy",
                }
            )
            continue
        if result.id in blocked_notes:
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "lint issue",
                    "lint_codes": blocked_notes[result.id],
                }
            )
            continue
        if len(selected) >= limit:
            skipped.append({"kind": result.kind, "id": result.id, "source": source, "reason": "over selection limit"})
            continue
        selected.append(
            RelevantMemoryItem(
                kind=result.kind,
                id=result.id,
                source=source,
                topic=result.title,
                score=result.score,
                text=result.text,
                metadata=result.metadata,
            )
        )

    rendered, compacted = _render_relevant_memory_text(
        query=query,
        selected=tuple(selected),
        budget_chars=budget_chars,
    )
    return RelevantMemoryRecall(
        query=query,
        selected=tuple(selected),
        skipped=tuple(skipped),
        budget_chars=budget_chars,
        rendered_chars=len(rendered),
        compacted=compacted,
    )


def _lint_note_codes_by_severity(
    repo_root: str | Path,
    *,
    severities: tuple[str, ...],
) -> dict[str, list[str]]:
    if not severities:
        return {}
    blocked_severities = set(severities)
    result = lint_memory_notes(repo_root)
    blocked: dict[str, list[str]] = {}
    for issue in result.issues:
        if issue.severity not in blocked_severities:
            continue
        blocked.setdefault(issue.note_id, []).append(issue.code)
    return blocked


def render_relevant_memory_recall(recall: RelevantMemoryRecall) -> str:
    rendered, _ = _render_relevant_memory_text(
        query=recall.query,
        selected=recall.selected,
        budget_chars=recall.budget_chars,
    )
    return rendered


def _render_relevant_memory_text(
    *,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> tuple[str, bool]:
    lines = [
        "AIT Relevant Memory",
        f"Query: {query}",
        f"Selected: {len(selected)}",
        f"Budget chars: {budget_chars}",
        "",
    ]
    if not selected:
        lines.append("- none")
    for item in selected:
        text = " ".join(item.text.split())
        lines.append(f"- {item.source} score={item.score:.2f} topic={item.topic}")
        if text:
            lines.append(f"  {text[:800]}")
    text = "\n".join(lines) + "\n"
    if budget_chars <= 0 or len(text) <= budget_chars:
        return text, False
    marker = "\n[ait relevant memory compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker, True


def _recent_attempts(
    conn: sqlite3.Connection,
    *,
    limit: int,
    path_filter: str | None,
    promoted_only: bool,
    policy: MemoryPolicy,
) -> list[MemoryAttempt]:
    where = []
    params: list[object] = []
    if promoted_only:
        where.append("a.verified_status = 'promoted'")
    if path_filter:
        where.append(
            """
            EXISTS (
              SELECT 1
              FROM evidence_files AS ef
              WHERE ef.attempt_id = a.id
                AND ef.file_path LIKE ?
            )
            """
        )
        params.append(f"{path_filter}%")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
          a.id AS attempt_id,
          a.agent_id,
          a.verified_status,
          a.result_exit_code,
          a.raw_trace_ref,
          a.started_at,
          i.title AS intent_title,
          i.status AS intent_status
        FROM attempts AS a
        JOIN intents AS i ON i.id = a.intent_id
        {where_sql}
        ORDER BY a.started_at DESC, a.ordinal DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [
        MemoryAttempt(
            intent_title=str(row["intent_title"]),
            intent_status=str(row["intent_status"]),
            attempt_id=str(row["attempt_id"]),
            agent_id=str(row["agent_id"]),
            verified_status=str(row["verified_status"]),
            result_exit_code=row["result_exit_code"],
            started_at=str(row["started_at"]),
            changed_files=_changed_files(conn, str(row["attempt_id"]), policy=policy),
            commit_oids=_commit_oids(conn, str(row["attempt_id"])),
        )
        for row in rows
    ]


def _changed_files(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    policy: MemoryPolicy,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path
        FROM evidence_files
        WHERE attempt_id = ? AND kind = 'changed'
        ORDER BY file_path
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))


def _commit_oids(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT commit_oid
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["commit_oid"]) for row in rows)


def _hot_files(
    conn: sqlite3.Connection,
    *,
    limit: int,
    path_filter: str | None,
    policy: MemoryPolicy,
) -> tuple[str, ...]:
    where = "kind IN ('changed', 'touched')"
    params: list[object] = []
    if path_filter:
        where += " AND file_path LIKE ?"
        params.append(f"{path_filter}%")
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT file_path, COUNT(*) AS touch_count
        FROM evidence_files
        WHERE {where}
        GROUP BY file_path
        ORDER BY touch_count DESC, file_path ASC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))


def _memory_notes(
    conn: sqlite3.Connection,
    *,
    limit: int,
    topic: str | None,
) -> tuple[MemoryNote, ...]:
    where = "active = 1"
    params: list[object] = []
    if topic:
        where += " AND topic = ?"
        params.append(topic)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, topic, body, source, created_at, updated_at
        FROM memory_notes
        WHERE {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return tuple(
        MemoryNote(
            id=str(row["id"]),
            topic=str(row["topic"]) if row["topic"] is not None else None,
            body=str(row["body"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    )


def _search_documents(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    policy: MemoryPolicy,
) -> tuple[dict[str, object], ...]:
    documents: list[dict[str, object]] = []
    note_rows = conn.execute(
        """
        SELECT id, topic, body, source, updated_at
        FROM memory_notes
        WHERE active = 1
        """
    ).fetchall()
    for row in note_rows:
        topic = str(row["topic"]) if row["topic"] is not None else "general"
        body, redacted = redact_text(str(row["body"]))
        documents.append(
            {
                "kind": "note",
                "id": str(row["id"]),
                "title": topic,
                "text": body,
                "metadata": {
                    "topic": topic,
                    "source": str(row["source"]),
                    "updated_at": str(row["updated_at"]),
                    "redacted": redacted,
                },
            }
        )

    attempt_rows = conn.execute(
        """
        SELECT
          a.id AS attempt_id,
          a.agent_id,
          a.verified_status,
          a.result_exit_code,
          a.raw_trace_ref,
          a.started_at,
          i.title AS intent_title,
          i.description AS intent_description,
          i.kind AS intent_kind
        FROM attempts AS a
        JOIN intents AS i ON i.id = a.intent_id
        """
    ).fetchall()
    for row in attempt_rows:
        attempt_id = str(row["attempt_id"])
        changed_files = _changed_files(conn, attempt_id, policy=policy)
        commits = _commit_oids(conn, attempt_id)
        raw_trace_ref = str(row["raw_trace_ref"] or "")
        trace_text = _read_trace_text(raw_trace_ref, repo_root=repo_root)
        if _trace_excluded(trace_text, policy=policy):
            trace_text = EXCLUDED_MARKER
        trace_redacted = has_redactions(trace_text)
        text_parts = [
            str(row["intent_title"]),
            str(row["intent_description"] or ""),
            str(row["intent_kind"] or ""),
            str(row["agent_id"]),
            str(row["verified_status"]),
            " ".join(changed_files),
            " ".join(commits),
            trace_text,
        ]
        documents.append(
            {
                "kind": "attempt",
                "id": attempt_id,
                "title": str(row["intent_title"]),
                "text": " ".join(part for part in text_parts if part),
                "metadata": {
                    "agent_id": str(row["agent_id"]),
                    "verified_status": str(row["verified_status"]),
                    "result_exit_code": row["result_exit_code"],
                    "started_at": str(row["started_at"]),
                    "raw_trace_ref": raw_trace_ref,
                    "redacted": trace_redacted,
                    "changed_files": list(changed_files),
                    "commit_oids": list(commits),
                },
            }
        )
    return tuple(documents)


def _trace_excluded(trace_text: str, *, policy: MemoryPolicy) -> bool:
    return (
        "Excluded-By-Memory-Policy: true" in trace_text
        or EXCLUDED_MARKER in trace_text
        or transcript_excluded(trace_text, policy)
    )


def _read_trace_text(raw_trace_ref: str, *, repo_root: Path, limit: int = 4000) -> str:
    if not raw_trace_ref:
        return ""
    path = _normalized_trace_path(raw_trace_ref, repo_root=repo_root)
    if path is None:
        path = Path(raw_trace_ref)
        if not path.is_absolute():
            path = repo_root / path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _normalized_trace_path(raw_trace_ref: str, *, repo_root: Path) -> Path | None:
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = repo_root / path
    normalized_path = path.parent / "normalized" / path.name
    return normalized_path if normalized_path.exists() else None


def _score_documents_vector(
    documents: tuple[dict[str, object], ...],
    query_terms: tuple[str, ...],
) -> list[MemorySearchResult]:
    document_terms = [_terms(str(document["title"]) + " " + str(document["text"])) for document in documents]
    if not document_terms:
        return []
    doc_count = len(document_terms)
    document_frequency: dict[str, int] = {}
    for terms in document_terms:
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    query_vector = _tfidf_vector(query_terms, document_frequency, doc_count)
    query_norm = _vector_norm(query_vector)
    if query_norm == 0:
        return []

    results: list[MemorySearchResult] = []
    for document, terms in zip(documents, document_terms, strict=True):
        vector = _tfidf_vector(terms, document_frequency, doc_count)
        norm = _vector_norm(vector)
        if norm == 0:
            continue
        score = _dot(query_vector, vector) / (query_norm * norm)
        if score <= 0:
            continue
        results.append(_search_result(document, score, "vector"))
    return results


def _score_document_lexical(
    document: dict[str, object],
    query_terms: tuple[str, ...],
) -> MemorySearchResult | None:
    title = str(document["title"])
    text = str(document["text"])
    haystack_terms = _terms(title + " " + text)
    if not haystack_terms:
        return None
    term_counts = {term: haystack_terms.count(term) for term in set(haystack_terms)}
    score = 0.0
    for term in query_terms:
        count = term_counts.get(term, 0)
        if count:
            score += 2.0 + count
        elif any(candidate.startswith(term) or term.startswith(candidate) for candidate in term_counts):
            score += 0.75
    if score <= 0:
        return None
    return _search_result(document, score, "lexical")


def _score_documents_literal(
    documents: tuple[dict[str, object], ...],
    normalized_query: str,
) -> list[MemorySearchResult]:
    results: list[MemorySearchResult] = []
    for document in documents:
        title = str(document["title"])
        text = str(document["text"])
        haystack = f"{title} {text}"
        normalized_haystack = _normalize_search_text(haystack)
        match_start = normalized_haystack.find(normalized_query)
        if match_start < 0:
            continue
        score = 10.0 + min(5.0, len(normalized_query) / 8.0)
        result = _search_result(document, score, "literal")
        metadata = dict(result.metadata)
        metadata["match_start"] = match_start
        metadata["match_end"] = match_start + len(normalized_query)
        metadata["snippet"] = _literal_snippet(haystack, normalized_query)
        results.append(
            MemorySearchResult(
                kind=result.kind,
                id=result.id,
                score=result.score,
                title=result.title,
                text=result.text,
                metadata=metadata,
            )
        )
    return results


def _merge_search_results(
    primary: list[MemorySearchResult],
    secondary: list[MemorySearchResult],
) -> list[MemorySearchResult]:
    merged: dict[tuple[str, str], MemorySearchResult] = {}
    for result in secondary:
        merged[(result.kind, result.id)] = result
    for result in primary:
        merged[(result.kind, result.id)] = result
    return list(merged.values())


def _search_result(document: dict[str, object], score: float, ranker: str) -> MemorySearchResult:
    metadata = dict(document["metadata"])
    metadata["ranker"] = ranker
    return MemorySearchResult(
        kind=str(document["kind"]),
        id=str(document["id"]),
        score=score,
        title=str(document["title"]),
        text=_compact_line(str(document["text"])),
        metadata=metadata,
    )


def _tfidf_vector(
    terms: tuple[str, ...],
    document_frequency: dict[str, int],
    doc_count: int,
) -> dict[str, float]:
    counts = {term: terms.count(term) for term in set(terms)}
    vector: dict[str, float] = {}
    for term, count in counts.items():
        df = document_frequency.get(term, 0)
        if df == 0:
            continue
        vector[term] = (1.0 + math.log(count)) * (math.log((1 + doc_count) / (1 + df)) + 1.0)
    return vector


def _vector_norm(vector: dict[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def _terms(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9_./:-]+", text.lower()))


def _normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\u3040" <= char <= "\u30ff"
        or "\uac00" <= char <= "\ud7af"
        for char in text
    )


def _should_prefer_literal(query: str) -> bool:
    normalized = _normalize_search_text(query)
    return _contains_cjk(normalized)


def _literal_snippet(text: str, normalized_query: str, *, radius: int = 80) -> str:
    normalized_text = _normalize_search_text(text)
    match_start = normalized_text.find(normalized_query)
    if match_start < 0:
        return _compact_line(text)
    start = max(0, match_start - radius)
    end = min(len(normalized_text), match_start + len(normalized_query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(normalized_text) else ""
    return prefix + normalized_text[start:end] + suffix


def _compact_line(text: str, *, limit: int = 180) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."


def _recommendations(
    attempts: tuple[MemoryAttempt, ...],
    hot_files: tuple[str, ...],
    notes: tuple[MemoryNote, ...],
) -> tuple[str, ...]:
    items: list[str] = [
        "treat this as external memory; verify current files before editing",
        "prefer continuing from promoted or succeeded attempts over failed attempts",
    ]
    failed = next((attempt for attempt in attempts if attempt.verified_status == "failed"), None)
    if failed is not None:
        items.append(f"review latest failed attempt before repeating work: {failed.attempt_id}")
    if hot_files:
        items.append(f"inspect frequently changed files first: {', '.join(hot_files[:5])}")
    if notes:
        items.append("apply curated notes as stable project guidance unless current files disagree")
    return tuple(items)
