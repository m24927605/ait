# Implementation Plan: Split Query Module

**Branch**: `002-split-query-module` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-split-query-module/spec.md`

## Summary

Split the oversized `ait.query` implementation into cohesive parser, model,
SQL-lowering, execution, and blame modules while keeping `ait.query` as the
public compatibility surface. The slice is mechanical: no new query language
features, no SQLite schema changes, and no CLI output changes. Any discovered
query/blame bug must be covered by a regression test before implementation is
marked complete.

## Technical Context

**Language/Version**: Python 3.14+  
**Primary Dependencies**: Python standard library only; no new runtime dependencies  
**Storage**: Existing SQLite tables accessed through supplied `sqlite3.Connection`  
**Testing**: `pytest` and existing `unittest`-style tests  
**Target Platform**: Local POSIX CLI environments supported by AIT  
**Project Type**: Python CLI/library package  
**Performance Goals**: Preserve current query result ordering and avoid extra SQL round trips  
**Constraints**: Preserve public imports from `ait.query`; no SQLite schema, CLI flag, JSON key, or daemon protocol changes  
**Scale/Scope**: Query module refactor only; no new query operators or fields

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Kit Traceability**: PASS. Active feature recorded in
  `.specify/feature.json`; this plan links to `spec.md` and will drive
  `tasks.md`.
- **Low Coupling, High Cohesion**: PASS. Target boundaries are parser/models,
  SQL field lowering, execution, and blame lookup. `ait.query` becomes a facade.
- **Stable Public Behavior**: PASS. Public functions, dataclasses, `QueryError`,
  CLI command behavior, SQLite semantics, and test import paths are listed in
  the compatibility contract.
- **Local Safety And Data Integrity**: PASS. The slice only reads existing
  SQLite rows through caller-provided connections and does not mutate Git,
  worktrees, daemon state, or SQLite schema.
- **Verification Before Completion**: PASS. Verification commands and
  line-count/import checks are listed below and must be reflected in `tasks.md`.

## Project Structure

### Documentation (this feature)

```text
specs/002-split-query-module/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── public-query-surface.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/ait/
├── query/
│   ├── __init__.py      # public compatibility facade
│   ├── models.py        # dataclasses, literal types, QueryError
│   ├── parser.py        # tokenization and expression parsing
│   ├── fields.py        # whitelisted field registry and SQL lowering
│   ├── executor.py      # compile_query, execute_query, shortcuts
│   └── blame.py         # blame target parsing and indexed evidence lookup
└── cli/
    ├── _shared.py
    └── query_helpers.py

tests/
├── test_query.py
└── test_cli_adapters.py
```

**Structure Decision**: Replace the single `src/ait/query.py` module with a
package named `src/ait/query/`. `src/ait/query/__init__.py` re-exports the same
public symbols so `from ait.query import ...` remains stable.

### Dependency Direction

Allowed query package direction:

```text
__init__ -> models, parser, executor, blame
executor -> models, parser, fields
fields -> models
parser -> models
blame -> models
```

Parser code must not import SQL lowering. Field lowering must not import CLI
helpers or open database connections. Execution may compile SQL and run it on a
caller-provided connection, but it must not own connection lifecycle. Blame may
read indexed evidence through the provided connection and must not depend on
query parser internals.

### Public Compatibility Surface

- `QueryError`
- `QueryPlan`
- `BlameTarget`
- `BlameRecord`
- `Comparison`
- `UnaryExpression`
- `BinaryExpression`
- `Expression`
- `parse_query`
- `compile_query`
- `execute_query`
- `list_shortcut_expression`
- `parse_blame_target`
- `blame_path`
- CLI behavior for `ait query`, `ait blame`, `ait intent list`, and
  `ait attempt list`

### Verification Plan

Run before marking implementation complete:

```bash
uv run pytest tests/test_query.py
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
wc -l src/ait/query/*.py | sort -nr
PYTHONPATH=src python3 - <<'PY'
from ait.query import (
    BinaryExpression, BlameRecord, BlameTarget, Comparison, QueryError,
    QueryPlan, UnaryExpression, blame_path, compile_query, execute_query,
    list_shortcut_expression, parse_blame_target, parse_query,
)
print("ait.query public imports ok")
PY
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Replace module with package | Needed to keep `ait.query` public import stable while giving internals cohesive files | Adding several top-level `query_*` modules would scatter one concern across `src/ait/` and leave `ait.query` as an ambiguous implementation module |
