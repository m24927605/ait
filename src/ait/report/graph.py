from __future__ import annotations



from dataclasses import asdict

import json

from pathlib import Path

import sqlite3



from ait.db import connect_db, list_memory_retrieval_events, utc_now

from ait.memory.eval import evaluate_memory_retrieval_event_records

from ait.memory_policy import load_memory_policy

from ait.repo import resolve_repo_root

from ait.report.shared import _short_id

def build_work_graph(
    repo_root: str | Path,
    *,
    limit: int = 20,
    agent: str | None = None,
    status: str | None = None,
    file_path: str | None = None,
) -> dict[str, object]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    filters = {
        "agent": agent,
        "status": status,
        "file": file_path,
    }
    root = resolve_repo_root(repo_root)
    db_path = root / ".ait" / "state.sqlite3"
    graph: dict[str, object] = {
        "repo_root": str(root),
        "state_path": str(db_path),
        "generated_at": utc_now(),
        "initialized": db_path.exists(),
        "report_status": _read_report_status(root),
        "intent_count": 0,
        "attempt_count": 0,
        "memory_note_count": 0,
        "memory_topics": {},
        "filters": {key: value for key, value in filters.items() if value},
        "intents": [],
    }
    if not db_path.exists():
        return graph

    conn = connect_db(db_path)
    try:
        policy = load_memory_policy(root)
        intents = _query_intents(conn, limit=limit)
        filtered_intents: list[dict[str, object]] = []
        for intent in intents:
            attempts = _query_attempts(conn, str(intent["id"]), repo_root=root)
            for attempt in attempts:
                attempt["files"] = _query_files(conn, str(attempt["id"]))
                attempt["commits"] = _query_commits(conn, str(attempt["id"]))
                attempt["memory_notes"] = _query_attempt_memory_notes(conn, str(attempt["id"]))
                attempt["memory_facts"] = _query_attempt_memory_facts(conn, str(attempt["id"]))
                attempt["memory_retrievals"] = _query_attempt_memory_retrievals(conn, str(attempt["id"]))
                attempt["memory_eval"] = _query_attempt_memory_eval(conn, str(attempt["id"]), policy=policy)
            attempts = [
                attempt
                for attempt in attempts
                if _attempt_matches(attempt, agent=agent, status=status, file_path=file_path)
            ]
            if filters["agent"] or filters["status"] or filters["file"]:
                if not attempts:
                    continue
            intent["attempts"] = attempts
            filtered_intents.append(intent)
        summary = _build_summary(filtered_intents)
        memory_topics = _query_memory_topics(conn)
        graph.update(
            {
                "intent_count": _count_rows(conn, "intents"),
                "attempt_count": _count_rows(conn, "attempts"),
                "matched_intent_count": len(filtered_intents),
                "matched_attempt_count": sum(
                    len([item for item in intent.get("attempts", []) if isinstance(item, dict)])
                    for intent in filtered_intents
                ),
                "memory_note_count": sum(memory_topics.values()),
                "memory_topics": memory_topics,
                "summary": summary,
                "intents": filtered_intents,
            }
        )
    finally:
        conn.close()
    return graph

