from __future__ import annotations

import sqlite3

from ait.query.fields import lower_expression
from ait.query.models import QueryError, QueryPlan, QuerySubject
from ait.query.parser import parse_query


def compile_query(
    subject: QuerySubject,
    expression: str | None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> QueryPlan:
    if limit < 0:
        raise QueryError("limit must be >= 0")
    if offset < 0:
        raise QueryError("offset must be >= 0")

    if expression is None or not expression.strip():
        where_sql = "1=1"
        where_params: tuple[object, ...] = ()
    else:
        ast = parse_query(expression)
        where = lower_expression(subject, ast)
        where_sql = where.sql
        where_params = where.params

    if subject == "attempt":
        sql = (
            "SELECT DISTINCT a.* "
            "FROM attempts AS a "
            "JOIN intents AS i ON i.id = a.intent_id "
            "LEFT JOIN evidence_summaries AS es ON es.attempt_id = a.id "
            f"WHERE {where_sql} "
            "ORDER BY a.started_at DESC, a.id DESC "
            "LIMIT ? OFFSET ?"
        )
    else:
        sql = (
            "SELECT DISTINCT i.* "
            "FROM intents AS i "
            f"WHERE {where_sql} "
            "ORDER BY i.created_at DESC, i.id DESC "
            "LIMIT ? OFFSET ?"
        )
    return QueryPlan(sql=sql, params=where_params + (limit, offset))


def execute_query(
    conn: sqlite3.Connection,
    subject: QuerySubject,
    expression: str | None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[sqlite3.Row]:
    plan = compile_query(subject, expression, limit=limit, offset=offset)
    return conn.execute(plan.sql, plan.params).fetchall()


def list_shortcut_expression(subject: QuerySubject, **filters: str | None) -> str:
    expressions: list[str] = []
    if subject == "intent":
        if filters.get("status"):
            expressions.append(f'status={_quote_string_literal(filters["status"] or "")}')
        if filters.get("kind"):
            expressions.append(f'kind={_quote_string_literal(filters["kind"] or "")}')
        if filters.get("tag"):
            expressions.append(f'tags~{_quote_string_literal(filters["tag"] or "")}')
    else:
        if filters.get("intent"):
            expressions.append(f'intent_id={_quote_string_literal(filters["intent"] or "")}')
        if filters.get("reported_status"):
            expressions.append(f'reported_status={_quote_string_literal(filters["reported_status"] or "")}')
        if filters.get("verified_status"):
            expressions.append(f'verified_status={_quote_string_literal(filters["verified_status"] or "")}')
        if filters.get("agent"):
            expressions.append(f'agent.agent_id={_quote_string_literal(filters["agent"] or "")}')
    return " AND ".join(expressions)


def _quote_string_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
