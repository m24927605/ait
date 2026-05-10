# Agent Command Contract

Core agent-facing commands support stable non-interactive operation:

- `ait status --json`
- `ait whereami --json`
- `ait next --json`
- `ait apply --json`
- `ait recover --json`
- `ait reconcile --json`
- `ait review --json`
- `ait review report --format json`
- `ait merge --json`

## Common Flags

- `--json`: alias for `--format json`
- `--format json|text`: select machine or human output where supported
- `--no-interactive`: declare that the command must not prompt
- `--dry-run`: plan without changing Git or AIT state where applicable

## Exit Codes

- `0`: command succeeded, or dry-run plan is valid
- `1`: command was safely blocked or no state transition was possible
- `2`: invalid request, unsafe state, missing repository state, or command error
- `130`: interrupted

## Error JSON

Agent-readable errors use this shape:

```json
{
  "schema_version": 1,
  "status": "error",
  "error_code": "NO_RECORDED_RESULT_BUT_COMMITS_FOUND",
  "message": "No recorded AIT result was found, but this branch has commits ahead of main.",
  "detected_state": {
    "branch": "codex/production-slices",
    "ahead_by": 1,
    "base_branch": "main"
  },
  "user_data_safe": true,
  "blocking_reason": "result metadata is missing",
  "recommended_commands": [
    "ait reconcile --json",
    "ait merge --to main --dry-run --json"
  ],
  "docs_reference": "docs/manual-commit-recovery-workflow.md"
}
```

Commands must not rely on prose-only failures for agent workflows.
