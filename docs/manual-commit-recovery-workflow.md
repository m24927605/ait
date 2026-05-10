# Manual Commit Recovery Workflow

Agents sometimes commit directly inside an AIT workspace. That is recoverable.

Detection:

```sh
ait whereami --json
ait next --json
```

If `current_state` is `manual_commit_without_recorded_result`, run:

```sh
ait reconcile --json
```

AIT will:

- locate the attempt associated with the current `.ait/workspaces/...` worktree
- verify commits ahead of the attempt base
- materialize `attempt_commits`
- mark the attempt as a finished synthetic result
- update the workspace lease to `succeeded`

Then validate landing:

```sh
ait merge --to main --dry-run --json
```

If the dry-run is clean:

```sh
ait merge --to main --push --json
```

If dirty files are present, AIT returns an actionable JSON error and does not
modify user data.
