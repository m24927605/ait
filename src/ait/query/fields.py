from __future__ import annotations

from ait.query.models import (
    BinaryExpression,
    Comparison,
    Expression,
    QueryError,
    QueryField,
    QuerySubject,
    SqlFragment,
    UnaryExpression,
    ValueType,
)


def lower_expression(subject: QuerySubject, expression: Expression) -> SqlFragment:
    if isinstance(expression, Comparison):
        field = FIELD_REGISTRY.get(expression.field)
        if field is None:
            raise QueryError(f"field is not queryable in v1: {expression.field}")
        lowerer = field.lower_attempt if subject == "attempt" else field.lower_intent
        return lowerer(expression.operator, expression.value)

    if isinstance(expression, UnaryExpression):
        operand = lower_expression(subject, expression.operand)
        return SqlFragment(sql=f"(NOT {operand.sql})", params=operand.params)

    if isinstance(expression, BinaryExpression):
        left = lower_expression(subject, expression.left)
        right = lower_expression(subject, expression.right)
        return SqlFragment(
            sql=f"({left.sql} {expression.operator} {right.sql})",
            params=left.params + right.params,
        )

    raise QueryError("unsupported query expression")


def _scalar_field(
    *,
    name: str,
    value_type: ValueType,
    attempt_expr: str,
    intent_expr: str,
    attempt_via_exists: str | None = None,
) -> QueryField:
    return QueryField(
        name=name,
        value_type=value_type,
        lower_attempt=lambda operator, value: _lower_scalar_predicate(
            attempt_expr, operator, value, value_type
        ),
        lower_intent=lambda operator, value: _lower_scalar_predicate(
            intent_expr, operator, value, value_type
        )
        if attempt_via_exists is None
        else _intent_exists(attempt_via_exists, operator, value, value_type),
    )


def _intent_exists(
    expr: str, operator: str, value: object, value_type: ValueType
) -> SqlFragment:
    inner = _lower_scalar_predicate(expr, operator, value, value_type)
    return SqlFragment(
        sql=(
            "EXISTS ("
            "SELECT 1 "
            "FROM attempts AS a "
            "LEFT JOIN evidence_summaries AS es ON es.attempt_id = a.id "
            f"WHERE a.intent_id = i.id AND {inner.sql}"
            ")"
        ),
        params=inner.params,
    )


def _evidence_file_field(kind: str) -> QueryField:
    def lower_attempt(operator: str, value: object) -> SqlFragment:
        return _exists_fragment(
            "SELECT 1 FROM evidence_files AS ef "
            "WHERE ef.attempt_id = a.id AND ef.kind = ? AND {predicate}",
            operator,
            value,
            "text",
            "ef.file_path",
            prefix_params=(kind,),
        )

    def lower_intent(operator: str, value: object) -> SqlFragment:
        return _exists_fragment(
            "SELECT 1 FROM attempts AS a "
            "JOIN evidence_files AS ef ON ef.attempt_id = a.id "
            "WHERE a.intent_id = i.id AND ef.kind = ? AND {predicate}",
            operator,
            value,
            "text",
            "ef.file_path",
            prefix_params=(kind,),
        )

    return QueryField(
        name=f"files_{kind}",
        value_type="text",
        lower_attempt=lower_attempt,
        lower_intent=lower_intent,
    )


def _commit_oid_field() -> QueryField:
    def lower_attempt(operator: str, value: object) -> SqlFragment:
        return _exists_fragment(
            "SELECT 1 FROM attempt_commits AS ac "
            "WHERE ac.attempt_id = a.id AND {predicate}",
            operator,
            value,
            "text",
            "ac.commit_oid",
        )

    def lower_intent(operator: str, value: object) -> SqlFragment:
        return _exists_fragment(
            "SELECT 1 FROM attempts AS a "
            "JOIN attempt_commits AS ac ON ac.attempt_id = a.id "
            "WHERE a.intent_id = i.id AND {predicate}",
            operator,
            value,
            "text",
            "ac.commit_oid",
        )

    return QueryField(
        name="commit_oid",
        value_type="text",
        lower_attempt=lower_attempt,
        lower_intent=lower_intent,
    )


def _tags_field() -> QueryField:
    def lower_attempt(operator: str, value: object) -> SqlFragment:
        return _lower_tags_predicate("i.tags_json", operator, value)

    def lower_intent(operator: str, value: object) -> SqlFragment:
        return _lower_tags_predicate("i.tags_json", operator, value)

    return QueryField(
        name="tags",
        value_type="tag",
        lower_attempt=lower_attempt,
        lower_intent=lower_intent,
    )


def _exists_fragment(
    template: str,
    operator: str,
    value: object,
    value_type: ValueType,
    expr: str,
    *,
    prefix_params: tuple[object, ...] = (),
) -> SqlFragment:
    predicate = _lower_scalar_predicate(expr, operator, value, value_type)
    return SqlFragment(
        sql=f"EXISTS ({template.format(predicate=predicate.sql)})",
        params=prefix_params + predicate.params,
    )


