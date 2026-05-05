# Feature Specification: Worktree Cleanup Policy

**Feature Branch**: `001-worktree-cleanup`
**Created**: 2026-05-05
**Status**: Complete
**Input**: User description: "AIT can make project folders grow under a worktree architecture; define a cleanup strategy as a spec-kit spec."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect Cleanup Impact (Priority: P1)

As an AIT user, I want to see which attempt worktrees and generated artifacts are taking disk space before anything is deleted, so that I can make an informed cleanup decision without risking unreviewed work.

**Why this priority**: Cleanup must be trustworthy before it is automated. The main failure mode is deleting useful attempt state.

**Independent Test**: Run cleanup in dry-run mode on a repo with promoted, discarded, failed, and active attempts. The command reports reclaimable paths, sizes, reasons, and skipped paths without deleting files.

**Acceptance Scenarios**:

1. **Given** a repo with AIT worktrees under `.ait/workspaces`, **When** the user runs `ait cleanup`, **Then** AIT prints a dry-run report and exits without deleting anything.
2. **Given** a worktree with uncommitted or untracked files, **When** cleanup evaluates it, **Then** the report marks it as skipped unless the user explicitly supplies `--force`.
3. **Given** an active or running attempt, **When** cleanup evaluates it, **Then** the worktree is always skipped.

---

### User Story 2 - Remove Safe Terminal Worktrees (Priority: P1)

As an AIT user, I want promoted and discarded attempt worktrees to be removed safely, so that AIT does not keep unnecessary full working copies after their lifecycle is complete.

**Why this priority**: Promoted and discarded attempts have explicit terminal meaning. They are the safest default cleanup target.

**Independent Test**: Create promoted and discarded attempts with worktrees present. Run `ait cleanup --apply`. Their worktrees are removed with `git worktree remove --force`, AIT-owned sidecar metadata is removed, and `git worktree prune` is run.

**Acceptance Scenarios**:

1. **Given** an attempt with `verified_status=promoted`, **When** the user runs `ait cleanup --apply`, **Then** AIT removes the attempt worktree and sidecar Python environment metadata.
2. **Given** an attempt with `verified_status=discarded`, **When** the user runs `ait cleanup --apply`, **Then** AIT removes the attempt worktree and records it as reclaimed in the report.
3. **Given** a promoted attempt whose worktree path is already gone, **When** cleanup runs, **Then** AIT treats the missing path as already clean and still runs Git worktree pruning.

---

### User Story 3 - Retain Reviewable Attempts (Priority: P2)

As an AIT user, I want succeeded, failed, or crashed attempts to remain available for review until an explicit retention rule says otherwise, so that cleanup does not erase debugging or promotion context too early.

**Why this priority**: AIT's value is reviewable attempts. Disk cleanup must not silently weaken that workflow.

**Independent Test**: Create succeeded, failed, and crashed attempts newer than the default retention window. Run `ait cleanup --apply`. Their worktrees remain intact and the report explains the retention reason.

**Acceptance Scenarios**:

1. **Given** a `succeeded` attempt that has not been promoted, **When** cleanup runs, **Then** its worktree is retained by default.
2. **Given** a failed or crashed attempt newer than the configured failed-attempt retention window, **When** cleanup runs, **Then** its worktree is retained.
3. **Given** a failed or crashed attempt older than the configured retention window and clean according to Git, **When** cleanup runs with `--apply`, **Then** AIT may remove the worktree.

---

### User Story 4 - Bound Artifact Growth (Priority: P2)

As an AIT user, I want AIT to identify and optionally clean generated dependency/build artifacts inside stale attempt worktrees, so that `node_modules`, `.venv`, `.next`, `dist`, and cache directories do not multiply indefinitely.

**Why this priority**: Git worktree metadata is usually shared, but dependency and build outputs are duplicated per worktree and are the primary disk-growth risk.

**Independent Test**: Add common generated directories inside stale terminal worktrees. Run cleanup in dry-run and apply modes. AIT reports artifact size separately and deletes only allowlisted generated paths.

**Acceptance Scenarios**:

