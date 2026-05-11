# Multi-Agent Control Plane

AIT coordinates multiple terminal sessions and coding agents through repo-local
state, isolated Git worktrees, and JSON-first commands. It is intentionally
local-only: metadata lives under `.ait/`, daemon transport is a Unix socket, and
AIT does not require outbound telemetry for coordination.

## Staff Audit Summary

| Capability | Status | Evidence | Notes |
| --- | --- | --- | --- |
| Multiple agents on one intent | Supported | `tests/test_agent_first_workflow.py::test_parallel_agents_same_task_keep_attempt_records_isolated` | Each attempt gets its own DB row, ordinal, lease, and worktree. |
| Concurrent attempt creation | Supported | `tests/test_concurrency.py` | `create_attempt` uses an immediate DB transaction before assigning ordinals. |
| Worktree isolation | Supported | `tests/test_agent_first_workflow.py::test_bad_prompt_mass_rewrite_stays_isolated_with_provenance` | Agent file rewrites stay under `.ait/workspaces/...`; root tracked and untracked files are preserved. |
| Discard one attempt without harming others | Supported | `tests/test_agent_first_workflow.py::test_parallel_agents_same_task_keep_attempt_records_isolated` | Discard removes only that attempt workspace and leaves sibling attempts queryable/promotable. |
| Promote one attempt without workspace pollution | Supported | `tests/test_agent_first_workflow.py::test_parallel_agents_same_task_keep_attempt_records_isolated` | Promotion updates the target ref and does not mutate sibling workspaces or root branch state. |
| Dirty root checkout safety | Supported for merge/apply/promote paths | `tests/test_agent_first_workflow.py::test_merge_blocks_dirty_worktree_with_actionable_json_error`, `tests/test_app_flow.py::test_promote_to_head_branch_refuses_when_main_working_tree_dirty` | Dirty or untracked files block destructive landing actions. |
| Manual workspace commit recovery | Supported | `tests/test_agent_first_workflow.py::test_next_reconcile_and_merge_dry_run_for_manual_workspace_commit` | `ait reconcile --json` materializes synthetic attempt results from workspace commits. |
| Agent decision contract | Supported | `tests/test_agent_first_workflow.py::test_next_json_contract_covers_common_agent_states` | `ait next --json` returns `current_state`, context, safe/unsafe actions, blocking reasons, recovery commands, and a recommended command. `ait whereami --json` and `ait status --json` embed the same `next_action`. |
| Local-only daemon transport | Supported | `tests/test_agent_first_workflow.py::test_local_only_workflow_uses_unix_socket_and_repo_local_metadata` | Daemon status and socket binding use `AF_UNIX`; metadata remains repo-local. |
| Stale running attempt recovery | Supported | `tests/test_daemon_lifecycle.py`, `tests/test_daemon_reaper.py` | Startup and reaper loops mark stale running attempts as crashed/failed after TTL and grace rules. |
| Post-rewrite metadata drift | Partially supported | `tests/test_reconcile.py` | Known post-rewrite mappings are reconciled; unmapped mappings produce a manual repair marker. |
| Concurrent promote/merge to the same branch | Supported for branch ref safety | `tests/test_agent_first_workflow.py::test_parallel_promote_same_target_does_not_silently_overwrite_branch` | Branch ref updates take a repo-local lock and reject attempts whose target changed since their base. |
| Semantic conflict resolution | Not supported | N/A | AIT blocks or holds unsafe states; it does not invent conflict resolutions. |

## Coordination Model

Each attempt has a repo-local DB record and an isolated detached worktree under
`.ait/workspaces/`. A workspace lease records attempt id, intent id, base ref,
owner pid, owner command, state, cleanup policy, and last touch time. Agents can
inspect lease and lineage through `ait whereami --json`, `ait status --json`, and
`ait next --json`.

Mutation follows a dry-run-first contract:

```sh
ait next --json
ait merge --to main --dry-run --json
ait merge --to main --json
```

AIT never stashes user files, deletes untracked root files, or cleans unknown
workspaces by default. Cleanup is conservative and reports skip/remove decisions
before applying them.

## Same-Task Multi-Agent Workflow

1. Create or reuse one intent.
2. Each agent creates its own attempt, either through `ait run` or
   `ait attempt new <intent-id> --agent-id <harness:name>`.
3. Each agent works only inside its assigned workspace.
4. Agents commit through `ait attempt commit` or let `ait run` auto-commit.
5. Review/query attempts independently:

```sh
ait attempt list --intent <intent-id> --format jsonl
ait query --on attempt 'title~"..."' --format jsonl
ait review report --attempt <attempt-id> --format json
```

Discarding one attempt removes only that attempt workspace. Promoting or merging
one attempt does not modify sibling workspaces.

## Safe Promote And Merge

Use `ait merge` for agent-first landing because it emits a machine-readable plan
and actionable JSON errors. Use low-level `ait attempt promote` only when a human
or higher-level agent already selected the attempt and target branch.

```sh
ait whereami --json
ait next --json
ait merge --to main --dry-run --json
ait merge --to main --json
```

Safety rules:

- Current dirty worktree blocks merge.
- Dirty primary worktree blocks merge from AIT workspaces.
- Untracked files are treated as user data and block destructive paths that could
  overwrite or remove them.
- `--dry-run` lists planned Git/AIT operations without mutating state.

## Stale Session Recovery

The daemon reaper marks old running attempts as `reported_status=crashed` and
`verified_status=failed` after the configured TTL. Startup recovery performs the
same check after a grace period so live agents have a chance to heartbeat.

Agents should recover through:

```sh
ait status --json
ait recover latest --json
ait recover latest --retry-apply --json
```

If a workspace exists and contains useful manual commits, run from the workspace:

```sh
ait next --json
ait reconcile --json
```

## Manual Commit Recovery

If an agent commits directly in an AIT workspace, `ait next --json` reports
`manual_commit_without_recorded_result`. The safe loop is:

```sh
ait reconcile --json
ait merge --to main --dry-run --json
ait merge --to main --json
```

Reconcile verifies commits ahead of the attempt base, materializes attempt
commit metadata, marks the attempt as a synthetic successful result, and updates
the workspace lease.

## Agent Loop

Agents should use JSON commands as the control contract:

```sh
ait whereami --json
ait status --json
ait next --json
```

`ait whereami --json` and `ait status --json` embed `next_action`. The
`next_action` payload contains:

- `current_state`
- `detected_context`
- `safe_actions`
- `unsafe_actions`
- `recommended_command`
- `blocking_reasons`
- `recovery_commands`

Execute only commands listed as safe or recommended for the current state. If an
operation returns `status=blocked`, inspect `error.error_code`,
`error.blocking_reason`, and `error.recommended_commands`.

## Known Limitations

- Branch landing uses a local ref lock and expected-base check, but AIT still
  does not choose a winner semantically when two valid attempts target one
  branch. The losing attempt remains reviewable and must be rebased or promoted
  to a new branch.
- AIT does not perform semantic merge conflict resolution.
- Post-rewrite reconciliation is automatic only when mappings are known. Unknown
  mappings require manual repair.
- Cleanup does not remove unknown or dirty state by default; forced cleanup is an
  explicit user decision.

## Safety Guarantees

- No outbound network telemetry is required for AIT coordination.
- Repo metadata is stored under `.ait/`.
- Agent execution happens in isolated attempt worktrees.
- Dirty or untracked user files are not deleted, stashed, or overwritten by
  default.
- JSON errors for agent-facing paths include `error_code`, `message`,
  `detected_state`, `user_data_safe`, `blocking_reason`,
  `recommended_commands`, and `docs_reference`.
