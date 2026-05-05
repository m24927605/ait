# Research: Split Query Module

## Decision: Convert `ait.query` From Module To Package

**Rationale**: A package keeps the public import path unchanged while allowing
internals to be grouped by responsibility. `src/ait/query/__init__.py` can
re-export the current public surface, so callers that use `from ait.query
import compile_query` do not need to change.

**Alternatives considered**:

- Keep `src/ait/query.py` and add top-level `query_parser.py`,
  `query_fields.py`, and `query_blame.py`. Rejected because it spreads one
  feature across the root package and leaves the old oversized file as an
  implementation coordinator.
- Leave `query.py` intact and only add comments. Rejected because it does not
  address coupling or cohesion.

## Decision: Keep Connection Ownership Outside Query Internals

**Rationale**: Current `execute_query()` accepts a caller-provided
`sqlite3.Connection`. Preserving that boundary keeps database lifecycle in the
CLI/app layer and prevents duplicated `connect_db + run_migrations` patterns.

**Alternatives considered**:

- Introduce a query repository object in this slice. Rejected because the
  existing public API is small, read-only, and already has an explicit
  connection boundary.

## Decision: Split Parser, Field Lowering, Execution, And Blame Separately

**Rationale**: These concerns change for different reasons. Parser changes are
DSL syntax changes; field lowering changes are SQL/registry changes; execution
changes are pagination and row selection changes; blame changes are provenance
lookup changes.

**Alternatives considered**:

- Combine parser and lowering in one module. Rejected because it would keep
  syntax and SQL generation coupled.
- Combine execution and blame because both read SQLite. Rejected because blame
  is a separate user workflow with independent target parsing and evidence
  ranking behavior.

## Decision: Treat Existing Tests As Compatibility Baseline

**Rationale**: The slice is intended to preserve behavior. Existing query and
CLI tests capture parser behavior, SQL semantics, shortcut quoting, blame target
validation, and public command behavior. Add tests only for discovered gaps.

**Alternatives considered**:

- Rewrite tests around the new module layout. Rejected because that would make
  the refactor easier to fake and weaker at protecting public behavior.
