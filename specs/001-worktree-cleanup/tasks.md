# Tasks: Worktree Cleanup Policy

**Input**: `specs/001-worktree-cleanup/spec.md`
**Plan**: `specs/001-worktree-cleanup/plan.md`

## Format

- `[x]` completed in the current working tree
- `[ ]` not complete
- `[P]` can run in parallel after dependencies are satisfied
- `US1..US4` refer to user stories in `spec.md`

## Phase 1: Spec-Kit Setup

- [x] T001 Create feature spec at `specs/001-worktree-cleanup/spec.md`
- [x] T002 Create implementation plan at `specs/001-worktree-cleanup/plan.md`
- [x] T003 Create research notes at `specs/001-worktree-cleanup/research.md`
- [x] T004 Create data model at `specs/001-worktree-cleanup/data-model.md`
- [x] T005 Create JSON report contract at `specs/001-worktree-cleanup/contracts/cleanup-report.schema.json`
- [x] T006 Create quickstart at `specs/001-worktree-cleanup/quickstart.md`
- [x] T007 Create task breakdown at `specs/001-worktree-cleanup/tasks.md`

## Phase 2: Foundations

- [x] T008 Add `CleanupPolicy`, `CleanupItem`, `CleanupReport`, and `CleanupError` in `src/ait/cleanup.py`
- [x] T009 Add repo-local cleanup config loading and CLI override merge in `src/ait/cleanup.py`
- [x] T010 Add `list_attempts(conn)` repository helper in `src/ait/db/core_repositories.py`
- [x] T011 Re-export `list_attempts` through `src/ait/db/repositories.py` and `src/ait/db/__init__.py`
- [x] T012 [P] Add repository export/order coverage in `tests/test_db_repositories.py`

## Phase 3: User Story 1 - Inspect Cleanup Impact (P1)

Goal: `ait cleanup` reports cleanup candidates without deleting files.

- [x] T013 Add cleanup candidate scan under `.ait/workspaces` in `src/ait/cleanup.py`
- [x] T014 Add status-based dry-run decisions in `src/ait/cleanup.py`
- [x] T015 Add path size estimation to cleanup items in `src/ait/cleanup.py`
- [x] T016 Add text and JSON report rendering in `src/ait/cli/cleanup_helpers.py`
- [x] T017 Wire `ait cleanup` parser flags in `src/ait/cli_parser.py`
- [x] T018 Register cleanup CLI handler in `src/ait/cli/main.py`
- [x] T019 [P] Test dry-run promoted worktree reporting without deletion in `tests/test_cleanup.py`
- [x] T020 [P] Test JSON cleanup report output in `tests/test_cleanup.py`
- [x] T021 [P] Test text cleanup report output in `tests/test_cleanup.py`

## Phase 4: User Story 2 - Remove Safe Terminal Worktrees (P1)

Goal: `ait cleanup --apply` removes clean terminal worktrees using existing
workspace cleanup paths.

- [x] T022 Use `remove_attempt_workspace()` for attempt-backed worktree deletion in `src/ait/cleanup.py`
- [x] T023 Run `git worktree prune` after successful worktree removal in `src/ait/cleanup.py`
- [x] T024 Preserve idempotent behavior when candidate paths are already missing in `src/ait/cleanup.py`
- [x] T025 [P] Test promoted worktree removal in apply mode in `tests/test_cleanup.py`
- [x] T026 [P] Test discarded worktree handling when the workspace path is already missing in `tests/test_cleanup.py`
- [x] T027 [P] Test cleanup apply is idempotent when run twice in `tests/test_cleanup.py`

## Phase 5: User Story 3 - Retain Reviewable Attempts (P2)

Goal: cleanup keeps reviewable and recent failed/crashed attempts by default.

- [x] T028 Retain active attempts with `reported_status=created|running` in `src/ait/cleanup.py`
- [x] T029 Retain `verified_status=pending` attempts in `src/ait/cleanup.py`
- [x] T030 Retain unpromoted `verified_status=succeeded` attempts in `src/ait/cleanup.py`
- [x] T031 Skip dirty removable worktrees unless `--force` is supplied in `src/ait/cleanup.py`
- [x] T032 [P] Test unpromoted succeeded attempt retention in `tests/test_cleanup.py`
- [x] T033 [P] Test dirty promoted worktree skip in `tests/test_cleanup.py`
- [x] T034 [P] Test active attempt retention in `tests/test_cleanup.py`
- [x] T035 [P] Test pending attempt retention in `tests/test_cleanup.py`
- [x] T036 [P] Test failed/crashed retention-window behavior in `tests/test_cleanup.py`
- [x] T037 [P] Test stale failed/crashed clean worktree removal in `tests/test_cleanup.py`

## Phase 6: User Story 4 - Bound Artifact Growth (P2)

Goal: allowlisted generated artifacts can be reported and removed without
touching non-allowlisted paths.

- [x] T038 Add default artifact allowlist to `src/ait/cleanup.py`
- [x] T039 Add repo-local artifact allowlist parsing and unsafe-name filtering in `src/ait/cleanup.py`
- [x] T040 Add artifact candidate evaluation for allowlisted names in `src/ait/cleanup.py`
- [x] T041 Add artifact deletion path in apply mode in `src/ait/cleanup.py`
- [x] T042 [P] Test repo-local cleanup policy parsing in `tests/test_cleanup.py`
- [x] T043 [P] Test artifact dry-run reports allowlisted generated paths in `tests/test_cleanup.py`
- [x] T044 [P] Test artifact apply removes allowlisted paths only in `tests/test_cleanup.py`
- [x] T045 [P] Test artifact cleanup does not remove non-allowlisted paths in `tests/test_cleanup.py`

## Phase 7: Safety And Error Coverage

- [x] T046 Test orphan worktree is skipped by default in `tests/test_cleanup.py`
- [x] T047 Test `--include-orphans --apply` removes only orphan directories under `.ait/workspaces` in `tests/test_cleanup.py`
- [x] T048 Test `--force --apply` removes a dirty otherwise-removable worktree in `tests/test_cleanup.py`
- [x] T049 Test negative `--older-than` returns exit code 2 in `tests/test_cleanup.py`
- [x] T050 Test path containment rejects a recorded workspace outside `.ait/workspaces` in `tests/test_cleanup.py`
- [x] T051 Test JSON payload fields match `contracts/cleanup-report.schema.json` shape in `tests/test_cleanup.py`

## Phase 8: Documentation And Verification

- [x] T052 Update user-facing README or docs with `ait cleanup` usage
- [x] T053 Run targeted tests: `uv run pytest tests/test_cleanup.py tests/test_db_repositories.py`
- [x] T054 Run full tests: `uv run pytest`
- [x] T055 Run whitespace check: `git diff --check`

## Current Next Task

All planned tasks are complete. Run the verification commands before marking
the feature done.
