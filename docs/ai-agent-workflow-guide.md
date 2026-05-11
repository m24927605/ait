# AI Agent Workflow Guide

AIT is designed to be driven by coding agents without interactive prompts. Agents
should treat AIT as a development control plane: inspect state, select a legal
next action, execute it, then record review and merge evidence.

For multi-agent coordination, leases, stale-session recovery, and safety
guarantees, see [`docs/multi-agent-control-plane.md`](multi-agent-control-plane.md).

## Standard Agent Loop

1. `ait whereami --json`
2. `ait status --json`
3. `ait next --json`
4. Execute the `recommended_command`
5. Run project tests
6. `ait review attempt latest-reviewable --format json`
7. `ait review report --format json`
8. `ait merge --to main --dry-run --json`
9. `ait merge --to main --push --json`

Agents should prefer `--json`, `--no-interactive`, and `--dry-run` when
planning a state transition. Text output is for humans; JSON output is the
contract for automation.

## State First

Use `ait whereami --json` to answer:

- whether the current directory is the primary worktree or an AIT workspace
- the current attempt id, if any
- current, base, target, and remote tracking branches
- commits ahead of the attempt base
- whether result metadata exists
- whether manual commits can be reconciled into a synthetic AIT result

Use `ait next --json` to avoid guessing. The response contains safe actions,
unsafe actions, blocking reasons, recovery commands, and one recommended command.
`ait whereami --json` and `ait status --json` embed the same decision payload as
`next_action` for agents that need context or dashboard calls.

## Manual Commit Recovery

If an agent commits directly inside `.ait/workspaces/...`, AIT can reconcile the
commit into the attempt lineage:

```sh
ait next --json
ait reconcile --json
ait merge --to main --dry-run --json
ait merge --to main --push --json
```

AIT will not overwrite local edits, delete untracked files, or stash user data.
Dirty worktrees block merge and apply until the agent or user resolves them.
