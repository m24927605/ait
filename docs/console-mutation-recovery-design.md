# Console Mutation Recovery Design

## Purpose

`ait console --read-only` solves discoverability, but not daily operation. This
design defines the gate for adding console actions without weakening AIT's
existing Git semantics.

The goal is not to turn the console into an independent Git UI. The goal is to
let the console trigger the same domain operations already exposed by the CLI,
with explicit preflight checks, an action journal, and recovery behavior.

## Implementation Status

Implemented as a CLI action-layer gate, not as browser mutation UI:

- `src/ait/console_actions.py` provides dry-run/preflight planning for
  apply/recover/discard.
- `ait console action apply|recover|discard --attempt <id> --dry-run --format json`
  emits versioned `ait.console_action` payloads.
- Every dry-run or blocked action appends a local JSONL journal entry under
  `.ait/actions/console-actions.jsonl`.
- Non-dry-run execution is intentionally not enabled from this layer yet; the
  payload points users back to the existing CLI/domain command.
- Browser action mode, CSRF endpoints, execution, retry links, and
  review-finding mutation remain follow-up work.

## Non-goals

- No automatic push, merge, or branch publication.
- No SaaS, telemetry, account system, or remote dashboard.
- No direct mutation of Git, SQLite, or worktree files from browser UI code.
- No mutation mode by default. `ait console --read-only` remains the default.

## User-facing model

The intended console gets two modes:

| Mode | Command | Behavior |
| --- | --- | --- |
| Read-only | `ait console --read-only` | Writes or serves static HTML; no action buttons. |
| CLI action dry-run | `ait console action apply|recover|discard --dry-run` | Local preflight and journal contract; does not execute mutation. |
| Future action mode | `ait console --serve-local --actions` | Loopback-only local server with explicit action endpoints and CSRF token. |

Action mode must show a visible "Action mode" state and the active repo path.
Every action must present a dry-run/preflight result before execution.

## Action boundary

Console actions call an internal action layer. The action layer calls existing
domain operations or CLI-equivalent functions.

Allowed first actions:

| Action | Existing semantic owner | Required preflight |
| --- | --- | --- |
| `apply_attempt` | `ait apply` / apply domain path | repo initialized, attempt exists, attempt succeeded/promoted, review not blocked, root dirty state policy satisfied |
| `recover_attempt` | `ait recover` / recovery domain path | attempt exists, workspace exists, target path safe, no conflicting recovery target |
| `discard_attempt` | `ait discard` / discard domain path | attempt exists, action confirmation, workspace not current root |
| `update_review_finding` | review finding repository/domain path | finding exists, allowed status transition, actor label recorded |

The console must not import low-level Git helpers and mutate refs directly.

## Action journal

Every mutation attempt writes an append-only JSONL journal under:

```text
.ait/actions/console-actions.jsonl
```

Schema:

```json
{
  "schema": "ait.console_action",
  "schema_version": 1,
  "action_id": "act_...",
  "repo_id": "repo_...",
  "actor_label": "local-user",
  "action": "apply_attempt",
  "target": {
    "attempt_id": "..."
  },
  "preflight": {
    "status": "passed",
    "checks": [
      {"name": "review_gate", "status": "passed", "message": ""}
    ]
  },
  "domain_command": ["ait", "apply", "..."],
  "started_at": "2026-05-16T00:00:00Z",
  "ended_at": "2026-05-16T00:00:01Z",
  "status": "succeeded",
  "error": null,
  "rollback_hint": null,
  "before": {
    "head": "...",
    "branch": "main",
    "dirty": false
  },
  "after": {
    "head": "...",
    "branch": "main",
    "dirty": false
  }
}
```

The journal is local metadata. It is not synchronized or uploaded.

## Failure and recovery rules

- Preflight failure records a `blocked` action journal entry and does not call
  the domain operation.
- Domain operation failure records `failed`, captures the error summary, and
  gives a rollback or retry hint.
- Retry is explicit and creates a new action entry linked to the previous
  `action_id`.
- A partially completed domain operation must be recoverable through the same
  CLI/domain recovery path that a terminal user would use.
- The console must never hide a held review, dirty repo, missing workspace, or
  failed action.

## Implementation plan

1. Add `src/ait/console_actions.py` with:
   - `ConsoleActionRequest`
   - `ConsoleActionResult`
   - `run_console_action(request, repo_root)`
   - preflight helpers
   - journal writer
2. Add a schema v1 golden fixture:
   - `tests/fixtures/console_action/schema_v1_contract.json`
3. Add CLI smoke commands before browser mutation:
   - `ait console action apply --attempt ... --dry-run --format json`
   - `ait console action recover --attempt ... --dry-run --format json`
   - `ait console action discard --attempt ... --dry-run --format json`
4. Add local server action endpoints only after CLI action tests pass and
   execution/retry behavior is implemented:
   - `POST /actions/apply`
   - `POST /actions/recover`
   - `POST /actions/discard`
   - `POST /actions/review-finding`
5. Add action-mode HTML controls only when `--actions` is passed.

## Tests

Required tests before enabling action mode:

- Schema contract test for `ait.console_action`.
- CLI JSON smoke for every action and dry-run mode.
- Dirty root apply preflight blocks without modifying root.
- Held review blocks apply.
- Missing attempt returns structured error and journal entry.
- Domain failure records `failed` and retry hint.
- Future successful apply/recover/discard execution must call existing domain
  paths, not direct Git mutation from console code.
- `--serve-local --actions --host 0.0.0.0` is rejected.
- HTML in read-only mode contains no action endpoints or `data-action`.

## Acceptance

Browser action mode is acceptable only when:

- `ait console --read-only` remains read-only and unchanged.
- `ait console --serve-local --actions` is loopback-only.
- Every mutation has preflight, confirmation, journal, and structured result.
- Failed actions are visible in graph/console data.
- No public docs imply automatic merge, push, or remote sync.

## Code Review Standard

Reviewers must block any console mutation PR that:

- writes Git refs, SQLite rows, or worktree contents directly from UI/server
  handlers instead of using the domain layer;
- lacks a journal entry for a mutation path;
- lacks a failure-path test;
- exposes action mode on non-loopback hosts;
- makes read-only mode render mutation controls;
- weakens review/apply gate semantics.
