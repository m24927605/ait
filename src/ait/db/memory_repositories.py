from __future__ import annotations



import json

import sqlite3



from ait.db.records import (

    MemoryFactEdgeRecord,

    MemoryFactEntityRecord,

    MemoryFactRecord,

    MemoryRetrievalEventRecord,

    NewMemoryFact,

    NewMemoryFactEdge,

    NewMemoryRetrievalEvent,

)

from ait.db.schema import SCHEMA_VERSION



def upsert_memory_fact(conn: sqlite3.Connection, fact: NewMemoryFact) -> MemoryFactRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO memory_facts(
                id, schema_version, kind, topic, body, summary, status,
                confidence, source_attempt_id, source_trace_ref,
                source_commit_oid, source_file_path, valid_from, valid_to,
                superseded_by, created_at, updated_at, human_review_state,
                provenance
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                schema_version = excluded.schema_version,
                kind = excluded.kind,
                topic = excluded.topic,
                body = excluded.body,
                summary = excluded.summary,
                status = excluded.status,
                confidence = excluded.confidence,
                source_attempt_id = excluded.source_attempt_id,
                source_trace_ref = excluded.source_trace_ref,
                source_commit_oid = excluded.source_commit_oid,
                source_file_path = excluded.source_file_path,
                valid_from = excluded.valid_from,
                valid_to = excluded.valid_to,
                superseded_by = excluded.superseded_by,
                human_review_state = excluded.human_review_state,
                provenance = excluded.provenance,
                updated_at = excluded.updated_at
            """,
            (
                fact.id,
                SCHEMA_VERSION,
                fact.kind,
                fact.topic,
                fact.body,
                fact.summary,
                fact.status,
                fact.confidence,
                fact.source_attempt_id,
                fact.source_trace_ref,
                fact.source_commit_oid,
                fact.source_file_path,
                fact.valid_from,
                fact.valid_to,
                fact.superseded_by,
                fact.created_at,
                fact.updated_at,
                fact.human_review_state,
                fact.provenance,
            ),
        )
    row = get_memory_fact(conn, fact.id)
    if row is None:
        raise LookupError(f"memory fact not found after upsert: {fact.id}")
    return row

def get_memory_fact(conn: sqlite3.Connection, fact_id: str) -> MemoryFactRecord | None:
    row = conn.execute(
        "SELECT * FROM memory_facts WHERE id = ?",
        (fact_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_memory_fact(row)

def list_memory_facts(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    kind: str | None = None,
    topic: str | None = None,
    source_attempt_id: str | None = None,
    include_superseded: bool = False,
    limit: int = 100,
) -> list[MemoryFactRecord]:
    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    elif not include_superseded:
        clauses.append("status != 'superseded'")
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if topic is not None:
        clauses.append("topic = ?")
        params.append(topic)
    if source_attempt_id is not None:
        clauses.append("source_attempt_id = ?")
        params.append(source_attempt_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_facts
        {where}
        ORDER BY updated_at DESC, id ASC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [_row_to_memory_fact(row) for row in rows]

def replace_memory_fact_entities(
    conn: sqlite3.Connection,
    *,
    memory_fact_id: str,
    entities: tuple[MemoryFactEntityRecord, ...],
) -> None:
    with conn:
        conn.execute(
            "DELETE FROM memory_fact_entities WHERE memory_fact_id = ?",
            (memory_fact_id,),
        )
        for entity in entities:
            conn.execute(
                """
                INSERT INTO memory_fact_entities(memory_fact_id, entity, entity_type, weight)
                VALUES (?, ?, ?, ?)
                """,
                (
                    memory_fact_id,
                    entity.entity,
                    entity.entity_type,
                    entity.weight,
                ),
            )

def list_memory_fact_entities(
    conn: sqlite3.Connection,
    memory_fact_id: str,
) -> list[MemoryFactEntityRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM memory_fact_entities
        WHERE memory_fact_id = ?
        ORDER BY entity_type, entity
        """,
        (memory_fact_id,),
    ).fetchall()
    return [_row_to_memory_fact_entity(row) for row in rows]

def insert_memory_fact_edge(
    conn: sqlite3.Connection,
    edge: NewMemoryFactEdge,
) -> MemoryFactEdgeRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO memory_fact_edges(
                id, source_fact_id, target_fact_id, edge_type, confidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                edge.id,
                edge.source_fact_id,
                edge.target_fact_id,
                edge.edge_type,
                edge.confidence,
                edge.created_at,
            ),
        )
    row = get_memory_fact_edge(conn, edge.id)
    if row is None:
        raise LookupError(f"memory fact edge not found after insert: {edge.id}")
    return row

