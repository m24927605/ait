# Implementation Plan: Worktree Cleanup Policy

**Branch**: `001-worktree-cleanup`
**Spec**: `specs/001-worktree-cleanup/spec.md`
**Date**: 2026-05-05
**Status**: Complete

## Summary

Add a safe cleanup workflow for AIT-owned attempt worktrees so users can
inspect and reclaim disk space without losing reviewable work. The first
implementation slice introduces `ait cleanup` with dry-run-by-default
behavior, status-based worktree decisions, JSON/text reports, and
repo-local policy configuration.

## Technical Context

- Language: Python 3.14+
- Runtime dependencies: stdlib only
- Storage: existing `.ait/state.sqlite3` attempt records
- Workspace boundary: `.ait/workspaces`
- Git operations: existing worktree helpers plus `git worktree prune`
- Test framework: `pytest` over existing `unittest` tests
- Public surface: new `ait cleanup` command

## Constraints

- No cleanup may delete outside the resolved `.ait/workspaces` directory.
- Cleanup must default to dry-run and require `--apply` before deletion.
- Cleanup must preserve reviewable attempts by default.
- Cleanup must not change existing attempt lifecycle, promotion, discard, or
  query behavior.
- No new runtime dependencies are allowed.

## Constitution Check

- **Safety first**: dry-run default, explicit `--apply`, dirty worktree skip,
  and path containment checks satisfy the project safety rules.
- **Small surface**: the first slice is limited to cleanup command plumbing,
  cleanup policy decisions, and focused tests.
- **Stable behavior**: no existing public CLI output, schema, or lifecycle
  behavior changes.
- **Local-only**: uses repo-local `.ait` state and Git; no network or SaaS.
- **Testable**: each user story maps to deterministic repo/worktree fixtures.

## Project Structure

```text
src/ait/
  cleanup.py                  # cleanup policy, scan, decision, apply logic
  cli/cleanup.py              # command handler
  cli/cleanup_helpers.py      # text/json report formatting
  cli/main.py                 # command dispatch registration
  cli_parser.py               # cleanup flags
  db/core_repositories.py     # attempt list repository helper

tests/
  test_cleanup.py             # cleanup command and core behavior
  test_db_repositories.py     # repository export and ordering coverage

specs/001-worktree-cleanup/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts/cleanup-report.schema.json
  tasks.md
```

## Implementation Phases

### Phase 0 - Research

Resolve the safety and policy decisions that affect implementation:

- which attempt states are removable by default
- how dirty worktrees are detected
- how artifact cleanup is bounded
- where repo-local cleanup config lives

Output: `research.md`.

### Phase 1 - Design

Define the cleanup entities, command contract, JSON report shape, and manual
verification flow.

Outputs:

- `data-model.md`
- `contracts/cleanup-report.schema.json`
- `quickstart.md`

### Phase 2 - Task Planning

Break implementation into ordered tasks grouped by user story and mark any
already-completed work against the current branch state.

Output: `tasks.md`.

### Phase 3 - Implementation

Implement the smallest safe slice first:

- cleanup policy dataclasses and repository read helper
- dry-run scan and report
- apply mode for promoted/discarded clean worktrees
- dirty-worktree protection
- JSON/text CLI output
- repo-local cleanup config

### Phase 4 - Verification

Run targeted tests for cleanup and repositories, then the full suite:

```bash
uv run pytest tests/test_cleanup.py tests/test_db_repositories.py
uv run pytest
git diff --check
```

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Deleting user-owned paths | Resolve every path and require containment under `.ait/workspaces` before deletion. |
| Removing reviewable attempt work | Retain active, pending, and unpromoted succeeded attempts by default. |
| Dirty generated files hide useful source files | Skip dirty worktrees unless `--force` is supplied. |
| Schema drift from duplicate row mapping | Read attempts through `ait.db.list_attempts`. |
| CLI report regressions | Keep formatting in CLI helper and cover JSON/text output in tests. |

## Acceptance Gate

The feature is not complete until every P1 task in `tasks.md` is checked and
the verification commands above pass. P2 artifact-retention work may remain as
a follow-up if P1 cleanup is shipped first, but must remain visible in
`tasks.md`.
