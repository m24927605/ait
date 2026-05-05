# Data Model: Split Query Module

## QueryError

Error type raised for invalid query expressions, unsupported fields, invalid
operators, invalid pagination, and invalid blame targets.

## QueryPlan

Fields:

- `sql`: SQL statement string with placeholders
- `params`: ordered tuple of bound parameters

Validation:

- `limit` and `offset` are validated before plan construction.
- Field and operator validation happens before SQL fragments are returned.

## Query Expression

Types:

- `Comparison`: `field`, `operator`, `value`
- `UnaryExpression`: `operator`, `operand`
- `BinaryExpression`: `operator`, `left`, `right`

Relationships:

- Parser returns a `Query Expression`.
- SQL lowering consumes a `Query Expression` and returns SQL fragments.

## Query Field

Fields:

- `name`: public query field name
- `value_type`: one of `text`, `integer`, `boolean`, `timestamp`, or `tag`
- `lower_attempt`: function that lowers a field predicate for attempt queries
- `lower_intent`: function that lowers a field predicate for intent queries

Validation:

- Only registered field names are queryable.
- Operators are constrained by `value_type`.
- Literal values are normalized before binding.

## SQL Fragment

Fields:

- `sql`: SQL predicate fragment
- `params`: ordered tuple of bound parameters for the fragment

Relationships:

- Field lowerers return SQL fragments.
- Expression lowering combines SQL fragments without reordering parameters.

## BlameTarget

Fields:

- `path`: file path supplied by the user
- `line`: optional positive line number

Validation:

- Empty target is rejected.
- Line suffix `0` and leading-zero suffixes are rejected.

## BlameRecord

Fields:

- `attempt_id`
- `intent_id`
- `file_kind`
- `commit_oid`
- `reported_status`
- `verified_status`
- `started_at`

Relationships:

- Produced from indexed `evidence_files`, `attempts`, and `attempt_commits`
  rows.
