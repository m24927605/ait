# Contract: Local Artifact Reconciliation JSON

Commands that land or materialize accepted attempt work may include a
`local_artifacts` object in their existing JSON response.

## Object Shape

```json
{
  "local_artifacts": {
    "detected": ["string"],
    "copied": [
      {
        "path": "string",
        "action": "copy",
        "reason": "string",
        "destination": "string"
      }
    ],
    "skipped": [
      {
        "path": "string",
        "action": "skip",
        "reason": "string",
        "destination": null
      }
    ],
    "pending": [
      {
        "path": "string",
        "action": "pending",
        "reason": "string",
        "destination": "string"
      }
    ],
    "blocked": [
      {
        "path": "string",
        "action": "blocked",
        "reason": "string",
        "destination": null
      }
    ],
    "cleanup_allowed": false
  }
}
```

## Compatibility

- Existing response keys remain unchanged.
- `local_artifacts` is additive.
- `worktree_cleaned` may be `false` when pending or blocked local artifacts
  require retaining the worktree.
- Paths are repository-relative POSIX paths.
- Reasons are concise and stable enough for users, but automation should key on
  `action` rather than exact reason text.