def _lower_scalar_predicate(
    expr: str, operator: str, value: object, value_type: ValueType
) -> SqlFragment:
    if operator == "IN":
        if not isinstance(value, tuple):
            raise QueryError("IN expects a non-empty list")
        if not value:
            raise QueryError("IN expects a non-empty list")
        normalized = tuple(_normalize_literal(item, value_type) for item in value)
        placeholders = ", ".join("?" for _ in normalized)
        return SqlFragment(sql=f"{expr} IN ({placeholders})", params=normalized)

    normalized_value = _normalize_literal(value, value_type)

    if operator == "~":
        if normalized_value is None:
            raise QueryError("~ does not support NULL")
        return SqlFragment(
            sql=f"instr(COALESCE({expr}, ''), ?) > 0",
            params=(normalized_value,),
        )

    if normalized_value is None:
        if operator == "=":
            return SqlFragment(sql=f"{expr} IS NULL")
        if operator == "!=":
            return SqlFragment(sql=f"{expr} IS NOT NULL")
        raise QueryError("NULL only supports = and !=")

    _validate_operator(operator, value_type)
    return SqlFragment(sql=f"{expr} {operator} ?", params=(normalized_value,))


def _lower_tags_predicate(expr: str, operator: str, value: object) -> SqlFragment:
    if operator == "~":
        normalized = _normalize_literal(value, "text")
        if normalized is None:
            raise QueryError("tags ~ does not support NULL")
        return SqlFragment(
            sql=(
                "EXISTS ("
                f"SELECT 1 FROM json_each({expr}) AS tag "
                "WHERE instr(tag.value, ?) > 0"
                ")"
            ),
            params=(normalized,),
        )

    if operator in {"=", "!="}:
        normalized = _normalize_literal(value, "text")
        quantifier = "EXISTS" if operator == "=" else "NOT EXISTS"
        return SqlFragment(
            sql=(
                f"{quantifier} ("
                f"SELECT 1 FROM json_each({expr}) AS tag "
                "WHERE tag.value = ?"
                ")"
            ),
            params=(normalized,),
        )

    if operator == "IN":
        if not isinstance(value, tuple) or not value:
            raise QueryError("tags IN expects a non-empty list")
        normalized = tuple(_normalize_literal(item, "text") for item in value)
        placeholders = ", ".join("?" for _ in normalized)
        return SqlFragment(
            sql=(
                "EXISTS ("
                f"SELECT 1 FROM json_each({expr}) AS tag "
                f"WHERE tag.value IN ({placeholders})"
                ")"
            ),
            params=normalized,
        )

    raise QueryError(f"operator {operator} is not supported for tags")


def _validate_operator(operator: str, value_type: ValueType) -> None:
    allowed = {
        "text": {"=", "!=", "<", ">", "<=", ">=", "~", "IN"},
        "timestamp": {"=", "!=", "<", ">", "<=", ">=", "~", "IN"},
        "integer": {"=", "!=", "<", ">", "<=", ">=", "IN"},
        "boolean": {"=", "!=", "IN"},
        "tag": {"=", "!=", "~", "IN"},
    }[value_type]
    if operator not in allowed:
        raise QueryError(f"operator {operator} is not supported for {value_type}")


def _normalize_literal(value: object, value_type: ValueType) -> object:
    if value is None:
        return None
    if value_type in {"text", "timestamp", "tag"}:
        if not isinstance(value, str):
            raise QueryError("expected string literal")
        return value
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise QueryError("expected integer literal")
        return value
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise QueryError("expected boolean literal")
        return int(value)
    raise QueryError(f"unsupported value type: {value_type}")


