from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

QuerySubject = Literal["intent", "attempt"]
ValueType = Literal["text", "integer", "boolean", "timestamp", "tag"]


class QueryError(ValueError):
    pass


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    params: tuple[object, ...]


@dataclass(frozen=True)
class BlameTarget:
    path: str
    line: int | None = None


@dataclass(frozen=True)
class BlameRecord:
    attempt_id: str
    intent_id: str
    file_kind: str
    commit_oid: str | None
    reported_status: str
    verified_status: str
    started_at: str


@dataclass(frozen=True)
class Comparison:
    field: str
    operator: str
    value: object


@dataclass(frozen=True)
class UnaryExpression:
    operator: str
    operand: "Expression"


@dataclass(frozen=True)
class BinaryExpression:
    operator: str
    left: "Expression"
    right: "Expression"


Expression = Comparison | UnaryExpression | BinaryExpression


@dataclass(frozen=True)
class SqlFragment:
    sql: str
    params: tuple[object, ...] = ()


@dataclass(frozen=True)
class QueryField:
    name: str
    value_type: ValueType
    lower_attempt: Callable[[str, object], SqlFragment]
    lower_intent: Callable[[str, object], SqlFragment]