def _read_report_status(repo_root: Path) -> dict[str, object]:
    status_path = repo_root / ".ait" / "report" / "status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def _build_summary(intents: list[dict[str, object]]) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    file_counts: dict[str, int] = {}
    for intent in intents:
        for attempt in [item for item in intent.get("attempts", []) if isinstance(item, dict)]:
            status = str(attempt.get("verified_status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
            outcome = str(attempt.get("outcome_class") or "unclassified")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            agent = str(attempt.get("agent_id", "unknown"))
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
            files = attempt.get("files", {})
            if not isinstance(files, dict):
                continue
            for file_path in files.get("changed", []) or files.get("touched", []):
                path = str(file_path)
                file_counts[path] = file_counts.get(path, 0) + 1
    hot_files = [
        {"path": path, "count": count}
        for path, count in sorted(file_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "agent_counts": dict(sorted(agent_counts.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "hot_files": hot_files,
    }

def _attempt_matches(
    attempt: dict[str, object],
    *,
    agent: str | None,
    status: str | None,
    file_path: str | None,
) -> bool:
    if agent and agent not in str(attempt.get("agent_id", "")):
        return False
    if status:
        statuses = {
            str(attempt.get("verified_status", "")),
            str(attempt.get("reported_status", "")),
            str(attempt.get("outcome_class", "")),
        }
        if status not in statuses:
            return False
    if file_path:
        files = attempt.get("files", {})
        if not isinstance(files, dict):
            return False
        all_files = [
            str(path)
            for paths in files.values()
            if isinstance(paths, list)
            for path in paths
        ]
        if not any(file_path in path for path in all_files):
            return False
    return True

def _query_intents(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, title, kind, status, created_at
        FROM intents
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "short_id": _short_id(str(row["id"])),
            "title": str(row["title"]),
            "kind": row["kind"],
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]

def _query_attempts(conn: sqlite3.Connection, intent_id: str, *, repo_root: Path) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.ordinal,
            a.agent_id,
            a.started_at,
            a.ended_at,
            a.reported_status,
            a.verified_status,
            a.raw_trace_ref,
            o.outcome_class,
            o.confidence AS outcome_confidence,
            o.reasons_json AS outcome_reasons_json
        FROM attempts a
        LEFT JOIN attempt_outcomes o ON o.attempt_id = a.id
        WHERE a.intent_id = ?
        ORDER BY a.ordinal ASC
        """,
        (intent_id,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "short_id": _short_id(str(row["id"])),
            "ordinal": int(row["ordinal"]),
            "agent_id": str(row["agent_id"]),
            "started_at": str(row["started_at"]),
            "ended_at": row["ended_at"],
            "reported_status": str(row["reported_status"]),
            "verified_status": str(row["verified_status"]),
            "outcome_class": str(row["outcome_class"] or ""),
            "outcome_confidence": str(row["outcome_confidence"] or ""),
            "outcome_reasons_json": str(row["outcome_reasons_json"] or "[]"),
            "raw_trace_ref": str(row["raw_trace_ref"] or ""),
            **_read_display_transcript(str(row["raw_trace_ref"] or ""), repo_root=repo_root),
        }
        for row in rows
    ]

def _read_display_transcript(raw_trace_ref: str, *, repo_root: Path, limit: int = 20000) -> dict[str, str]:
    if not raw_trace_ref:
        return {"transcript": "", "transcript_mode": "none"}
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = repo_root / path
    normalized_path = path.parent / "normalized" / path.name
    mode = "normalized" if normalized_path.exists() else "raw"
    if normalized_path.exists():
        path = normalized_path
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"transcript": "", "transcript_mode": "missing"}
    if len(text) <= limit:
        return {"transcript": text, "transcript_mode": mode}
    return {
        "transcript": text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]",
        "transcript_mode": mode,
    }

def _query_files(conn: sqlite3.Connection, attempt_id: str) -> dict[str, list[str]]:
    rows = conn.execute(
        """
        SELECT kind, file_path
        FROM evidence_files
        WHERE attempt_id = ?
        ORDER BY kind, file_path
        """,
        (attempt_id,),
    ).fetchall()
    files: dict[str, list[str]] = {}
    for row in rows:
        files.setdefault(str(row["kind"]), []).append(str(row["file_path"]))
    return files

def _query_commits(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT commit_oid, insertions, deletions, touched_files_json
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return [
        {
            "commit_oid": str(row["commit_oid"]),
            "insertions": row["insertions"],
            "deletions": row["deletions"],
            "touched_files": row["touched_files_json"],
        }
        for row in rows
    ]

def _query_attempt_memory_notes(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, object]]:
    sources = (
        f"durable-memory:{attempt_id}",
        f"memory-candidate:{attempt_id}",
    )
    rows = conn.execute(
        """
        SELECT id, topic, source, body, created_at, updated_at
        FROM memory_notes
        WHERE active = 1
          AND source IN (?, ?)
        ORDER BY updated_at DESC, id ASC
        """,
        sources,
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "topic": str(row["topic"] or ""),
            "source": str(row["source"]),
            "body": str(row["body"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]

def _query_attempt_memory_facts(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            id, kind, topic, body, summary, status, confidence,
            source_trace_ref, source_commit_oid, source_file_path,
            valid_from, valid_to, superseded_by, updated_at
        FROM memory_facts
        WHERE source_attempt_id = ?
        ORDER BY updated_at DESC, id ASC
        """,
        (attempt_id,),
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "topic": str(row["topic"]),
            "body": str(row["body"]),
            "summary": str(row["summary"]),
            "status": str(row["status"]),
            "confidence": str(row["confidence"]),
            "source_trace_ref": str(row["source_trace_ref"] or ""),
            "source_commit_oid": str(row["source_commit_oid"] or ""),
            "source_file_path": str(row["source_file_path"] or ""),
            "valid_from": str(row["valid_from"]),
            "valid_to": str(row["valid_to"] or ""),
            "superseded_by": str(row["superseded_by"] or ""),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]

def _query_attempt_memory_retrievals(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, query, selected_fact_ids_json, ranker_version, budget_chars, created_at
        FROM memory_retrieval_events
        WHERE attempt_id = ?
        ORDER BY created_at DESC, id ASC
        """,
        (attempt_id,),
    ).fetchall()
    retrievals: list[dict[str, object]] = []
    for row in rows:
        fact_ids = _json_string_list(str(row["selected_fact_ids_json"] or "[]"))
        retrievals.append(
            {
                "id": str(row["id"]),
                "query": str(row["query"]),
                "selected_fact_ids": fact_ids,
                "selected_facts": _query_memory_facts_by_ids(conn, fact_ids),
                "ranker_version": str(row["ranker_version"]),
                "budget_chars": int(row["budget_chars"]),
                "created_at": str(row["created_at"]),
            }
        )
    return retrievals

def _query_attempt_memory_eval(conn: sqlite3.Connection, attempt_id: str, *, policy) -> dict[str, object]:
    events = list_memory_retrieval_events(conn, attempt_id=attempt_id, limit=10000)
    eval_events = evaluate_memory_retrieval_event_records(conn, events, policy=policy)
    if not eval_events:
        return {
            "status": "pass",
            "event_count": 0,
            "average_score": 100,
            "events": [],
        }
    status = "fail" if any(event.status == "fail" for event in eval_events) else (
        "warn" if any(event.status == "warn" for event in eval_events) else "pass"
    )
    return {
        "status": status,
        "event_count": len(eval_events),
        "average_score": round(sum(event.score for event in eval_events) / len(eval_events)),
        "events": [
            {
                **asdict(event),
                "selected_fact_ids": list(event.selected_fact_ids),
                "missing_relevant_fact_ids": list(event.missing_relevant_fact_ids),
                "issues": list(event.issues),
                "warnings": list(event.warnings),
                "selected_facts": [asdict(fact) for fact in event.selected_facts],
            }
            for event in eval_events
        ],
    }

def _query_memory_facts_by_ids(conn: sqlite3.Connection, fact_ids: tuple[str, ...]) -> list[dict[str, object]]:
    if not fact_ids:
        return []
    placeholders = ",".join("?" for _ in fact_ids)
    rows = conn.execute(
        f"""
        SELECT id, kind, topic, body, summary, status, confidence
        FROM memory_facts
        WHERE id IN ({placeholders})
        """,
        fact_ids,
    ).fetchall()
    facts = {
        str(row["id"]): {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "topic": str(row["topic"]),
            "body": str(row["body"]),
            "summary": str(row["summary"]),
            "status": str(row["status"]),
            "confidence": str(row["confidence"]),
        }
        for row in rows
    }
    return [facts[fact_id] for fact_id in fact_ids if fact_id in facts]

def _json_string_list(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)

def _query_memory_topics(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT COALESCE(topic, 'general') AS topic, COUNT(*) AS count
        FROM memory_notes
        WHERE active = 1
        GROUP BY COALESCE(topic, 'general')
        ORDER BY topic
        """
    ).fetchall()
    return {str(row["topic"]): int(row["count"]) for row in rows}

def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])



__all__ = ["build_work_graph"]
