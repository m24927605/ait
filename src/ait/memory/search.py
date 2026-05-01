from __future__ import annotations

import math
from pathlib import Path
import sqlite3

from ait.db import utc_now
from ait.memory_policy import (
    EXCLUDED_MARKER,
    MemoryPolicy,
    default_memory_policy,
    load_memory_policy,
)
from ait.redaction import has_redactions, redact_text
from ait.repo import resolve_repo_root

from .common import (
    _attempt_memory_note_field,
    _compact_line,
    _literal_snippet,
    _normalize_search_text,
    _read_trace_text,
    _should_prefer_literal,
    _terms,
    _trace_excluded,
)
from .models import MemorySearchResult
from .repository import open_memory_repository
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
