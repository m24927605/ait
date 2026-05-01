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

from .common import (
    _attempt_memory_note_advisory,
    _attempt_memory_note_field,
    _compact_line,
    _contains_cjk,
    _literal_snippet,
    _normalize_search_text,
    _normalized_trace_path,
    _read_trace_text,
    _should_prefer_literal,
    _terms,
    _trace_excluded,
)
from .lint import lint_memory_notes
from .repository import MemoryRepository, open_memory_repository
from .summary import _changed_files, _commit_oids

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
    with open_memory_repository(root) as repo:
        return search_repo_memory_with_connection(
            repo.conn,
            query=query,
            limit=limit,
            ranker=ranker,
            repo_root=root,
            policy=resolved_policy,
        )

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
    attempt_id: str | None = None,
) -> RelevantMemoryRecall:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    candidates = search_repo_memory(root, query, limit=max(limit * 3, 12), policy=policy)
    blocked_notes = (
        _lint_note_codes_by_severity(root, severities=policy.recall_lint_block_severities)
        if not include_unhealthy
        else {}
    )
    eligible: list[MemorySearchResult] = []
    skipped: list[dict[str, object]] = []
    for result in candidates:
        source = str(result.metadata.get("source", ""))
        if result.kind == "fact":
            status = str(result.metadata.get("status", ""))
            if status != "accepted":
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": f"memory fact status is {status}",
                    }
                )
                continue
            blocked_reason = _fact_recall_blocked_reason(result.metadata, policy)
            if blocked_reason:
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": blocked_reason,
                    }
                )
                continue
        elif result.kind != "note":
            skipped.append({"kind": result.kind, "id": result.id, "reason": "not a memory note"})
            continue
        if result.kind == "note" and recall_source_blocked(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source blocked by memory policy",
                }
            )
            continue
        if result.kind == "note" and not recall_source_allowed(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source not allowed by memory policy",
                }
            )
            continue
        if result.kind == "note" and result.id in blocked_notes:
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
        if result.kind == "note" and (
            _attempt_memory_note_advisory(source, result.text)
            or str(result.metadata.get("attempt_memory_confidence") or "") == "advisory"
            or str(result.metadata.get("attempt_memory_verified_status") or "")
            in {"failed", "failed_interrupted", "needs_review"}
        ):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "attempt memory is advisory",
                }
            )
            continue
        eligible.append(result)
    ranked = _apply_temporal_recall_ranking(_normalize_recall_ranker_scores(eligible))
    selected_results = ranked[:limit]
    for result in ranked[limit:]:
        skipped.append(
            {
                "kind": result.kind,
                "id": result.id,
                "source": str(result.metadata.get("source", "")),
                "reason": "over selection limit",
            }
        )
    selected = [
        RelevantMemoryItem(
            kind=result.kind,
            id=result.id,
            source=str(result.metadata.get("source", "")),
            topic=result.title,
            score=result.score,
            text=result.text,
            metadata=result.metadata,
        )
        for result in selected_results
    ]

    rendered, compacted = _render_relevant_memory_text(
        query=query,
        selected=tuple(selected),
        budget_chars=budget_chars,
    )
    if attempt_id:
        _record_memory_retrieval_event(
            root,
            attempt_id=attempt_id,
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

def _apply_temporal_recall_ranking(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
    now = _parse_memory_time(utc_now()) or datetime.now(tz=UTC)
    ranked = [_temporal_ranked_result(result, now=now) for result in results]
    ranked.sort(
        key=lambda result: (
            -float(result.metadata.get("temporal_score", result.score)),
            -result.score,
            result.kind,
            result.id,
        )
    )
    return ranked

def _normalize_recall_ranker_scores(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
    by_ranker: dict[str, list[MemorySearchResult]] = {}
    for result in results:
        by_ranker.setdefault(str(result.metadata.get("ranker") or "unknown"), []).append(result)

    normalized: list[MemorySearchResult] = []
    for ranker_results in by_ranker.values():
        scores = [result.score for result in ranker_results]
        minimum = min(scores)
        maximum = max(scores)
        for result in ranker_results:
            if maximum == minimum:
                score = 1.0
            else:
                score = (result.score - minimum) / (maximum - minimum)
            metadata = dict(result.metadata)
            metadata["ranker_raw_score"] = round(result.score, 6)
            metadata["ranker_normalized_score"] = round(score, 6)
            normalized.append(
                MemorySearchResult(
                    kind=result.kind,
                    id=result.id,
                    score=score,
                    title=result.title,
                    text=result.text,
                    metadata=metadata,
                )
            )
    return normalized

def _fact_recall_blocked_reason(metadata: dict[str, object], policy: MemoryPolicy) -> str:
    sources = tuple(
        str(metadata.get(key) or "")
        for key in ("source_file_path", "source_trace_ref")
        if metadata.get(key)
    )
    if any(recall_source_blocked(source, policy) for source in sources):
        return "fact source blocked by memory policy"
    if any(_looks_like_logical_source(source) and not recall_source_allowed(source, policy) for source in sources):
        return "fact source not allowed by memory policy"
    source_file_path = str(metadata.get("source_file_path") or "")
    if source_file_path and path_excluded(source_file_path, policy):
        return "fact source path excluded by memory policy"
    return ""

def _looks_like_logical_source(source: str) -> bool:
    if "/" in source or "\\" in source:
        return False
    return ":" in source

def _temporal_ranked_result(result: MemorySearchResult, *, now: datetime) -> MemorySearchResult:
    metadata = dict(result.metadata)
    temporal_kind = str(metadata.get("kind") or result.kind or "note")
    normalized_kind, unknown_kind = _normalize_temporal_kind(temporal_kind)
    anchor = _parse_memory_time(str(metadata.get("updated_at") or metadata.get("valid_from") or ""))
    age_days = (now - anchor).total_seconds() / 86400.0 if anchor else None
    if age_days is not None and age_days < 0:
        metadata["temporal_future_anchor"] = True
        age_days = None
    time_factor = _temporal_time_factor(normalized_kind, age_days)
    confidence_factor = _temporal_confidence_factor(str(metadata.get("confidence") or ""))
    kind_factor = _temporal_kind_factor(normalized_kind)
    temporal_score = result.score * time_factor * confidence_factor * kind_factor
    metadata.update(
        {
            "temporal_ranker": "temporal-v1",
            "temporal_kind": temporal_kind,
            "temporal_effective_kind": normalized_kind,
            "temporal_base_score": round(result.score, 6),
            "temporal_factor": round(time_factor * confidence_factor * kind_factor, 6),
            "temporal_score": round(temporal_score, 6),
        }
    )
    if unknown_kind:
        metadata["temporal_unknown_kind"] = True
    if age_days is not None:
        metadata["temporal_age_days"] = round(age_days, 3)
    return MemorySearchResult(
        kind=result.kind,
        id=result.id,
        score=temporal_score,
        title=result.title,
        text=result.text,
        metadata=metadata,
    )

def _temporal_time_factor(kind: str, age_days: float | None) -> float:
    if age_days is None:
        return 1.0
    half_life_days, minimum = {
        "current_state": (14.0, 0.35),
        "workflow": (45.0, 0.50),
        "failure": (45.0, 0.45),
        "entity": (60.0, 0.50),
        "rule": (90.0, 0.60),
        "decision": (180.0, 0.70),
        "manual": (365.0, 0.85),
        "note": (90.0, 0.55),
    }.get(kind, (90.0, 0.55))
    return minimum + (1.0 - minimum) * (0.5 ** (age_days / half_life_days))

def _temporal_confidence_factor(confidence: str) -> float:
    return {
        "manual": 1.08,
        "high": 1.05,
        "medium": 0.92,
        "low": 0.78,
    }.get(confidence, 0.90)

def _temporal_kind_factor(kind: str) -> float:
    return {
        "decision": 1.04,
        "rule": 1.03,
        "workflow": 1.02,
        "manual": 1.04,
        "current_state": 1.00,
        "entity": 0.96,
        "failure": 0.88,
    }.get(kind, 1.00)

def _normalize_temporal_kind(kind: str) -> tuple[str, bool]:
    known = {
        "current_state",
        "workflow",
        "failure",
        "entity",
        "rule",
        "decision",
        "manual",
        "note",
    }
    return (kind, False) if kind in known else ("note", True)

def _parse_memory_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

def _record_memory_retrieval_event(
    repo_root: Path,
    *,
    attempt_id: str,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> None:
    with open_memory_repository(repo_root) as repo:
        _record_memory_retrieval_event_with_repository(
            repo,
            attempt_id=attempt_id,
            query=query,
            selected=selected,
            budget_chars=budget_chars,
        )

def _record_memory_retrieval_event_with_repository(
    repo: MemoryRepository,
    *,
    attempt_id: str,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> None:
    selected_fact_ids = tuple(item.id for item in selected if item.kind == "fact")
    repo.insert_retrieval_event(
        NewMemoryRetrievalEvent(
            id=f"{attempt_id}:memory-retrieval:{uuid.uuid4().hex}",
            attempt_id=attempt_id,
            query=query,
            selected_fact_ids=selected_fact_ids,
            ranker_version="hybrid-v1",
            budget_chars=budget_chars,
            created_at=utc_now(),
        )
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

def _search_documents(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    policy: MemoryPolicy,
) -> tuple[dict[str, object], ...]:
    documents: list[dict[str, object]] = []
    fact_rows = conn.execute(
        """
        SELECT
            id, kind, topic, body, summary, status, confidence,
            source_attempt_id, source_trace_ref, source_commit_oid,
            source_file_path, valid_from, valid_to, superseded_by,
            human_review_state, provenance, updated_at
        FROM memory_facts
        WHERE status = 'accepted'
          AND superseded_by IS NULL
          AND (valid_to IS NULL OR valid_to > ?)
          AND NOT (confidence = 'high' AND human_review_state != 'approved')
        """,
        (utc_now(),),
    ).fetchall()
    for row in fact_rows:
        body, redacted = redact_text(str(row["body"]))
        summary, summary_redacted = redact_text(str(row["summary"]))
        source_attempt_id = str(row["source_attempt_id"] or "")
        source_trace_ref = str(row["source_trace_ref"] or "")
        source_commit_oid = str(row["source_commit_oid"] or "")
        source_file_path = str(row["source_file_path"] or "")
        source = f"memory-fact:{row['id']}"
        documents.append(
            {
                "kind": "fact",
                "id": str(row["id"]),
                "title": str(row["topic"]),
                "text": " ".join(
                    part
                    for part in (
                        str(row["kind"]),
                        str(row["topic"]),
                        summary,
                        body,
                        source_file_path,
                        source_commit_oid,
                    )
                    if part
                ),
                "metadata": {
                    "kind": str(row["kind"]),
                    "topic": str(row["topic"]),
                    "status": str(row["status"]),
                    "confidence": str(row["confidence"]),
                    "source": source,
                    "source_attempt_id": source_attempt_id,
                    "source_trace_ref": source_trace_ref,
                    "source_commit_oid": source_commit_oid,
                    "source_file_path": source_file_path,
                    "valid_from": str(row["valid_from"]),
                    "valid_to": str(row["valid_to"] or ""),
                    "superseded_by": str(row["superseded_by"] or ""),
                    "human_review_state": str(row["human_review_state"]),
                    "provenance": str(row["provenance"]),
                    "updated_at": str(row["updated_at"]),
                    "redacted": redacted or summary_redacted,
                },
            }
        )

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
                    "kind": "manual" if str(row["source"]) == "manual" or str(row["source"]).startswith("manual:") else "note",
                    "topic": topic,
                    "source": str(row["source"]),
                    "updated_at": str(row["updated_at"]),
                    "attempt_memory_confidence": _attempt_memory_note_field(body, "confidence"),
                    "attempt_memory_verified_status": _attempt_memory_note_field(body, "verified_status"),
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
        elif len(term) >= 3 and any(candidate.startswith(term) or term.startswith(candidate) for candidate in term_counts):
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
