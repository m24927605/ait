from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import sqlite3
from pathlib import Path

from ait.db import (
    MemoryFactRecord,
    MemoryRetrievalEventRecord,
    connect_db,
    get_memory_fact,
    list_memory_fact_entities,
    list_memory_facts,
    list_memory_retrieval_events,
    run_migrations,
)
from ait.memory_policy import (
    MemoryPolicy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
)
from ait.repo import resolve_repo_root


@dataclass(frozen=True, slots=True)
class MemoryEvalFact:
    id: str
    kind: str
    topic: str
    summary: str
    status: str
    confidence: str
    relevance_score: int


@dataclass(frozen=True, slots=True)
class MemoryEvalEvent:
    event_id: str
    attempt_id: str
    query: str
    status: str
    score: int
    selected_count: int
    issue_count: int
    warning_count: int
    selected_fact_ids: tuple[str, ...]
    missing_relevant_fact_ids: tuple[str, ...]
    issues: tuple[str, ...]
    warnings: tuple[str, ...]
    selected_facts: tuple[MemoryEvalFact, ...]


@dataclass(frozen=True, slots=True)
class MemoryEvalReport:
    repo_root: str
    status: str
    event_count: int
    average_score: int
    events: tuple[MemoryEvalEvent, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "status": self.status,
            "event_count": self.event_count,
            "average_score": self.average_score,
            "events": [
                {
                    **asdict(event),
                    "selected_fact_ids": list(event.selected_fact_ids),
                    "missing_relevant_fact_ids": list(event.missing_relevant_fact_ids),
                    "issues": list(event.issues),
                    "warnings": list(event.warnings),
                    "selected_facts": [asdict(fact) for fact in event.selected_facts],
                }
                for event in self.events
            ],
        }


def evaluate_memory_retrievals(
    repo_root: str | Path,
    *,
    attempt_id: str | None = None,
    limit: int = 50,
) -> MemoryEvalReport:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    root = resolve_repo_root(repo_root)
    db_path = root / ".ait" / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        policy = load_memory_policy(root)
        events = list_memory_retrieval_events(conn, attempt_id=attempt_id, limit=limit)
        eval_events = evaluate_memory_retrieval_event_records(conn, events, policy=policy)
    finally:
        conn.close()
    if not eval_events:
        return MemoryEvalReport(
            repo_root=str(root),
            status="pass",
            event_count=0,
            average_score=100,
            events=(),
        )
    status = _aggregate_status(tuple(event.status for event in eval_events))
    average_score = round(sum(event.score for event in eval_events) / len(eval_events))
    return MemoryEvalReport(
        repo_root=str(root),
        status=status,
        event_count=len(eval_events),
        average_score=average_score,
        events=eval_events,
    )


def evaluate_memory_retrieval_event_records(
    conn: sqlite3.Connection,
    events: tuple[MemoryRetrievalEventRecord, ...] | list[MemoryRetrievalEventRecord],
    *,
    policy: MemoryPolicy,
) -> tuple[MemoryEvalEvent, ...]:
    return tuple(_evaluate_event(conn, event, policy=policy) for event in events)


def render_memory_eval_report(report: MemoryEvalReport) -> str:
    lines = [
        "AIT Memory Eval",
        f"Repo: {report.repo_root}",
        f"Events: {report.event_count}",
        f"Status: {report.status}",
        f"Average score: {report.average_score}",
        "",
    ]
    if not report.events:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for event in report.events:
        short_attempt = event.attempt_id.rsplit(":", 1)[-1][:8]
        lines.append(
            f"- event={event.event_id} attempt={short_attempt} "
            f"status={event.status} score={event.score} selected={event.selected_count}"
        )
        if event.query:
            lines.append(f"  query: {event.query}")
        if event.issues:
            lines.append("  issues:")
            for issue in event.issues:
                lines.append(f"  - {issue}")
        if event.warnings:
            lines.append("  warnings:")
            for warning in event.warnings:
                lines.append(f"  - {warning}")
        if event.selected_facts:
            lines.append("  selected:")
            for fact in event.selected_facts:
                lines.append(
                    f"  - {fact.id} {fact.kind}/{fact.topic} "
                    f"confidence={fact.confidence} status={fact.status} "
                    f"relevance={fact.relevance_score}"
                )
                lines.append(f"    {fact.summary}")
        if event.missing_relevant_fact_ids:
            lines.append("  missing relevant facts:")
            for fact_id in event.missing_relevant_fact_ids:
                lines.append(f"  - {fact_id}")
    return "\n".join(lines) + "\n"


