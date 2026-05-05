# Tasks: Split Adapters Module

**Input**: Design documents from `specs/004-split-adapters-module/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required because this refactor preserves public adapter imports, CLI behavior, setup/bootstrap writes, and doctor checks.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Run spec-kit prerequisite check with `.specify/scripts/bash/check-prerequisites.sh --json`
- [x] T002 Run baseline adapter tests with `uv run pytest tests/test_adapters.py`
- [x] T003 Run baseline targeted adapter consumers with `uv run pytest tests/test_cli_adapters.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T004 Create adapter model module in `src/ait/adapter_models.py`
- [x] T005 [P] Create adapter registry module in `src/ait/adapter_registry.py`
- [x] T006 [P] Create adapter resource/settings module in `src/ait/adapter_resources.py`
- [x] T007 [P] Create adapter wrapper module in `src/ait/adapter_wrapper.py`
- [x] T008 Replace `src/ait/adapters.py` with public compatibility facade

---

## Phase 3: User Story 1 - Preserve Adapter Discovery And CLI Behavior (Priority: P1) MVP

**Goal**: Adapter discovery, listing, parser choices, and CLI adapter display behavior remain compatible.

**Independent Test**: Public import contract and CLI adapter tests pass unchanged.

- [x] T009 [US1] Run public import contract from `specs/004-split-adapters-module/quickstart.md`
- [x] T010 [US1] Run `uv run pytest tests/test_cli_adapters.py`
- [x] T011 [US1] Fix any adapter discovery or CLI regression in `src/ait/adapters.py` or `src/ait/adapter_*.py`

---

## Phase 4: User Story 2 - Preserve Setup, Bootstrap, And Doctor Behavior (Priority: P1)

**Goal**: Native hook setup, settings merge, wrapper generation, `.envrc`, bootstrap, and doctor behavior remain compatible.

**Independent Test**: Adapter setup and native hook tests pass unchanged against temporary repositories.

- [x] T012 [US2] Move `doctor_adapter()` and `doctor_automation()` into `src/ait/adapter_doctor.py`
- [x] T013 [US2] Move `setup_adapter()`, `bootstrap_adapter()`, `bootstrap_shell_snippet()`, and `enable_available_adapters()` into `src/ait/adapter_setup.py`
- [x] T014 [US2] Run `uv run pytest tests/test_adapters.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py`
- [x] T015 [US2] Fix any setup/bootstrap/doctor regression in `src/ait/adapter_*.py`
- [x] T016 [US2] Add regression tests in `tests/test_adapters.py` if implementation reveals an untested adapter bug

---

## Phase 5: User Story 3 - Make Adapter Internals Cohesive (Priority: P2)

**Goal**: Adapter internals are separated by responsibility and dependency direction gates pass.

**Independent Test**: Architecture checks from quickstart pass.

- [x] T017 [US3] Run adapter architecture gate from `specs/004-split-adapters-module/quickstart.md`
- [x] T018 [US3] Confirm helper modules do not import `ait.adapters`
- [x] T019 [US3] Confirm `src/ait/adapters.py` stays below 150 lines and helpers stay below 400 lines

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T020 Run targeted adapter tests from `specs/004-split-adapters-module/plan.md`
- [x] T021 Run `uv run pytest`
- [x] T022 Run `PYTHONPATH=src python3 -m unittest discover -s tests`
- [x] T023 Run `git diff --check`
- [x] T024 Audit `specs/004-split-adapters-module/spec.md` requirements and success criteria against real evidence in `specs/004-split-adapters-module/audit.md`
- [x] T025 Mark completed tasks in `specs/004-split-adapters-module/tasks.md`

---

## Dependencies & Execution Order

- Phase 1 must complete before code movement.
- Phase 2 must complete before public behavior verification.
- US1 and US2 both depend on Phase 2.
- US3 depends on final helper layout.
- Polish depends on all user stories.

## Parallel Opportunities

- T005, T006, and T007 affect separate helper files and can be prepared in parallel after T004.
- US1 verification and US2 verification can be run independently after the facade and helper modules are wired.
- Native hook tests can be run as a focused group while architecture checks inspect source boundaries.

## Notes

- Do not convert `ait.adapters` to a package in this slice.
- Do not change generated hook resource contents, CLI output keys, or wrapper shell behavior.
- Mark tasks complete only after command/file evidence exists.
- If implementation reveals a bug, update the spec/plan/tasks before fixing it and add a regression test.
