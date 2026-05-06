# Tasks: Split Daemon Module

**Input**: Design documents from `specs/005-split-daemon-module/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required because this refactor preserves daemon lifecycle, socket protocol handling, thread behavior, and established patch surfaces.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Run spec-kit prerequisite check with `.specify/scripts/bash/check-prerequisites.sh --json`
- [x] T002 Run baseline daemon tests with `uv run pytest tests/test_daemon_lifecycle.py tests/test_daemon_reaper.py tests/test_daemon_concurrency.py tests/test_daemon_verifier_threads.py tests/test_daemon_e2e.py`
- [x] T003 Run baseline targeted daemon consumers with `uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py tests/test_runner.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T004 Create daemon model module in `src/ait/daemon_models.py`
- [x] T005 [P] Create daemon state helper module in `src/ait/daemon_state.py`
- [x] T006 [P] Create daemon reaper module in `src/ait/daemon_reaper.py`
- [x] T007 [P] Create daemon lifecycle module in `src/ait/daemon_lifecycle.py`
- [x] T008 Rewire `src/ait/daemon.py` to import extracted helpers while preserving patch-sensitive globals

---

## Phase 3: User Story 1 - Preserve Daemon Lifecycle And CLI Behavior (Priority: P1) MVP

**Goal**: Daemon start/stop/status/prune/serve behavior and CLI consumers remain compatible.

**Independent Test**: Daemon lifecycle tests and public import contract pass unchanged.

- [x] T009 [US1] Run public import contract from `specs/005-split-daemon-module/quickstart.md`
- [x] T010 [US1] Run `uv run pytest tests/test_daemon_lifecycle.py`
- [x] T011 [US1] Run daemon CLI/status consumers with `uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py`
- [x] T012 [US1] Fix any lifecycle/status/CLI regression in `src/ait/daemon.py` or `src/ait/daemon_*.py`

---

## Phase 4: User Story 2 - Preserve Server Loop, Protocol, And Background Work (Priority: P1)

**Goal**: Client protocol handling, concurrent accept loop, background verifier/summarizer work, and reaper behavior remain compatible.

**Independent Test**: Daemon concurrency, reaper, verifier-thread, e2e, runner, and hook tests pass unchanged.

- [x] T013 [US2] Run `uv run pytest tests/test_daemon_reaper.py tests/test_daemon_concurrency.py tests/test_daemon_verifier_threads.py tests/test_daemon_e2e.py`
- [x] T014 [US2] Run `uv run pytest tests/test_runner.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py`
- [x] T015 [US2] Verify patch-sensitive tests still affect `ait.daemon._handle_client`, `ait.daemon._verify_attempt_in_background`, and `ait.daemon.verify_attempt`
- [x] T016 [US2] Fix any server/protocol/background regression in `src/ait/daemon.py` or `src/ait/daemon_*.py`
- [x] T017 [US2] Add regression tests in daemon tests if implementation reveals an untested daemon bug

---

## Phase 5: User Story 3 - Make Daemon Internals Cohesive (Priority: P2)

**Goal**: Daemon internals are separated by responsibility and dependency direction gates pass.

**Independent Test**: Architecture checks from quickstart pass.

- [x] T018 [US3] Run daemon architecture gate from `specs/005-split-daemon-module/quickstart.md`
- [x] T019 [US3] Confirm helper modules do not import `ait.daemon`
- [x] T020 [US3] Confirm `src/ait/daemon.py` stays below 420 lines and helpers stay below 400 lines

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T021 Run targeted daemon tests from `specs/005-split-daemon-module/plan.md`
- [x] T022 Run `uv run pytest`
- [x] T023 Run `PYTHONPATH=src python3 -m unittest discover -s tests`
- [x] T024 Run `git diff --check`
- [x] T025 Audit `specs/005-split-daemon-module/spec.md` requirements and success criteria against real evidence in `specs/005-split-daemon-module/audit.md`
- [x] T026 Mark completed tasks in `specs/005-split-daemon-module/tasks.md`

---

## Dependencies & Execution Order

- Phase 1 must complete before code movement.
- Phase 2 must complete before public behavior verification.
- US1 and US2 both depend on Phase 2.
- US3 depends on final helper layout.
- Polish depends on all user stories.

## Parallel Opportunities

- T005, T006, and T007 affect separate helper files and can be prepared in parallel after T004.
- US1 lifecycle/CLI verification and US2 protocol/background verification can run independently after helper extraction.
- Architecture checks can run while targeted consumer tests are reviewed.

## Notes

- Do not convert `ait.daemon` to a package in this slice.
- Keep patch-sensitive server/client/background functions in `src/ait/daemon.py` or as patch-compatible globals.
- Do not change daemon protocol envelopes, CLI output, SQLite schema, or generated hook resources.
- Mark tasks complete only after command/file evidence exists.
- If implementation reveals a bug, update the spec/plan/tasks before fixing it and add a regression test.