1. **Given** a stale terminal attempt worktree with `node_modules`, `.next`, `dist`, `build`, `.pytest_cache`, or `.venv`, **When** cleanup runs, **Then** these paths appear in an artifact section with size estimates.
2. **Given** artifact cleanup is applied, **When** a generated path is not in the allowlist, **Then** AIT does not delete it.
3. **Given** a live reviewable attempt, **When** cleanup runs, **Then** artifact cleanup is skipped unless the user explicitly targets artifact-only cleanup.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST provide a cleanup command that defaults to dry-run behavior.
- **FR-002**: The cleanup command MUST require `--apply` before deleting any file, directory, Git worktree registration, sidecar environment metadata, or dev-server record.
- **FR-003**: AIT MUST only consider worktrees located under the repository's AIT-owned `.ait/workspaces` directory.
- **FR-004**: AIT MUST match candidate worktrees to attempt records before applying status-based cleanup.
- **FR-005**: AIT MUST skip active attempts whose `reported_status` is `created` or `running`.
- **FR-006**: AIT MUST skip attempts whose `verified_status` is `pending` unless the worktree is an orphan that has no matching attempt record and the user explicitly uses an orphan cleanup option.
- **FR-007**: AIT MUST remove `promoted` and `discarded` attempt worktrees by default when `--apply` is supplied.
- **FR-008**: AIT MUST retain unpromoted `succeeded` attempts by default.
- **FR-009**: AIT MUST retain failed or crashed attempts for at least the configured retention window; the default retention window MUST be 14 days.
- **FR-010**: AIT MUST skip any candidate worktree with uncommitted tracked changes or untracked files unless `--force` is supplied.
- **FR-011**: AIT MUST run the existing dev-server cleanup for a worktree before removing that worktree.
- **FR-012**: AIT MUST clean AIT-owned sidecar Python environment metadata for a removed worktree.
- **FR-013**: AIT MUST run `git worktree prune` after removing one or more worktrees.
- **FR-014**: AIT MUST report skipped candidates with a concrete reason such as `active`, `reviewable`, `dirty`, `outside-ait-root`, `retention-window`, or `unknown-attempt`.
- **FR-015**: AIT MUST estimate and report disk usage for each candidate path in dry-run and apply modes.
- **FR-016**: AIT MUST expose machine-readable cleanup output with `--format json`.
- **FR-017**: AIT MUST support configuration for failed/crashed retention days, artifact cleanup allowlist, and whether cleanup may include orphaned AIT workspaces.
- **FR-018**: AIT MUST NOT delete paths outside `.ait/workspaces` through worktree cleanup.
- **FR-019**: AIT MUST NOT delete non-allowlisted generated artifacts through artifact cleanup.
- **FR-020**: AIT MUST make cleanup idempotent; rerunning cleanup after a successful apply should report already-clean or no-op results, not fail.

### Command Surface

Primary command:

```bash
ait cleanup [--apply] [--force] [--format text|json]
            [--older-than DAYS]
            [--include-orphans]
            [--artifacts]
            [--worktrees]
```

Defaults:

- dry-run unless `--apply` is present
- `--worktrees` enabled
- `--artifacts` disabled for live worktrees and enabled only as part of stale terminal worktree cleanup
- `--older-than 14` for failed or crashed terminal attempts
- `--format text`
- `--include-orphans` disabled

Exit codes:

- `0`: cleanup completed or dry-run completed
- `1`: cleanup completed with one or more recoverable deletion failures
- `2`: invalid arguments, not an AIT repo, or unsafe path detection failure

### Default Cleanup Policy

| Attempt state | Default action | Reason |
| --- | --- | --- |
| `reported_status=created` or `running` | retain | active or possibly active |
| `verified_status=pending` | retain | not yet verified |
| `verified_status=succeeded` and not promoted | retain | still reviewable/promotable |
| `verified_status=promoted` | remove on `--apply` | change has reached target ref |
| `verified_status=discarded` | remove on `--apply` | user explicitly abandoned workspace |
| `verified_status=failed` older than retention window | remove if clean | stale debugging context |
| `reported_status=crashed` older than retention window | remove if clean | stale debugging context |
| unknown/orphan worktree | report only | avoid deleting non-AIT work |

### Artifact Allowlist

Generated artifact cleanup is limited to these path names inside an AIT worktree:

