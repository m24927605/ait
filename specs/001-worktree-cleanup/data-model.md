# Data Model: Worktree Cleanup Policy

## CleanupPolicy

Effective cleanup policy after merging defaults, repo-local config, and CLI
flags.

Fields:

- `apply: bool` - whether deletion is allowed.
- `force: bool` - whether dirty removable worktrees may be removed.
- `older_than_days: int` - retention threshold for failed/crashed attempts.
- `include_orphans: bool` - whether unmatched AIT workspace directories may be removed.
- `worktrees: bool` - whether worktree cleanup is enabled.
- `artifacts: bool` - whether allowlisted artifact cleanup is enabled.
- `artifact_allowlist: tuple[str, ...]` - path names eligible for artifact cleanup.

Validation:

- `older_than_days` must be zero or greater.
- Artifact allowlist entries must be simple path names, not nested paths.

## CleanupCandidate

Internal path selected for evaluation.

Fields:

- `path: Path`
- `kind: worktree | artifact | orphan`
- `attempt: AttemptRecord | None`
- `bytes: int`

Rules:

- Candidate paths must resolve under `.ait/workspaces`.
- Attempt-backed candidates are matched by resolved `workspace_ref`.
- Orphans are directories under `.ait/workspaces` with no matching attempt row.

## CleanupDecision

Computed action for a candidate before optional deletion.

Fields:

- `action: remove | retain | skip`
- `reason: string`
- `dirty: bool`

Decision rules:

- `created` or `running` attempts: `retain`, reason `active`.
- `pending` attempts: `retain`, reason `pending`.
- `promoted` or `discarded` attempts: `remove`.
- `succeeded` attempts: `retain`, reason `reviewable`.
- stale failed/crashed attempts: `remove`, reason `stale-failed`.
- failed/crashed attempts inside retention: `retain`, reason `retention-window`.
- dirty removable worktree without `force`: `skip`, reason `dirty`.
- orphan without `include_orphans`: `skip`, reason `unknown-attempt`.

## CleanupItem

Serializable report item.

Fields:

- `path: string`
- `kind: worktree | artifact | orphan`
- `attempt_id: string | null`
- `reported_status: string | null`
- `verified_status: string | null`
- `action: remove | retain | skip`
- `reason: string`
- `dirty: bool`
- `bytes: int`
- `deleted: bool`
- `error: string | null`

## CleanupReport

Top-level report returned by cleanup core and rendered by the CLI.

Fields:

- `mode: dry-run | apply`
- `repo_root: string`
- `workspaces_root: string`
- `scanned_count: int`
- `remove_count: int`
- `skip_count: int`
- `reclaimed_bytes: int`
- `would_reclaim_bytes: int`
- `items: CleanupItem[]`

## Existing Entities Used

### AttemptRecord

Cleanup reads existing attempt fields:

- `id`
- `workspace_ref`
- `started_at`
- `ended_at`
- `heartbeat_at`
- `reported_status`
- `verified_status`

No schema migration is required for the first cleanup slice.
