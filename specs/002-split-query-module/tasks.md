# Tasks: Split Query Module

**Input**: Design documents from `specs/002-split-query-module/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required because this is a public-behavior-preserving refactor.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish baseline behavior and package skeleton.

- [x] T001 Run baseline query tests with `uv run pytest tests/test_query.py`
- [x] T002 Create `src/ait/query/` package directory for the refactor
- [x] T003 Add public facade skeleton in `src/ait/query/__init__.py`
- [x] T004 Add shared model definitions in `src/ait/query/models.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Move pure internals before user-facing behavior changes.

**CRITICAL**: No story implementation can be marked complete until public imports still resolve.

- [x] T005 [P] Move parser/tokenizer behavior into `src/ait/query/parser.py`
- [x] T006 [P] Move field registry and SQL fragment lowering into `src/ait/query/fields.py`
- [x] T007 [P] Move query planning/execution/shortcut behavior into `src/ait/query/executor.py`
- [x] T008 [P] Move blame target parsing and evidence lookup into `src/ait/query/blame.py`
- [x] T009 Export all contract symbols from `src/ait/query/__init__.py`
- [x] T010 Remove legacy implementation file `src/ait/query.py`
- [x] T011 Run public import contract from `specs/002-split-query-module/quickstart.md`

---

## Phase 3: User Story 1 - Preserve Query Behavior (Priority: P1) MVP

**Goal**: Query DSL, list shortcuts, SQL planning, execution, and CLI query behavior remain compatible.

**Independent Test**: `uv run pytest tests/test_query.py` and targeted CLI tests pass unchanged.

### Tests for User Story 1

- [x] T012 [US1] Run `uv run pytest tests/test_query.py` after moving query internals
- [x] T013 [US1] Run `uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py` after moving query internals

### Implementation for User Story 1

- [x] T014 [US1] Fix any query behavior or import regressions found by T012/T013 in `src/ait/query/`
- [x] T015 [US1] Add regression tests in `tests/test_query.py` if implementation reveals an untested query bug

**Checkpoint**: User Story 1 is complete when query tests and targeted CLI tests pass without compatibility changes.

---

## Phase 4: User Story 2 - Preserve Blame Behavior (Priority: P1)

**Goal**: Blame parsing and indexed evidence lookup remain compatible.

**Independent Test**: Blame tests in `tests/test_query.py` pass and public `blame_path` imports still work.

### Tests for User Story 2

- [x] T016 [US2] Run blame-focused tests from `tests/test_query.py`

### Implementation for User Story 2

- [x] T017 [US2] Fix any blame behavior or import regressions found by T016 in `src/ait/query/blame.py`
- [x] T018 [US2] Add regression tests in `tests/test_query.py` if implementation reveals an untested blame bug

**Checkpoint**: User Story 2 is complete when blame tests pass and `ait.query.blame_path` remains exported.

---

## Phase 5: User Story 3 - Make Query Internals Cohesive (Priority: P2)

**Goal**: Query internals are split by responsibility and line-count gates pass.

**Independent Test**: Architecture checks show the facade and implementation modules meet the plan boundaries.

### Implementation for User Story 3

- [x] T019 [US3] Verify dependency direction in `src/ait/query/*.py` matches `specs/002-split-query-module/plan.md`
- [x] T020 [US3] Run `wc -l src/ait/query/*.py | sort -nr` and confirm no query module exceeds 600 lines
- [x] T021 [US3] Confirm `src/ait/query.py` no longer exists

**Checkpoint**: User Story 3 is complete when architecture checks pass and the public facade is below 150 lines.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate the entire repository and update task evidence.

- [x] T022 Run `uv run pytest`
- [x] T023 Run `PYTHONPATH=src python3 -m unittest discover -s tests`
- [x] T024 Run `git diff --check`
- [x] T025 Audit `specs/002-split-query-module/spec.md` requirements and success criteria against real evidence
- [x] T026 Mark completed tasks in `specs/002-split-query-module/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup completion and blocks all user stories.
- **User Story 1 and 2 (P1)**: Depend on Foundational completion.
- **User Story 3 (P2)**: Depends on User Story 1 and 2 because architecture checks rely on final files.
- **Polish**: Depends on all selected user stories.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational.
- **User Story 2 (P1)**: Starts after Foundational and can run alongside US1 after files are moved.
- **User Story 3 (P2)**: Starts after US1 and US2 pass.

### Parallel Opportunities

- T005, T006, T007, and T008 touch separate new files and can be prepared in parallel after models exist.
- T012 and T016 can run in parallel after public imports are restored.
- T020 and T021 can run in parallel with documentation audit after tests pass.

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete User Story 1 query compatibility.
3. Complete User Story 2 blame compatibility.
4. Stop and validate targeted tests before line-count polish.

### Incremental Delivery

1. Move pure dataclasses and parser.
2. Move SQL field lowering and execution.
3. Move blame lookup.
4. Restore public facade.
5. Run targeted tests, then full repository gates.

## Notes

- Mark a task complete only after the referenced file or command evidence exists.
- If implementation reveals a bug, add a regression test and update this task list before fixing it.
- Do not change query language, SQLite schema, CLI flags, or output formats in this slice.