def _evaluate_event(
    conn: sqlite3.Connection,
    event: MemoryRetrievalEventRecord,
    *,
    policy: MemoryPolicy,
) -> MemoryEvalEvent:
    selected_facts = tuple(
        fact
        for fact_id in event.selected_fact_ids
        for fact in (get_memory_fact(conn, fact_id),)
        if fact is not None
    )
    selected_by_id = {fact.id: fact for fact in selected_facts}
    relevance_scores = _relevance_scores(conn, query=event.query, as_of=event.created_at)
    likely_relevant_fact_ids = tuple(
        fact_id
        for fact_id, score in sorted(relevance_scores.items(), key=lambda item: (-item[1], item[0]))
        if score >= 4
    )
    missing_relevant_fact_ids = tuple(
        fact_id for fact_id in likely_relevant_fact_ids if fact_id not in event.selected_fact_ids
    )
    issues: list[str] = []
    warnings: list[str] = []
    penalty = 0

    for fact_id in event.selected_fact_ids:
        fact = selected_by_id.get(fact_id)
        if fact is None:
            issues.append(f"selected fact is missing: {fact_id}")
            penalty += 40
            continue
        if fact.status != "accepted":
            issues.append(f"selected fact is not accepted: {fact.id} status={fact.status}")
            penalty += 40
        if _fact_stale(fact, as_of=event.created_at):
            issues.append(f"selected fact is stale or superseded: {fact.id}")
            penalty += 40
        if _fact_policy_blocked(fact, policy):
            issues.append(f"selected fact is blocked by memory policy: {fact.id}")
            penalty += 40
        if fact.confidence != "high":
            warnings.append(f"selected fact confidence is not high: {fact.id} confidence={fact.confidence}")
            penalty += 15
        if not _fact_has_evidence(fact):
            warnings.append(f"selected fact has no trace, commit, or file evidence: {fact.id}")
            penalty += 10

    if not event.selected_fact_ids and likely_relevant_fact_ids:
        warnings.append(
            f"no facts selected but {len(likely_relevant_fact_ids)} likely relevant fact exists"
        )
        penalty += 15
    if missing_relevant_fact_ids:
        warnings.append(f"{len(missing_relevant_fact_ids)} likely relevant accepted fact was not selected")
        penalty += min(20, len(missing_relevant_fact_ids) * 5)

    score = max(0, min(100, 100 - penalty))
    status = "fail" if issues else "warn" if warnings or score < 85 else "pass"
    return MemoryEvalEvent(
        event_id=event.id,
        attempt_id=event.attempt_id,
        query=event.query,
        status=status,
        score=score,
        selected_count=len(event.selected_fact_ids),
        issue_count=len(issues),
        warning_count=len(warnings),
        selected_fact_ids=event.selected_fact_ids,
        missing_relevant_fact_ids=missing_relevant_fact_ids,
        issues=tuple(issues),
        warnings=tuple(warnings),
        selected_facts=tuple(
            MemoryEvalFact(
                id=fact.id,
                kind=fact.kind,
                topic=fact.topic,
                summary=fact.summary,
                status=fact.status,
                confidence=fact.confidence,
                relevance_score=relevance_scores.get(fact.id, 0),
            )
            for fact in selected_facts
        ),
    )


def _relevance_scores(conn: sqlite3.Connection, *, query: str, as_of: str) -> dict[str, int]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return {}
    scores: dict[str, int] = {}
    facts = list_memory_facts(conn, status="accepted", include_superseded=True, limit=10000)
    for fact in facts:
        if _fact_stale(fact, as_of=as_of):
            continue
        summary_tokens = _tokens(fact.summary)
        body_tokens = _tokens(fact.body)
        topic_tokens = _tokens(fact.topic)
        entity_tokens = set()
        for entity in list_memory_fact_entities(conn, fact.id):
            entity_tokens.update(_tokens(entity.entity))
        score = 0
        score += 3 * len(query_tokens & summary_tokens)
        score += 2 * len(query_tokens & body_tokens)
        score += 4 * len(query_tokens & entity_tokens)
        score += 1 * len(query_tokens & topic_tokens)
        if score:
            scores[fact.id] = score
    return scores


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[0-9A-Za-z_]+", text.casefold()) if len(token) >= 3}


def _fact_stale(fact: MemoryFactRecord, *, as_of: str) -> bool:
    if fact.status == "superseded" or fact.superseded_by:
        return True
    if fact.valid_to and fact.valid_to <= as_of:
        return True
    return False


def _fact_policy_blocked(fact: MemoryFactRecord, policy: MemoryPolicy) -> bool:
    sources = tuple(
        source
        for source in (fact.source_file_path, fact.source_trace_ref)
        if source
    )
    if any(recall_source_blocked(source, policy) for source in sources):
        return True
    if any(_looks_like_logical_source(source) and not recall_source_allowed(source, policy) for source in sources):
        return True
    if fact.source_file_path and path_excluded(fact.source_file_path, policy):
        return True
    return False


def _looks_like_logical_source(source: str) -> bool:
    if "/" in source or "\\" in source:
        return False
    return ":" in source


def _fact_has_evidence(fact: MemoryFactRecord) -> bool:
    return bool(fact.source_trace_ref or fact.source_commit_oid or fact.source_file_path)


def _aggregate_status(statuses: tuple[str, ...]) -> str:
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"