def get_memory_fact_edge(conn: sqlite3.Connection, edge_id: str) -> MemoryFactEdgeRecord | None:
    row = conn.execute(
        "SELECT * FROM memory_fact_edges WHERE id = ?",
        (edge_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_memory_fact_edge(row)

def list_memory_fact_edges(
    conn: sqlite3.Connection,
    *,
    source_fact_id: str | None = None,
    target_fact_id: str | None = None,
    edge_type: str | None = None,
) -> list[MemoryFactEdgeRecord]:
    clauses: list[str] = []
    params: list[object] = []
    if source_fact_id is not None:
        clauses.append("source_fact_id = ?")
        params.append(source_fact_id)
    if target_fact_id is not None:
        clauses.append("target_fact_id = ?")
        params.append(target_fact_id)
    if edge_type is not None:
        clauses.append("edge_type = ?")
        params.append(edge_type)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_fact_edges
        {where}
        ORDER BY created_at DESC, id ASC
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_memory_fact_edge(row) for row in rows]

def insert_memory_retrieval_event(
    conn: sqlite3.Connection,
    event: NewMemoryRetrievalEvent,
) -> MemoryRetrievalEventRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO memory_retrieval_events(
                id, attempt_id, query, selected_fact_ids_json,
                ranker_version, budget_chars, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.attempt_id,
                event.query,
                _json_dump(list(event.selected_fact_ids)),
                event.ranker_version,
                event.budget_chars,
                event.created_at,
            ),
        )
    row = get_memory_retrieval_event(conn, event.id)
    if row is None:
        raise LookupError(f"memory retrieval event not found after insert: {event.id}")
    return row

def get_memory_retrieval_event(
    conn: sqlite3.Connection,
    event_id: str,
) -> MemoryRetrievalEventRecord | None:
    row = conn.execute(
        "SELECT * FROM memory_retrieval_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_memory_retrieval_event(row)

def list_memory_retrieval_events(
    conn: sqlite3.Connection,
    *,
    attempt_id: str | None = None,
    limit: int | None = None,
) -> list[MemoryRetrievalEventRecord]:
    clauses: list[str] = []
    params: list[object] = []
    if attempt_id is not None:
        clauses.append("attempt_id = ?")
        params.append(attempt_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)
    rows = conn.execute(
        f"""
        SELECT *
        FROM memory_retrieval_events
        {where}
        ORDER BY created_at DESC, id ASC
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_memory_retrieval_event(row) for row in rows]

def _row_to_memory_fact(row: sqlite3.Row) -> MemoryFactRecord:
    return MemoryFactRecord(
        id=str(row["id"]),
        schema_version=int(row["schema_version"]),
        kind=str(row["kind"]),
        topic=str(row["topic"]),
        body=str(row["body"]),
        summary=str(row["summary"]),
        status=str(row["status"]),
        confidence=str(row["confidence"]),
        source_attempt_id=_str_or_none(row["source_attempt_id"]),
        source_trace_ref=_str_or_none(row["source_trace_ref"]),
        source_commit_oid=_str_or_none(row["source_commit_oid"]),
        source_file_path=_str_or_none(row["source_file_path"]),
        valid_from=str(row["valid_from"]),
        valid_to=_str_or_none(row["valid_to"]),
        superseded_by=_str_or_none(row["superseded_by"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        human_review_state=str(row["human_review_state"]),
        provenance=str(row["provenance"]),
    )

def _row_to_memory_fact_entity(row: sqlite3.Row) -> MemoryFactEntityRecord:
    return MemoryFactEntityRecord(
        memory_fact_id=str(row["memory_fact_id"]),
        entity=str(row["entity"]),
        entity_type=str(row["entity_type"]),
        weight=float(row["weight"]),
    )

def _row_to_memory_fact_edge(row: sqlite3.Row) -> MemoryFactEdgeRecord:
    return MemoryFactEdgeRecord(
        id=str(row["id"]),
        source_fact_id=str(row["source_fact_id"]),
        target_fact_id=str(row["target_fact_id"]),
        edge_type=str(row["edge_type"]),
        confidence=str(row["confidence"]),
        created_at=str(row["created_at"]),
    )

def _row_to_memory_retrieval_event(row: sqlite3.Row) -> MemoryRetrievalEventRecord:
    return MemoryRetrievalEventRecord(
        id=str(row["id"]),
        attempt_id=str(row["attempt_id"]),
        query=str(row["query"]),
        selected_fact_ids=tuple(str(item) for item in _json_load(row["selected_fact_ids_json"])),
        ranker_version=str(row["ranker_version"]),
        budget_chars=int(row["budget_chars"]),
        created_at=str(row["created_at"]),
    )

def _json_dump(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)

def _json_load(value: object) -> object:
    return json.loads(str(value))

def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)



__all__ = [

    "upsert_memory_fact",

    "get_memory_fact",

    "list_memory_facts",

    "replace_memory_fact_entities",

    "list_memory_fact_entities",

    "insert_memory_fact_edge",

    "get_memory_fact_edge",

    "list_memory_fact_edges",

    "insert_memory_retrieval_event",

    "get_memory_retrieval_event",

    "list_memory_retrieval_events",

]
