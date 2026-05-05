# Feature Specification: Split Query Module

**Feature Branch**: `002-split-query-module`  
**Created**: 2026-05-06  
**Status**: Draft  
**Input**: User description: "Refactor the oversized query module into cohesive parser, SQL lowering, execution, and blame modules while preserving ait query and blame public behavior and fixing any discovered query bugs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Query Behavior (Priority: P1)

As an AIT user, I want existing `ait query`, list shortcut filters, and query
DSL expressions to return the same records after the refactor, so that
architecture cleanup does not change the way I inspect intents and attempts.

**Why this priority**: Query is a public inspection surface. A refactor that
changes results, accepted expressions, JSON/table output, or pagination would
break existing workflows.

**Independent Test**: Run the existing query test module and targeted CLI list
tests before and after the module split. Results, errors, and ordering remain
unchanged for intent and attempt queries.

**Acceptance Scenarios**:

1. **Given** existing intent and attempt records, **When** a user runs an
   attempt query with field filters, boolean logic, substring matching, and
   pagination, **Then** the same attempts are returned in the same order.
2. **Given** existing intent records, **When** a user runs an intent query that
   references attempt fields through supported `EXISTS` semantics, **Then** the
   same intents are returned as before the refactor.
3. **Given** invalid expressions or unsupported fields, **When** a user runs
   query compilation, **Then** the same `QueryError` behavior is preserved.

---

### User Story 2 - Preserve Blame Behavior (Priority: P1)

As an AIT user, I want `ait blame <path[:line]>` and the programmatic
`blame_path()` API to keep working after query internals are split, so that file
provenance remains trustworthy.

**Why this priority**: Blame shares the current oversized module but is a
separate user workflow. Splitting query must not orphan or rewrite blame logic
without tests.

**Independent Test**: Run blame target parsing and blame metadata tests before
and after extraction. Supported path and optional line formats behave the same,
and indexed evidence lookup returns the same records.

**Acceptance Scenarios**:

1. **Given** a file path with indexed evidence, **When** the user runs blame,
   **Then** AIT returns the same attempt IDs, file kind ranking, commit OIDs,
   and statuses as before.
2. **Given** a target with a positive line suffix, **When** the target is parsed,
   **Then** the path and line are preserved.
3. **Given** a target with line `0` or a leading-zero line suffix, **When** the
   target is parsed, **Then** the same validation error is raised.

---

### User Story 3 - Make Query Internals Cohesive (Priority: P2)

As a maintainer, I want query parsing, SQL lowering, field registry, execution,
and blame lookup to live in focused modules with stable compatibility exports,
so that future query changes touch the smallest relevant area.

**Why this priority**: The current single module mixes unrelated concerns and
is one of the largest production files. Separating responsibilities improves
maintenance without changing user behavior.

**Independent Test**: Inspect module line counts and import paths after the
split. Each new module has one clear responsibility, `ait.query` remains a
compatibility facade, and existing public imports still work.

**Acceptance Scenarios**:

1. **Given** downstream code imports `compile_query`, `execute_query`,
   `parse_query`, `blame_path`, and query dataclasses from `ait.query`,
   **When** the refactor is complete, **Then** those imports still succeed.
2. **Given** a maintainer opens query internals, **When** they inspect module
   boundaries, **Then** parser, field lowering, execution, and blame are not
   mixed in a single implementation file.
3. **Given** the refactor touches query internals, **When** line-count gates
   run, **Then** no touched production query module exceeds 600 lines without a
   documented exception.

### Edge Cases

- Empty or whitespace-only expressions still list all records for the selected
  subject.
- String literal escaping, Unicode text, booleans, `NULL`, negative integers,
  `IN`, `NOT`, `AND`, `OR`, parentheses, and substring matching keep current
  parsing behavior.
- Tags and evidence-file filters continue to use the same SQL semantics.
- Shortcut filters continue to quote user input so injected query fragments are
  treated as literal text.
- Existing import paths keep working for tests and third-party users that
  import from `ait.query`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST keep `parse_query(expression)` public behavior
  compatible for supported DSL expressions.
- **FR-002**: AIT MUST keep `compile_query(subject, expression, limit, offset)`
  SQL shape semantically equivalent for intent and attempt subjects.
- **FR-003**: AIT MUST keep `execute_query(conn, subject, expression, limit,
  offset)` returning the same rows for existing supported filters.
- **FR-004**: AIT MUST keep `list_shortcut_expression(subject, **filters)`
  quoting and filter composition behavior compatible.
- **FR-005**: AIT MUST keep `parse_blame_target(target)` and
  `blame_path(conn, target)` behavior compatible.
- **FR-006**: AIT MUST keep public dataclasses and `QueryError` importable from
  `ait.query`.
- **FR-007**: Query internals MUST be split into focused modules for models,
  parser/tokenization, field registry/lowering, execution, and blame lookup.
- **FR-008**: The `ait.query` module MUST become a compatibility facade rather
  than owning all implementation concerns directly.
- **FR-009**: Refactor changes MUST preserve the documented public behavior
  unless this specification explicitly declares a compatibility change.
- **FR-010**: Refactor changes MUST improve or preserve cohesion and coupling
  metrics named in Success Criteria.
- **FR-011**: If a query or blame bug is discovered during extraction, the bug
  MUST be fixed in the same slice with a regression test and documented task.

### Key Entities *(include if feature involves data)*

- **Query Expression**: Parsed representation of user query filters, including
  comparisons and boolean composition.
- **Query Field Registry**: Whitelisted fields and subject-specific lowering
  rules for intent and attempt queries.
- **Query Plan**: SQL statement and bound parameters produced from a subject and
  expression.
- **Blame Target**: User-supplied file path with optional line suffix.
- **Blame Record**: Indexed attempt evidence returned for a file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `tests/test_query.py` passes without reducing assertion coverage
  for parser, compiler, execution, shortcut, and blame behavior.
- **SC-002**: Existing CLI tests that exercise query, attempt list, and intent
  list behavior pass unchanged.
- **SC-003**: `src/ait/query.py` is reduced to a compatibility facade below 150
  lines.
- **SC-004**: No new or touched query implementation module exceeds 600 lines.
- **SC-005**: All public imports currently used by `tests/test_query.py` from
  `ait.query` remain available.
- **SC-006**: Full repository tests and `git diff --check` pass before tasks are
  marked complete.

## Assumptions

- This slice is a mechanical refactor of query internals; it does not add new
  query language features.
- SQLite table names, JSON keys, command names, flags, and output formats stay
  unchanged.
- Existing tests are the behavioral baseline; new tests are added only for
  newly discovered bugs or compatibility gaps.