FIELD_REGISTRY: dict[str, QueryField] = {
    "id": _scalar_field(
        name="id",
        value_type="text",
        attempt_expr="a.id",
        intent_expr="i.id",
        attempt_via_exists="a.id",
    ),
    "status": _scalar_field(
        name="status",
        value_type="text",
        attempt_expr="i.status",
        intent_expr="i.status",
    ),
    "kind": _scalar_field(
        name="kind",
        value_type="text",
        attempt_expr="i.kind",
        intent_expr="i.kind",
    ),
    "title": _scalar_field(
        name="title",
        value_type="text",
        attempt_expr="i.title",
        intent_expr="i.title",
    ),
    "description": _scalar_field(
        name="description",
        value_type="text",
        attempt_expr="i.description",
        intent_expr="i.description",
    ),
    "created_at": _scalar_field(
        name="created_at",
        value_type="timestamp",
        attempt_expr="i.created_at",
        intent_expr="i.created_at",
    ),
    "created_by.actor_type": _scalar_field(
        name="created_by.actor_type",
        value_type="text",
        attempt_expr="i.created_by_actor_type",
        intent_expr="i.created_by_actor_type",
    ),
    "created_by.actor_id": _scalar_field(
        name="created_by.actor_id",
        value_type="text",
        attempt_expr="i.created_by_actor_id",
        intent_expr="i.created_by_actor_id",
    ),
    "tags": _tags_field(),
    "intent_id": _scalar_field(
        name="intent_id",
        value_type="text",
        attempt_expr="a.intent_id",
        intent_expr="a.intent_id",
        attempt_via_exists="a.intent_id",
    ),
    "agent.agent_id": _scalar_field(
        name="agent.agent_id",
        value_type="text",
        attempt_expr="a.agent_id",
        intent_expr="a.agent_id",
        attempt_via_exists="a.agent_id",
    ),
    "agent.model": _scalar_field(
        name="agent.model",
        value_type="text",
        attempt_expr="a.agent_model",
        intent_expr="a.agent_model",
        attempt_via_exists="a.agent_model",
    ),
    "agent.harness": _scalar_field(
        name="agent.harness",
        value_type="text",
        attempt_expr="a.agent_harness",
        intent_expr="a.agent_harness",
        attempt_via_exists="a.agent_harness",
    ),
    "reported_status": _scalar_field(
        name="reported_status",
        value_type="text",
        attempt_expr="a.reported_status",
        intent_expr="a.reported_status",
        attempt_via_exists="a.reported_status",
    ),
    "verified_status": _scalar_field(
        name="verified_status",
        value_type="text",
        attempt_expr="a.verified_status",
        intent_expr="a.verified_status",
        attempt_via_exists="a.verified_status",
    ),
    "started_at": _scalar_field(
        name="started_at",
        value_type="timestamp",
        attempt_expr="a.started_at",
        intent_expr="a.started_at",
        attempt_via_exists="a.started_at",
    ),
    "ended_at": _scalar_field(
        name="ended_at",
        value_type="timestamp",
        attempt_expr="a.ended_at",
        intent_expr="a.ended_at",
        attempt_via_exists="a.ended_at",
    ),
    "workspace.kind": _scalar_field(
        name="workspace.kind",
        value_type="text",
        attempt_expr="a.workspace_kind",
        intent_expr="a.workspace_kind",
        attempt_via_exists="a.workspace_kind",
    ),
    "workspace.base_ref_oid": _scalar_field(
        name="workspace.base_ref_oid",
        value_type="text",
        attempt_expr="a.base_ref_oid",
        intent_expr="a.base_ref_oid",
        attempt_via_exists="a.base_ref_oid",
    ),
    "observed.tool_calls": _scalar_field(
        name="observed.tool_calls",
        value_type="integer",
        attempt_expr="es.observed_tool_calls",
        intent_expr="es.observed_tool_calls",
        attempt_via_exists="es.observed_tool_calls",
    ),
    "observed.file_reads": _scalar_field(
        name="observed.file_reads",
        value_type="integer",
        attempt_expr="es.observed_file_reads",
        intent_expr="es.observed_file_reads",
        attempt_via_exists="es.observed_file_reads",
    ),
    "observed.file_writes": _scalar_field(
        name="observed.file_writes",
        value_type="integer",
        attempt_expr="es.observed_file_writes",
        intent_expr="es.observed_file_writes",
        attempt_via_exists="es.observed_file_writes",
    ),
    "observed.commands_run": _scalar_field(
        name="observed.commands_run",
        value_type="integer",
        attempt_expr="es.observed_commands_run",
        intent_expr="es.observed_commands_run",
        attempt_via_exists="es.observed_commands_run",
    ),
    "observed.duration_ms": _scalar_field(
        name="observed.duration_ms",
        value_type="integer",
        attempt_expr="es.observed_duration_ms",
        intent_expr="es.observed_duration_ms",
        attempt_via_exists="es.observed_duration_ms",
    ),
    "observed.tests_run": _scalar_field(
        name="observed.tests_run",
        value_type="integer",
        attempt_expr="es.observed_tests_run",
        intent_expr="es.observed_tests_run",
        attempt_via_exists="es.observed_tests_run",
    ),
    "observed.tests_passed": _scalar_field(
        name="observed.tests_passed",
        value_type="integer",
        attempt_expr="es.observed_tests_passed",
        intent_expr="es.observed_tests_passed",
        attempt_via_exists="es.observed_tests_passed",
    ),
    "observed.tests_failed": _scalar_field(
        name="observed.tests_failed",
        value_type="integer",
        attempt_expr="es.observed_tests_failed",
        intent_expr="es.observed_tests_failed",
        attempt_via_exists="es.observed_tests_failed",
    ),
    "observed.lint_passed": _scalar_field(
        name="observed.lint_passed",
        value_type="boolean",
        attempt_expr="es.observed_lint_passed",
        intent_expr="es.observed_lint_passed",
        attempt_via_exists="es.observed_lint_passed",
    ),
    "observed.build_passed": _scalar_field(
        name="observed.build_passed",
        value_type="boolean",
        attempt_expr="es.observed_build_passed",
        intent_expr="es.observed_build_passed",
        attempt_via_exists="es.observed_build_passed",
    ),
    "files_read": _evidence_file_field("read"),
    "files_touched": _evidence_file_field("touched"),
    "files_changed": _evidence_file_field("changed"),
    "commit_oid": _commit_oid_field(),
}
