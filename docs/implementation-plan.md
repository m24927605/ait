# AI VCS Implementation Plan

## Purpose

This document turns the frozen v1 spec into an execution plan.

It is intentionally delivery-oriented:

- define implementation milestones
- define dependency order
- define acceptance criteria
- reduce kickoff ambiguity

## Implementation Strategy

Build the system in the same order that risk appears in the architecture:

1. persistence and schema
2. attempt creation and workspace setup
3. daemon ingestion and protocol handling
4. query and inspection
5. verification and cleanup

This keeps the team from overbuilding protocol or CLI features before the core state model is real.

## Milestone Overview

### M1: Persistence And Attempt Bootstrap

Goal:

- make the core objects real
- initialize local state
- create attempts in isolated worktrees

Primary deliverables:

- SQLite schema and migration runner
- `.ait/` local directory bootstrap
- local config creation with `install_nonce`
- `ait init`
- `ait intent new`
- `ait attempt new`
- worktree provisioning
- ownership token issuance

Acceptance criteria:

1. running `ait init` creates:
   - `.ait/`
   - `.ait/objects/`
   - local config
   - SQLite database
2. `.ait/` is added to `.gitignore` if missing
3. `ait intent new` persists an `Intent`
4. `ait attempt new <intent-id>`:
   - persists an `Attempt`
   - allocates monotonic `ordinal`
   - creates a worktree
   - records `base_ref_oid`
   - returns `attempt_id`, `workspace_ref`, `base_ref_oid`, `ownership_token`
5. repeated `ait attempt new` under one intent creates multiple concurrent attempts cleanly

Suggested implementation order:

1. schema definitions
2. migration runner
3. config loader
4. repo identity generation
5. `ait init`
6. `Intent` creation
7. `Attempt` creation
8. worktree adapter

Open implementation choices to settle in M1:

- SQLite library choice
- config file format
- worktree directory naming
- ownership token encoding format

### M2: Daemon Ingest And Evidence Accumulation

Goal:

- make harness integration real
- ingest protocol events safely
- populate evidence summaries incrementally

Primary deliverables:

- daemon process
- Unix socket transport
- newline-delimited JSON protocol handling
- `event_id` dedupe
- `ownership_token` validation
- handlers for:
  - `attempt_started`
  - `attempt_heartbeat`
  - `tool_event`
  - `attempt_finished`
  - `attempt_promoted`
  - `attempt_discarded`
- event-to-summary accumulation
- file path accumulation into:
  - `files_read`
  - `files_touched`

Acceptance criteria:

1. daemon starts and exposes the configured socket path
2. duplicate events with the same `event_id` are ignored
3. invalid `ownership_token` rejects lifecycle-mutating events
4. `tool_event` updates:
   - `observed.tool_calls`
   - `observed.file_reads`
   - `observed.file_writes`
   - `observed.commands_run`
5. `tool_event.files[]` correctly updates `evidence_files`
6. `attempt_finished` stores refs and moves `reported_status` to `finished`
7. daemon restart preserves state and can resume from SQLite

Suggested implementation order:

1. daemon lifecycle
2. socket server
3. message envelope validation
4. idempotency table or event log
5. token validation
6. event handlers
7. evidence accumulation
8. daemon restart recovery

Open implementation choices to settle in M2:

- whether to persist a raw event log
- where to keep dedupe state
- how aggressively to fsync writes

### M3: Query, Verification, And Cleanup

Goal:

- make the system inspectable
- verify attempts deterministically
- clean up dead executions

Primary deliverables:

- query parser for the v1 DSL
- query planner over whitelisted fields
- `ait query --on <intent|attempt>`
- `ait intent list`
- `ait attempt list`
- `ait blame`
- verifier for `succeeded` and `promoted`
- reaper loop
- daemon startup recovery
- post-rewrite reconciliation hook installation

Acceptance criteria:

1. `ait query --on attempt 'observed.tool_calls>0'` returns correct rows
2. `ait query --on intent 'kind="bugfix"'` uses intent-subject semantics
3. `ait blame <path>` resolves through indexed metadata, not full blob scans
4. verifier can move:
   - `pending -> succeeded`
   - `succeeded -> promoted`
   - `pending -> failed`
5. reaper marks stale running attempts as `crashed` and `failed`
6. daemon startup recovery handles stale running attempts
7. rewrite hook installation completes during `ait init`
8. rewritten commits update `attempt_commits` or surface a stale-linkage warning

Suggested implementation order:

1. whitelist field registry
2. minimal parser
3. SQL lowering
4. query output formatting
5. verifier
6. reaper loop
7. startup recovery
8. rewrite hook installer

Open implementation choices to settle in M3:

- parser implementation style
- whether `ait blame` is built as a direct query or dedicated read path
- stale linkage surfacing UX

## Work Breakdown By Area

### Persistence

Responsibilities:

- database schema
- migrations
- object repositories
- config persistence
- blob ref helpers

Core tables:

- `meta`
- `intents`
- `attempts`
- `evidence_summaries`
- `intent_edges`
- `attempt_commits`
- `evidence_files`

### Workspace

Responsibilities:

- create worktrees
- derive `base_ref_oid`
- clean up discarded attempts
- map attempt ID to worktree path

### Daemon

Responsibilities:

- socket lifecycle
- protocol parsing
- dedupe
- token validation
- event dispatch
- reaper
- startup recovery

### Verifier

Responsibilities:

- determine `succeeded`
- determine `promoted`
- materialize `files_changed`
- confirm promotion ref movement

### Query

Responsibilities:

- parse DSL
- validate whitelist fields
- lower to SQL
- format results
- power `intent list`, `attempt list`, and `blame`

### Git Integration

Responsibilities:

- commit trailer conventions
- hook installation
- rewrite reconciliation
- branch/ref verification

## Recommended Team Split

If multiple people are implementing in parallel, use this ownership split:

1. persistence + config + migrations
2. workspace + attempt bootstrap + Git integration
3. daemon + protocol + event handling
4. query + CLI + blame
5. verifier + reaper + startup recovery

This split minimizes overlap on the same files if the codebase is structured by module.

## Suggested Repository Skeleton

One reasonable skeleton:

```text
src/
  cli/
  config/
  daemon/
  db/
  git/
  model/
  query/
  verifier/
  workspace/
```

Support directories:

```text
docs/
  ai-vcs-mvp-spec.md
  implementation-notes.md
  protocol-appendix.md
  implementation-plan.md
```

## Definition Of Done For V1

V1 is done when all of the following are true:

1. a user can initialize `.ait/` in a Git repository
2. a user can create an intent
3. a harness can create an attempt and receive an ownership token
4. the daemon can ingest protocol events
5. evidence summaries are materialized and queryable
6. commit linkage is queryable through `attempt_commits`
7. `ait query` and `ait blame` work on real data
8. stale attempts are failed by the reaper
9. promotion is verified against real Git refs
10. local rewrite reconciliation does not silently corrupt metadata

## Immediate Next Actions

The next concrete steps should be:

1. choose implementation language and SQLite library
2. define the initial SQLite schema in code
3. scaffold `ait init`
4. scaffold `ait attempt new`
5. scaffold the daemon envelope parser

Do not start with the full query DSL or advanced hook behavior before M1 is real.
