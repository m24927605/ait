# Safe Merge Workflow

Use `ait merge` for agent-friendly landing.

```sh
ait merge --to main --dry-run --json
ait merge --to main --push --json
```

Supported modes:

- `auto`: prefer AIT result apply, otherwise fast-forward branch merge
- `apply`: require an AIT attempt result and use AIT apply
- `ff-only`: use `git merge --ff-only`
- `merge`: use a normal Git merge commit when fast-forward is not required

Safety rules:

- dirty current worktrees block merge
- dirty primary worktrees block merge from AIT workspaces
- untracked files are never deleted
- user edits are never stashed or overwritten
- branch ref updates use a local lock and reject stale attempt bases
- `--dry-run --json` lists every Git or AIT operation before execution

If an AIT workspace has commits but no recorded result metadata, run:

```sh
ait reconcile --json
ait merge --to main --dry-run --json
```

With `--push`, AIT pushes the target branch after a successful local merge.
With `--set-default-branch`, AIT records `ait.defaultBranch` in local Git config.

For concurrent agent attempts, leases, and residual landing-lock limitations, see
[`docs/multi-agent-control-plane.md`](multi-agent-control-plane.md).