- `.venv`
- `node_modules`
- `.next`
- `.nuxt`
- `.svelte-kit`
- `dist`
- `build`
- `coverage`
- `.coverage`
- `.pytest_cache`
- `.mypy_cache`
- `.ruff_cache`
- `.tox`
- `.turbo`
- `.vite`

The allowlist may be extended by repo-local config, but cleanup must still stay inside the selected AIT worktree.

### Configuration

Repo-local configuration should live under existing AIT config, conceptually:

```json
{
  "cleanup": {
    "failed_retention_days": 14,
    "include_orphans": false,
    "artifact_allowlist": [
      ".venv",
      "node_modules",
      ".next",
      "dist",
      "build",
      "coverage",
      ".pytest_cache"
    ]
  }
}
```

Command-line flags override repo-local configuration for that invocation only.

### Text Report

Example:

```text
AIT Cleanup
Mode: dry-run
Worktrees scanned: 6
Would reclaim: 2.4 GiB

- remove worktree attempt-0002-01abc promoted 1.1 GiB
- remove worktree attempt-0003-01def discarded 820 MiB
- retain worktree attempt-0004-01ghi succeeded reviewable 410 MiB
- skip worktree attempt-0005-01jkl failed dirty 90 MiB

Run with --apply to delete removable paths.
```

### JSON Report

Top-level schema:

```json
{
  "mode": "dry-run",
  "repo_root": "...",
  "workspaces_root": "...",
  "scanned_count": 0,
  "remove_count": 0,
  "skip_count": 0,
  "reclaimed_bytes": 0,
  "would_reclaim_bytes": 0,
  "items": []
}
```

Item schema:

```json
{
  "path": "...",
  "kind": "worktree|artifact|orphan",
  "attempt_id": "...",
  "reported_status": "finished",
  "verified_status": "promoted",
  "action": "remove|retain|skip",
  "reason": "promoted",
  "dirty": false,
  "bytes": 0,
  "deleted": false,
  "error": null
}
```

## Key Entities

- **CleanupPolicy**: Effective policy after merging defaults, repo config, and CLI flags.
- **CleanupCandidate**: A worktree or generated artifact path being evaluated.
- **CleanupDecision**: The computed action and reason for a candidate.
- **CleanupReport**: Text or JSON summary of scanned, removed, retained, skipped, and failed items.

## Edge Cases

- The worktree directory exists but Git no longer lists it.
- Git lists a worktree but the directory was manually deleted.
- The attempt row exists but `workspace_ref` points outside `.ait/workspaces`.
- The attempt has terminal status but contains untracked generated files and untracked source files.
- `du` or platform-specific size calculation fails for a path.
- A dev server is still running from a worktree selected for removal.
- Cleanup is interrupted after Git registration removal but before sidecar metadata deletion.
- Two cleanup commands run concurrently.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In dry-run mode, cleanup deletes zero files across all tests.
- **SC-002**: Promoted and discarded clean worktrees are removed in apply mode with 100% deterministic decisions.
- **SC-003**: Active, pending, and unpromoted succeeded attempts are retained by default.
- **SC-004**: Dirty worktrees are skipped by default and identified in both text and JSON output.
- **SC-005**: Cleanup never removes a path outside `.ait/workspaces` in automated tests.
- **SC-006**: Re-running cleanup after successful apply exits `0` and reports no additional removable worktrees.
- **SC-007**: Artifact cleanup removes only allowlisted generated paths in stale terminal worktrees.

## Implementation Notes

- Reuse `remove_attempt_workspace()` for worktree deletion so dev-server and Python environment cleanup stay centralized.
- Add a lower-level candidate scanner in `ait.workspace` or a dedicated `ait.cleanup` module; avoid putting cleanup decisions directly in the CLI handler.
- Use Git status porcelain from the worktree to detect tracked and untracked dirtiness before deletion.
- Use defensive path checks with resolved paths and parent containment before any deletion.
- Serialize cleanup with the same repo-local locking approach used for attempt lifecycle operations, or add a cleanup-specific lock under `.ait/`.
- Tests should cover both direct library calls and CLI behavior.

## Non-Goals

- No background daemon cleanup in the first slice.
- No deletion of user checkouts outside `.ait/workspaces`.
- No cleanup of Git object database history.
- No semantic decision about whether failed attempt code is valuable.
- No automatic cleanup of unpromoted succeeded attempts.
