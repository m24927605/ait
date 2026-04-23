# AI VCS Implementation Notes

## Purpose

This document captures non-blocking limitations, implementation edge rules, and first-sprint clarifications for the v1 AI-agent-native VCS spec.

It exists to prevent kickoff-week ambiguity without expanding the frozen MVP surface.

## Known Limitations

The following limitations are accepted in v1:

1. Different local clones of the same repository will produce different `repo_id` values because `install_nonce` is local.
2. Commit trailers may reference `Intent-Id` values that are not resolvable on another machine.
3. Local rewrite reconciliation is intended for common local rewrites such as `rebase` and `commit --amend`. More destructive history changes such as `reset --hard` and `filter-branch` may require manual reconciliation.
4. Daemon transport does not provide process-level authentication in v1. Local write protection relies on `ownership_token`.
5. The `~` query operator is case-sensitive in v1.
6. Harnesses may misclassify `tool_event.category`, which can skew `observed.*` counters.
7. Raw prompt blobs may contain secrets. V1 does not perform redaction automatically.
8. Schema migration is not automated in v1.

## Required Local Defaults

The following local defaults must be applied by `ait init`:

1. Create `.ait/`
2. Create `.ait/objects/`
3. Create local config containing:
   - `install_nonce`
   - daemon socket path
   - reaper TTL override, if any
4. Add `.ait/` to `.gitignore` if not already ignored

## Lifecycle Clarifications

### Intent Status Is Forward-Only

Intent status transitions are **forward-only**. Once an intent reaches
`running`, it must never regress to `open`, even if every child attempt ends
as `failed` or `discarded`. Terminal statuses (`finished`, `abandoned`,
`superseded`) are never mutated by automatic refresh.

The single source of truth is `ait.lifecycle.refresh_intent_status`. All
callers (event handlers, verifier, CLI flows) must route through it rather
than computing intent status inline.

Allowed automatic transitions:

- `open -> running`: any child attempt reaches `reported_status = running`
- `open -> finished` or `running -> finished`: any child attempt reaches `verified_status = promoted`

Disallowed transitions (must be rejected or no-op):

- `running -> open`
- any automatic transition out of `finished`, `abandoned`, or `superseded`

### Attempt Success vs Promotion

`verified_status=succeeded` means:

- the attempt completed
- expected artifacts exist
- verification checks passed
- but the result has not yet been promoted to a target branch

`verified_status=promoted` means:

- the attempt already satisfied `succeeded`
- and the verifier confirmed that the target Git ref moved to include the intended commit set

### Abandoning An Intent

If a user runs:

```bash
ait intent abandon <intent-id>
```

Then:

1. the intent status becomes `abandoned`
2. no new attempts may be created under that intent
3. existing running attempts are not force-killed by `ait`
4. later lifecycle events from those attempts are still recorded
5. a promoted result under an abandoned intent must be rejected by the verifier unless the intent is reopened or superseded

This avoids daemon-side process management scope creep in v1 while keeping lifecycle behavior deterministic.

### Daemon Restart Recovery

On daemon startup:

1. load all attempts where `reported_status='running'`
2. compare `heartbeat_at` against the configured TTL
3. if stale, mark them `crashed` and `failed`
4. if not stale, leave them `running` and wait for the next heartbeat or finished event

This recovery path is required in addition to the periodic reaper loop.

## CLI Clarifications

### `ait intent list`

`ait intent list` is a shortcut over `ait query --on intent`.

Supported flags in v1:

- `--status <status>`
- `--kind <kind>`
- `--tag <tag>`
- `--limit <n>`
- `--offset <n>`
- `--format <table|jsonl>`

Equivalent lowering rules:

- `--status X` => `status="X"`
- `--kind X` => `kind="X"`
- `--tag X` => `tags~"X"`

### `ait attempt list`

`ait attempt list` is a shortcut over `ait query --on attempt`.

Supported flags in v1:

- `--intent <intent-id>`
- `--reported-status <status>`
- `--verified-status <status>`
- `--agent <agent-id>`
- `--limit <n>`
- `--offset <n>`
- `--format <table|jsonl>`

## Git Rewrite Handling Notes

### Hook Installation

`ait init` must install or update local Git hooks needed by v1.

For rewrite reconciliation, v1 uses:

- `post-rewrite`

Installation strategy:

1. if `core.hooksPath` is not set, install into `.git/hooks/`
2. if `core.hooksPath` is set, install into that directory
3. if an existing hook is present, append or chain rather than overwrite when possible

### Manual Reconciliation

If automatic rewrite reconciliation fails, the implementation must surface the repository as needing manual repair.

The intended follow-up command is:

```bash
ait reconcile
```

This command is not required to be fully implemented in v1, but the failure mode must be visible to the user.

## First Sprint Priority

The following implementation questions should be answered before parallel work begins:

1. how `tool_event` carries file path information
2. exact `attempt_finished` event payload
3. exact `ownership_token` issuance and transport flow
4. daemon socket path default and override rules
5. concrete `post-rewrite` hook script behavior
6. verifier transition logic from `succeeded` to `promoted`
