# Tasks: Split Runner Module

**Input**: Design documents from `specs/003-split-runner-module/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required because this refactor preserves public runner behavior and patch points.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Run baseline runner tests with `uv run pytest tests/test_runner.py`
- [x] T002 Add PTY helper module in `src/ait/runner_pty.py`
- [x] T003 Add context helper module in `src/ait/runner_context.py`
- [x] T004 Add transcript helper module in `src/ait/runner_transcript.py`
- [x] T005 Add semantic helper module in `src/ait/runner_semantics.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T006 Move PTY process dataclass and terminal capture helpers from `src/ait/runner.py` to `src/ait/runner_pty.py`
- [x] T007 Move context rendering and budget helpers from `src/ait/runner.py` to `src/ait/runner_context.py`
- [x] T008 Move transcript writer, redaction, normalization, and trace-name helpers from `src/ait/runner.py` to `src/ait/runner_transcript.py`
- [x] T009 Move semantic exit-code and refusal helpers from `src/ait/runner.py` to `src/ait/runner_semantics.py`
- [x] T010 Import moved helpers into `src/ait/runner.py` as module-level names
- [x] T011 Run public runner import contract from `specs/003-split-runner-module/quickstart.md`

---

## Phase 3: User Story 1 - Preserve Wrapped Run Behavior (Priority: P1) MVP

**Goal**: `run_agent_command()` behavior remains compatible.

**Independent Test**: `uv run pytest tests/test_runner.py` passes unchanged.

- [x] T012 [US1] Run `uv run pytest tests/test_runner.py` after helper extraction
- [x] T013 [US1] Fix any runner behavior regressions found by T012 in `src/ait/runner.py` or `src/ait/runner_*.py`
- [x] T014 [US1] Add regression tests in `tests/test_runner.py` if implementation reveals an untested runner bug

---

## Phase 4: User Story 2 - Preserve Test And Extension Patch Surface (Priority: P1)

**Goal**: Existing monkey-patch seams keep affecting `run_agent_command()`.

**Independent Test**: Existing runner tests that patch `ait.runner.*` pass unchanged.

- [x] T015 [US2] Verify patch-sensitive tests in `tests/test_runner.py` pass unchanged
- [x] T016 [US2] Fix any broken patch surface by keeping patchable wrappers or globals in `src/ait/runner.py`

---

## Phase 5: User Story 3 - Make Runner Internals Cohesive (Priority: P2)

**Goal**: Runner internals are separated by responsibility and line-count gates pass.

**Independent Test**: Architecture checks from quickstart pass.

- [x] T017 [US3] Run `wc -l src/ait/runner.py src/ait/runner_*.py | sort -nr`
- [x] T018 [US3] Confirm helper modules do not import `ait.runner`
- [x] T019 [US3] Confirm `src/ait/runner.py` stays below 600 lines and helpers stay below 400 lines

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T020 Run targeted consumer tests from `specs/003-split-runner-module/plan.md`
- [x] T021 Run `uv run pytest`
- [x] T022 Run `PYTHONPATH=src python3 -m unittest discover -s tests`
- [x] T023 Run `git diff --check`
- [x] T024 Audit `specs/003-split-runner-module/spec.md` requirements and success criteria against real evidence
- [x] T025 Mark completed tasks in `specs/003-split-runner-module/tasks.md`

---

## Dependencies & Execution Order

- Phase 1 must complete before helper movement.
- Phase 2 must complete before public behavior verification.
- US1 and US2 both depend on Phase 2.
- US3 depends on final helper layout.
- Polish depends on all user stories.

## Notes

- Do not convert `ait.runner` to a package in this slice.
- Do not move `_finish_attempt_locally` or `_write_command_transcript_best_effort`; they depend on existing patch points.
- Mark tasks complete only after command/file evidence exists.
