# Tasks: Reconcile Local Artifacts

**Input**: Design documents from `specs/005-reconcile-local-artifacts/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included because the specification requires acceptance coverage for loss prevention, generated skips, conflict handling, and JSON reporting.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the focused module and test file for local artifact reconciliation.

- [x] T001 Create empty local artifact module in `src/ait/local_artifacts.py`
- [x] T002 [P] Create local artifact test module in `tests/test_local_artifacts.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and scan/classification policy that all user stories depend on.

- [x] T003 Define `LocalArtifact`, `ArtifactDecision`, and `ReconciliationReport` dataclasses in `src/ait/local_artifacts.py`
- [x] T004 Implement safe relative path validation and destination resolution helpers in `src/ait/local_artifacts.py`
- [x] T005 Implement Git ignored/untracked artifact scanning in `src/ait/local_artifacts.py`
- [x] T006 Implement deterministic generated-path, symlink, binary, oversized, and secret-risk guardrails in `src/ait/local_artifacts.py`
- [x] T007 [P] Add unit tests for scan and guardrail classification in `tests/test_local_artifacts.py`

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Prevent Silent Local File Loss (Priority: P1) MVP

**Goal**: Land accepted attempts without silently deleting ignored or untracked local user work.

**Independent Test**: Create an ignored `.env.local` in an attempt worktree, land the attempt, and verify the worktree is retained with `.env.local` reported pending.

### Tests for User Story 1

- [x] T008 [P] [US1] Add app flow test for ignored `.env.local` retention during land in `tests/test_app_flow.py`
- [x] T009 [P] [US1] Add local artifact copy/pending report tests in `tests/test_local_artifacts.py`

### Implementation for User Story 1

- [x] T010 [US1] Implement reconciliation execution and safe copy behavior in `src/ait/local_artifacts.py`
- [x] T011 [US1] Add local artifact report field to `AttemptLandResult` in `src/ait/app.py`
- [x] T012 [US1] Invoke local artifact reconciliation before `remove_attempt_workspace()` in `land_attempt()` in `src/ait/app.py`
- [x] T013 [US1] Retain the attempt worktree and set `worktree_cleaned=false` when pending or blocked artifacts remain in `src/ait/app.py`

**Checkpoint**: User Story 1 is independently functional and testable.

---

## Phase 4: User Story 2 - Explain Artifact Decisions (Priority: P2)

**Goal**: Expose copied, skipped, pending, blocked, and cleanup decisions clearly in command results.

**Independent Test**: Land an attempt with safe, generated, and pending artifacts and verify JSON output includes categorized decisions and reasons.

### Tests for User Story 2

- [x] T014 [P] [US2] Add CLI JSON land test for `local_artifacts` output in `tests/test_app_flow.py`
- [x] T015 [P] [US2] Add generated directory skip report tests in `tests/test_local_artifacts.py`

### Implementation for User Story 2

- [x] T016 [US2] Add stable `asdict`-friendly report serialization fields in `src/ait/local_artifacts.py`
- [x] T017 [US2] Ensure `ait attempt land` JSON includes `local_artifacts` through existing dataclass serialization in `src/ait/cli/attempt.py`
- [x] T018 [US2] Preserve prior JSON keys and successful cleanup behavior when no artifacts are detected in `src/ait/app.py`

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 - Use Intelligent Classification Safely (Priority: P3)

**Goal**: Represent the AI-assisted classification boundary while enforcing deterministic guardrails.

**Independent Test**: Simulate classifier recommendations that conflict with safety rules and verify guardrails decide the final action.

### Tests for User Story 3

- [x] T019 [P] [US3] Add guardrail override tests for classifier-like recommendations in `tests/test_local_artifacts.py`

### Implementation for User Story 3

- [x] T020 [US3] Add internal optional recommendation hook that accepts redacted artifact metadata in `src/ait/local_artifacts.py`
- [x] T021 [US3] Ensure deterministic guardrails override recommendation hook output in `src/ait/local_artifacts.py`

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, docs consistency, and architecture gates.

- [x] T022 [P] Update `specs/005-reconcile-local-artifacts/quickstart.md` if implementation behavior differs from planned acceptance flow
- [x] T023 Run `uv run pytest tests/test_local_artifacts.py`
- [x] T024 Run `uv run pytest tests/test_app_flow.py tests/test_cli_run.py tests/test_workspace.py`
- [x] T025 Run `uv run pytest`
- [x] T026 Run `PYTHONPATH=src python3 -m unittest discover -s tests`
- [x] T027 Run `git diff --check`
- [x] T028 Run architecture gate from `specs/005-reconcile-local-artifacts/plan.md`
- [x] T029 Audit FR-001 through FR-014 and SC-001 through SC-006 against test evidence

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup completion and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational and is the MVP.
- **User Story 2 (Phase 4)**: Depends on User Story 1 report plumbing.
- **User Story 3 (Phase 5)**: Depends on Foundational classification model and can be implemented after US1 basics.
- **Polish (Phase 6)**: Depends on all selected user stories.

### User Story Dependencies

- **User Story 1 (P1)**: Required for MVP and cleanup safety.
- **User Story 2 (P2)**: Builds on US1 by exposing report output.
- **User Story 3 (P3)**: Extends classification boundary without changing required deterministic behavior.

### Parallel Opportunities

- T002 can run in parallel with T001.
- T007 can be developed alongside T003-T006 once dataclass names are known.
- T008 and T009 can run in parallel.
- T014 and T015 can run in parallel.
- T019 can run in parallel with CLI output work after T006.

---

## Parallel Example: User Story 1

```bash
Task: "Add app flow test for ignored .env.local retention during land in tests/test_app_flow.py"
Task: "Add local artifact copy/pending report tests in tests/test_local_artifacts.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Implement User Story 1.
3. Run `uv run pytest tests/test_local_artifacts.py tests/test_app_flow.py`.
4. Verify `.env.local` is not silently lost and worktree retention is reported.

### Incremental Delivery

1. Add deterministic scanning and guardrails.
2. Add land integration that prevents silent loss.
3. Add report output for CLI/JSON users.
4. Add optional recommendation boundary guarded by deterministic rules.
5. Run full verification.

### Notes

- Mark each task complete only after code, tests, and evidence exist.
- Do not add SQLite schema changes for this slice.
- Do not add a runtime third-party dependency.
