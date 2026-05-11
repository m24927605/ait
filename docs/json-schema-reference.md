# JSON Schema Reference

All schemas are versioned with `schema_version: 1`.

## `ait whereami --json`

Required top-level fields:

- `current_state`
- `repo_root`
- `cwd`
- `worktree`
- `primary_worktree`
- `target_branch`
- `target_ref`
- `base_branch`
- `attempt`
- `commits_ahead_of_base`
- `ahead_by`
- `blocking_reasons`
- `recovery_commands`
- `detected_context`

`detected_context` is the compact state object agents should pass through logs
and error handling. It includes `is_primary_worktree`, `is_ait_workspace`,
`attempt_id`, `current_branch`, `base_branch`, `target_branch`, `ahead_by`,
`remote_tracking_branch`, `result_metadata_exists`, and
`manual_commits_can_be_synthetic`.

`next_action` is also present and uses the same decision payload shape as
`ait next --json`.

## `ait next --json`

Required fields:

- `current_state`
- `detected_context`
- `safe_actions`
- `unsafe_actions`
- `recommended_command`
- `alternative_commands`
- `blocking_reasons`
- `recovery_commands`
- `explanation`

## `ait status --json`

`ait status --json` includes adapter, memory, daemon, and recovery dashboard
fields. For agent decision-making it also includes:

- `agent_state`: the same state payload shape returned by `ait whereami --json`
- `next_action`: the same decision payload shape returned by `ait next --json`

## `ait reconcile --json`

Required fields:

- `processed_mappings`
- `updated_commit_rows`
- `updated_base_rows`
- `unmapped_mappings`
- `manual_repair_required`
- `synthetic_result_created`
- `attempt_id`
- `commit_oids`
- `changed_files`
- `blocking_reason`
- `detected_context`

## `ait merge --json`

Required fields:

- `status`: `planned`, `merged`, or `blocked`
- `mode`: `auto`, `apply`, `ff-only`, or `merge`
- `dry_run`
- `target_branch`
- `target_ref`
- `source_ref`
- `current_state`
- `detected_context`
- `operations`
- `blocking_reasons`
- `recommended_commands`
- `message`
- `apply`
- `pushed`
- `error`

Each operation includes `kind`, `command`, `cwd`, and `will_execute`.

## `ait review report --format json`

Required fields:

- `attempt_id`
- `base_commit`
- `head_commit`
- `changed_files`
- `commands_executed`
- `tests_run`
- `review_agents`
- `reviews`
- `findings_by_severity`
- `findings`
- `fixes_applied`
- `final_approval_status`
- `residual_risks`
