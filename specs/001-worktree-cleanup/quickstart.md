# Quickstart: Worktree Cleanup Policy

## Inspect Cleanup Candidates

From an initialized AIT repository:

```bash
ait cleanup
```

Expected behavior:

- command runs in dry-run mode
- no files are deleted
- report lists removable, retained, and skipped worktrees
- report includes estimated reclaimable bytes

## Produce JSON For Automation

```bash
ait cleanup --format json
```

Expected behavior:

- output matches `contracts/cleanup-report.schema.json`
- `mode` is `dry-run`
- each item includes `action`, `reason`, `dirty`, `bytes`, and `deleted`

## Apply Safe Worktree Cleanup

```bash
ait cleanup --apply
```

Expected behavior:

- clean promoted/discarded attempt worktrees are removed
- active, pending, and unpromoted succeeded attempts are retained
- dirty removable worktrees are skipped
- `git worktree prune` runs after successful worktree removal

## Override Failed Attempt Retention

```bash
ait cleanup --older-than 30
```

Expected behavior:

- failed/crashed attempts are retained unless their end/heartbeat/start
  timestamp is at least 30 days old

## Configure Repo-Local Defaults

Edit `.ait/config.json`:

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

Expected behavior:

- CLI flags override repo-local config for one invocation
- invalid nested artifact names are ignored

## Verification Commands

```bash
uv run pytest tests/test_cleanup.py tests/test_db_repositories.py
uv run pytest
git diff --check
```
