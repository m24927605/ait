# Contract: Public Query Surface

The refactor must preserve this import surface:

```python
from ait.query import (
    BinaryExpression,
    BlameRecord,
    BlameTarget,
    Comparison,
    QueryError,
    QueryPlan,
    UnaryExpression,
    blame_path,
    compile_query,
    execute_query,
    list_shortcut_expression,
    parse_blame_target,
    parse_query,
)
```

## Functions

### `parse_query(expression: str) -> Expression`

- Rejects empty expressions with `QueryError`.
- Preserves current literal parsing for strings, Unicode, booleans, `NULL`, and
  integers.
- Preserves boolean precedence for `NOT`, `AND`, `OR`, and parentheses.

### `compile_query(subject, expression, *, limit=100, offset=0) -> QueryPlan`

- Accepts `subject` values `intent` and `attempt`.
- Rejects negative `limit` or `offset`.
- Treats `None` or whitespace expressions as unfiltered list queries.
- Preserves current intent and attempt SQL semantics.

### `execute_query(conn, subject, expression, *, limit=100, offset=0)`

- Uses a caller-owned SQLite connection.
- Does not run migrations or close the connection.
- Returns `sqlite3.Row` values as before.

### `list_shortcut_expression(subject, **filters) -> str`

- Preserves filter names used by CLI list commands.
- Quotes user input as query string literals.
- Returns an empty string when no filters are supplied.

### `parse_blame_target(target: str) -> BlameTarget`

- Rejects empty targets.
- Accepts `path:positive_line`.
- Rejects `path:0` and `path:01`.
- Treats other colons as part of the path unless they match the valid line
  suffix form.

### `blame_path(conn, target: str) -> list[BlameRecord]`

- Reads indexed evidence only.
- Preserves file-kind ranking: `changed`, then `touched`, then `read`.
- Preserves ordering by best rank, attempt start time descending, then commit
  OID ascending.

## Non-Contracts

- Internal module names under `ait.query` are not public API.
- Generated SQL text may be reorganized only if query results, ordering, and
  bound-parameter semantics remain equivalent.
