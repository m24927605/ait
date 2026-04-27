from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from pathlib import Path
import re
import sqlite3
import uuid

from ait.db import connect_db, run_migrations, utc_now
from ait.memory_policy import (
    EXCLUDED_MARKER,
    MemoryPolicy,
    default_memory_policy,
    load_memory_policy,
    path_excluded,
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


def search_repo_memory(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 8,
    ranker: str = "vector",
) -> tuple[MemorySearchResult, ...]:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        return search_repo_memory_with_connection(
            conn,
            query=query,
            limit=limit,
            ranker=ranker,
            repo_root=root,
            policy=policy,
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
    query_terms = _terms(query)
    if not query_terms:
        return ()
    documents = _search_documents(
        conn,
        repo_root=Path(repo_root).resolve() if repo_root else Path.cwd(),
        policy=policy or default_memory_policy(),
    )
    if ranker == "vector":
        results = _score_documents_vector(documents, query_terms)
    elif ranker == "lexical":
        results = [
            result
            for result in (
                _score_document_lexical(document, query_terms)
                for document in documents
            )
            if result is not None
        ]
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
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


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
