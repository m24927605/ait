# AI-Agent-Native VCS MVP Spec

## Overview

This document defines an MVP for an AI-agent-native version control layer built on top of Git.

The v1 goal is not to replace Git storage, branching, or commit mechanics. The goal is to add the missing primitives needed for AI-agent coding workflows:

- structured intent tracking
- isolated attempts
- queryable execution history
- durable linkage between attempts and Git-visible code changes

The design target is:

- the core model must support multi-agent concurrency
- queryability must exist from day 1
- attempts must be cheap to isolate and discard
- the product entry point should still fit a Git-compatible single-agent workflow

## Non-Goals For V1

The MVP does not implement:

- semantic diff or semantic merge
- agent-to-agent review workflows
- policy enforcement
- symbol-level ownership or leases
- cross-machine sync of AI metadata
- distributed remote object storage
- cross-repo orchestration

Some of these are reserved as extension points, but none should appear as runtime logic in v1.

## Design Principles

1. Git remains the source of truth for code history.
2. AI workflow metadata must not be flattened into commit messages.
3. Queryability is a core capability, not a later enhancement.
4. Attempt isolation is required for cheap experimentation.
5. The data model must support graph relationships and concurrent attempts.
6. Runtime scope must stay small enough to produce a real v1.

## Assumptions

This MVP is designed under the following explicit assumptions:

1. `single-machine`: all AI metadata is local to one machine and one `.ait/` directory.
2. `git-only`: v1 targets Git repositories only.
3. `harness-cooperative`: the harness is expected to emit lifecycle and tool events, though the system must still verify key transitions.
4. `local-rewrite-tolerated`: local Git history may be rewritten by normal commands such as `rebase` or `commit --amend`, and v1 must reconcile local metadata after rewrites on the same machine.
5. `discrete-tool-events`: high-frequency tool activity can be represented as events sent to a daemon or library API.

These assumptions should be revisited in v2, especially for remote sync, shared repositories, and non-Git backends.

## V1 Runtime Objects

V1 runtime logic is limited to three persisted objects plus one materialized query layer:

- `Intent`
- `Attempt`
- `EvidenceSummary`
- indexed supporting tables for files and commits

There is no standalone `Change` object in v1.

Reason:

- the v1 CLI does not expose `change` as a first-class user surface
- the v1 query DSL does not expose `change.*`
- commit linkage can be represented through `Attempt.result` plus indexed tables

If a future CLI adds `ait change ...` or query support for `change.*`, the model should be reevaluated and `Change` can be extracted as a first-class object.

## Identity And Namespacing

V1 must define identity rules explicitly.

### Repo Identity

`repo_id` is a local identifier derived from:

```text
<root_commit_oid>:<install_nonce>
```

`install_nonce` is generated once at `ait init` time and stored in local config.

This avoids collisions between multiple local clones or forks that share the same root commit. It is still a v1 local identity only, not a permanent cross-machine identity scheme.

### Agent Identity

`agent_id` format is:

```text
<harness_name>:<agent_name>
```

Examples:

```text
claude-code:default
aider:main
codex:worker-1
```

The harness provider owns the namespace under its prefix.

### Object Identity

All runtime object IDs use:

```text
<repo_id>:<ulid>
```

This provides local uniqueness, time ordering, and a stable repo namespace boundary for v1.

## Object Model

### Intent

`Intent` is the top-level structured record of what an agent or user is trying to accomplish.

An intent is not a branch and not a commit. It is the structured "why" that groups one or more attempts.

An intent may have multiple concurrent attempts.

Required responsibilities:

- represent the goal of a task
- support parent or child relationships
- record who created the intent
- track lifecycle state
- group one or more attempts

Suggested shape:

```ts
type IntentStatus =
  | "open"
  | "running"
  | "finished"
  | "abandoned"
  | "superseded";

interface Intent {
  id: string;
  schema_version: 1;
  repo_id: string;
  title: string;
  description?: string;
  kind?: string;
  parent_intent_id?: string;
  root_intent_id: string;
  created_at: string;
  created_by: {
    actor_type: "user" | "agent" | "system";
    actor_id: string;
  };
  trigger: {
    source: "prompt" | "cli" | "schedule" | "api";
    prompt_ref?: string;
  };
  status: IntentStatus;
  tags?: string[];
  metadata?: Record<string, string>;
}
```

Notes:

- `kind` is intentionally an open string, not a closed enum.
- `scope_paths` is intentionally excluded from v1.
- `current_attempt_id` is intentionally excluded from v1.
- if `parent_intent_id` is null, then `root_intent_id` must equal `id`.
- if `parent_intent_id` is non-null, then `root_intent_id` must equal the root intent of the parent.

### Attempt

`Attempt` represents one execution attempt for an intent.

An intent may have multiple simultaneous attempts. This is required for:

- retry without history pollution
- competing strategies for the same task
- multi-agent concurrency under one intent

Conceptually, `Workspace` is distinct from `Attempt`, but v1 embeds workspace data inside the attempt rather than modeling workspace as a first-class object.

Required responsibilities:

- record which agent and runtime executed the attempt
- record which isolated workspace was used
- record attempt lifecycle and heartbeats
- keep Git-visible results
- point to raw execution traces

Suggested shape:

```ts
type AttemptReportedStatus =
  | "created"
  | "running"
  | "finished"
  | "crashed";

type AttemptVerifiedStatus =
  | "pending"
  | "succeeded"
  | "failed"
  | "discarded"
  | "promoted";

interface Attempt {
  id: string;
  schema_version: 1;
  intent_id: string;
  ordinal: number;
  agent: {
    agent_id: string;
    model?: string;
    harness?: string;
    harness_version?: string;
  };
  workspace: {
    kind: "worktree";
    workspace_ref: string;
    base_ref_oid: string;
    base_ref_name?: string;
  };
  started_at: string;
  ended_at?: string;
  heartbeat_at?: string;
  reported_status: AttemptReportedStatus;
  verified_status: AttemptVerifiedStatus;
  result?: {
    commits: Array<{
      commit_oid: string;
      base_commit_oid: string;
      insertions?: number;
      deletions?: number;
      touched_files: string[];
    }>;
    promotion_ref?: string;
    exit_code?: number;
  };
  raw_trace_ref?: string;
}
```

Notes:

- v1 explicitly supports `Attempt 1:N commit`.
- commit linkage is stored in `Attempt.result.commits` and indexed separately.
- `reported_status` and `verified_status` are intentionally separate.
- `ordinal` is monotonically increasing within one intent, never reused, and may contain gaps.

### EvidenceSummary

`EvidenceSummary` is the queryable summary layer between runtime objects and raw traces.

This object exists to avoid two failure modes:

- turning the system into an unqueryable log dump
- mixing observed facts, agent claims, and derived inferences without trust boundaries

In v1, only `observed` fields are populated. `claimed` and `derived` are reserved shapes for later use.

Required responsibilities:

- store indexable execution metrics
- store verification outcomes
- store touched file summaries
- point to raw prompt, trace, and logs

Suggested shape:

```ts
interface EvidenceSummary {
  id: string;
  schema_version: 1;
  attempt_id: string;
  observed: {
    tool_calls: number;
    file_reads: number;
    file_writes: number;
    commands_run: number;
    duration_ms: number;
    tests_run: number;
    tests_passed: number;
    tests_failed: number;
    lint_passed?: boolean;
    build_passed?: boolean;
  };
  files_read: string[];
  files_touched: string[];
  files_changed: string[];
  refs: {
    raw_prompt_ref?: string;
    raw_trace_ref?: string;
    logs_ref?: string;
  };
}
```

Notes:

- agent self-report fields are intentionally excluded from the v1 populated schema.
- all numeric observed counters are required in v1; producers must emit `0` instead of null.

## Lifecycle

### Intent Lifecycle

1. User or harness creates an intent.
2. Intent starts in `open`.
3. Once at least one attempt enters `running`, the intent moves to `running`.
4. One or more attempts may execute under the same intent.
5. Final intent status becomes:
   - `finished`
   - `abandoned`
   - `superseded`

Intent lifecycle is derived from attempt state, not from a single pointer to one current attempt.

#### Intent Transition Rules

Intent status transitions are **forward-only**. Automatic refresh must never
move an intent backward (e.g., `running -> open`) and must never mutate a
terminal status (`finished`, `abandoned`, `superseded`).

| From | To | Trigger |
| --- | --- | --- |
| `open` | `running` | any child attempt reaches `reported_status=running` |
| `open` or `running` | `finished` | any child attempt reaches `verified_status=promoted` |
| `open` or `running` | `abandoned` | user runs `ait intent abandon <intent-id>` |
| `open` or `running` | `superseded` | user runs `ait intent supersede <intent-id> --by <new-intent-id>` and an `intent_edges` relation is written |

If an intent has multiple attempts with mixed outcomes, intent status is still `finished` once at least one attempt is promoted. Failed or discarded sibling attempts remain queryable through their own attempt records. An intent whose attempts all end without a promotion stays in its current status until a user explicitly abandons or supersedes it.

### Attempt Lifecycle

Attempt state is split into two dimensions.

#### Reported Status

Set by the harness or agent runtime:

- `created`
- `running`
- `finished`
- `crashed`

#### Verified Status

Set by deterministic verification or supervisor logic:

- `pending`
- `succeeded`
- `failed`
- `discarded`
- `promoted`

Example flow:

1. Attempt created with `reported_status=created`, `verified_status=pending`
2. Harness begins execution and moves to `reported_status=running`
3. Heartbeats update `heartbeat_at`
4. Harness ends execution and reports `finished`
5. Verifier checks commits, outputs, and promotion side effects
6. Verifier marks attempt as `succeeded`, `failed`, or `promoted`
7. If discarded, verifier marks `discarded`

### Reaper

V1 includes a reaper process inside the daemon.

Default behavior:

- heartbeat interval: 30 seconds
- TTL: 5 minutes
- scan interval: 30 seconds

The reaper scans attempts where:

- `reported_status='running'`
- `heartbeat_at` is older than `now - reaper_ttl`

Those attempts are marked `reported_status='crashed'` and `verified_status='failed'` in the same transaction if they are still `pending`.

### EvidenceSummary Lifecycle

1. Prompt, trace, logs, and verification outputs are collected during execution.
2. A summarizer extracts observed metrics and files touched.
3. The observed layer is indexed.
4. Raw payloads remain in blob storage and are referenced by hash.

## Storage Mapping

The storage model is split into three layers.

### 1. Git Layer

Git remains responsible for:

- commits
- branches
- merges
- worktrees

Commit linkage back to AI metadata should be stored using commit trailers:

```text
Intent-Id: <intent-id>
Attempt-Id: <attempt-id>
```

This is preferred over `git notes` for v1 because the metadata travels with commits more predictably in normal Git workflows.

### Rewrite Reconciliation

V1 must tolerate local history rewrite on the same machine.

Required mechanism:

- install a `post-rewrite` Git hook or equivalent observer
- map old commit OIDs to rewritten commit OIDs
- update `attempt_commits` rows for rewritten commits

Commit trailers remain attached to historical commits, but `attempt_commits` is the authoritative live mapping used by `ait query` and `ait blame`.

If reconciliation cannot determine a new commit mapping, the attempt linkage must be marked stale and surfaced by a future `ait reconcile` command rather than failing silently.

### 2. Local Indexed Store

V1 uses SQLite as the local indexed metadata store.

Suggested tables:

- `meta`
- `intents`
- `attempts`
- `evidence_summaries`
- `intent_edges`
- `attempt_commits`
- `evidence_files`

Suggested schema responsibilities:

- `meta(schema_version)`
- `intents(...)`
- `attempts(...)`
- `evidence_summaries(...)`
- `intent_edges(parent_intent_id, child_intent_id, edge_type)`
- `attempt_commits(attempt_id, commit_oid, base_commit_oid)`
- `evidence_files(attempt_id, file_path, kind)`

Required indexes:

- `intents(status, created_at)`
- `intents(kind, created_at)`
- `attempts(intent_id)`
- `attempts(reported_status, heartbeat_at)`
- `attempts(verified_status, started_at)`
- `evidence_summaries(attempt_id)`
- `attempt_commits(commit_oid)`
- `evidence_files(file_path, kind, attempt_id)`
- `intent_edges(child_intent_id, edge_type)`

### 3. Raw Blob Store

Raw payloads are stored in a separate content-addressed blob store, not embedded in the indexed schema.

Raw payload examples:

- full prompt text
- complete tool trace
- stdout or stderr logs
- large test output

Suggested local layout:

```text
.ait/objects/ab/cdef...
```

The indexed store keeps only refs such as:

- `raw_prompt_ref`
- `raw_trace_ref`
- `logs_ref`

## Query And Indexing

Queryability is a phase-1 requirement, not a future enhancement.

V1 therefore defines:

- a minimal query DSL
- a whitelist of queryable fields
- explicit supporting indexes

### Query DSL

Canonical query entry point:

```bash
ait query --on <intent|attempt> '<expression>'
```

Example:

```bash
ait query --on attempt 'kind="bugfix" AND observed.tool_calls>50 AND files_changed~"src/auth/"'
```

Default query subject is `attempt`.

Supported operators:

- `=`
- `!=`
- `<`
- `>`
- `<=`
- `>=`
- `IN`
- `AND`
- `OR`
- `NOT`
- `~` for substring or LIKE-style match

Operator precedence follows SQL:

- `NOT`
- `AND`
- `OR`

`IN` uses SQL-style list syntax:

```text
kind IN ("bugfix", "refactor")
```

`~` means case-sensitive substring match in v1.

Cross-table conditions use `EXISTS` semantics relative to the query subject. For example:

- `--on attempt`: attempt matches if its joined rows satisfy the predicate
- `--on intent`: intent matches if any child attempt or joined child row satisfies the predicate

Pagination is required in v1:

- default `--limit 100`
- optional `--offset`
- output formats: `table` and `jsonl`

### Whitelisted Fields

V1 query support is intentionally restricted to a white list.

Intent fields:

- `id`
- `status`
- `kind`
- `created_at`
- `created_by.actor_type`
- `created_by.actor_id`
- `tags`

Attempt fields:

- `intent_id`
- `agent.agent_id`
- `agent.model`
- `agent.harness`
- `reported_status`
- `verified_status`
- `started_at`
- `ended_at`
- `workspace.kind`
- `workspace.base_ref_oid`

EvidenceSummary observed fields:

- `observed.tool_calls`
- `observed.file_reads`
- `observed.file_writes`
- `observed.commands_run`
- `observed.duration_ms`
- `observed.tests_run`
- `observed.tests_passed`
- `observed.tests_failed`
- `observed.lint_passed`
- `observed.build_passed`

Derived index-backed fields:

- `files_read`
- `files_touched`
- `files_changed`
- `commit_oid`

Any field outside the whitelist must return an error in v1.

### Materialization Rules

SQLite JSON queries are not the primary query mechanism in v1.

Fields needed for filtering should be flattened into indexed columns or supporting tables. The query engine may reconstruct nested API shapes for presentation, but filtering must not depend on unindexed JSON scans.

`metadata` is intentionally not queryable in v1. It exists as a black-box roundtrip map for harness-specific data.

## Workspace Model

V1 does not create `Workspace` as a first-class object, but the concept remains distinct from `Attempt`.

Why this distinction matters:

- the same workspace may be reused across retries
- one attempt may eventually span multiple environments in later versions
- workspace lifecycle and cleanup are separate concerns from attempt identity

V1 simplification:

- embed workspace data inside `Attempt.workspace`
- support `worktree` only in v1

Minimum workspace requirements:

- create isolated execution context from a Git base ref
- expose a stable workspace reference
- cleanly discard unused attempts
- promote successful results back to a target branch

### Discard Semantics

V1 distinguishes between:

- built-in cleanup
- external side effects

Built-in cleanup handled by `ait`:

- deleting worktrees
- stopping local sandboxes owned by `ait`
- removing temporary local state owned by `ait`

External side effects are out of scope for v1, but a teardown hook should be reserved for user-defined cleanup.

## Harness Integration Protocol

High-frequency event ingestion must not rely on spawning a CLI process for every tool call.

V1 integration strategy:

- `daemon/library first`
- `CLI second`

### Required Protocol Modes

1. Background daemon over Unix socket or equivalent local IPC
2. Optional library bindings for harness integrations
3. Human-facing CLI for inspection and lifecycle commands

### Transport

V1 daemon transport is newline-delimited JSON over a Unix domain socket.

Each event must include:

- `event_id`
- `event_type`
- `attempt_id`
- `sent_at`
- `ownership_token`

`event_id` is the idempotency key. Duplicate events with the same `event_id` must be ignored.

### Required Event Types

- `intent_created`
- `attempt_created`
- `attempt_started`
- `attempt_heartbeat`
- `tool_event`
- `attempt_finished`
- `attempt_promoted`
- `attempt_discarded`

### Event Payload Rules

`tool_event` payload must include:

- `tool_name`
- `category`: `read | write | command | other`
- `duration_ms`
- `success`
- optional `payload_ref`

Category meanings:

- `read`: pure read operations such as read, grep, glob
- `write`: file modifications
- `command`: external command execution
- `other`: everything else

The daemon computes counters from event categories:

- `observed.tool_calls`: count of all `tool_event`
- `observed.file_reads`: count of `category=read`
- `observed.file_writes`: count of `category=write`
- `observed.commands_run`: count of `category=command`

Harnesses must emit categories, but they must not pre-compute summary counters.

### Ordering And Ownership

- events may arrive out of order
- heartbeat handling uses `max(heartbeat_at)`
- `attempt_finished` arriving after a later heartbeat is valid
- only the holder of the `ownership_token` returned by `ait attempt new` may emit lifecycle-mutating events for that attempt

### Verification Responsibility

The harness may report events, but final durable state must still be verified.

Examples:

- promotion is only valid if the target Git ref actually moved
- success is only valid if the expected outputs and commits exist
- crashes are detected via missing heartbeat and reaper logic

## CLI Surface

The MVP CLI should stay narrow and consistent.

### Lifecycle Commands

```bash
ait intent new --title "fix oauth expiry" --kind bugfix
ait intent show <intent-id>
ait intent list
ait intent abandon <intent-id>

ait attempt new <intent-id>
ait attempt show <attempt-id>
ait attempt list --intent <intent-id>
ait attempt promote <attempt-id> --to <branch>
ait attempt discard <attempt-id>
```

### Query Command

```bash
ait query --on <intent|attempt> '<dsl>'
```

This is the single general-purpose query entry point in v1.

There is no parallel `ait list` or `ait find` top-level query surface.

### Shortcut Command

```bash
ait blame <path>[:<line>]
```

`ait blame` is a convenience command layered on top of the same indexed metadata, not a separate query model. `ait intent list` and `ait attempt list` are allowed only as thin shortcuts over the same query engine.

### Daemon Commands

```bash
ait daemon start
ait daemon stop
ait daemon status
```

## Example End-To-End Flow

```bash
ait intent new --title "fix oauth expiry" --kind bugfix
# => <repo_id>:01...

ait attempt new <intent-id>
# => creates isolated workspace

# harness reports execution through daemon or library API

ait attempt promote <attempt-id> --to fix/oauth-expiry
# => verifier confirms target branch update
# => attempt verified_status becomes promoted

ait intent show <intent-id>
```

Expected `ait intent show` output should include:

- intent goal and status
- attempts under the intent
- files touched
- verification summary
- linked commits

## Extension Points

V1 does not persist dedicated runtime objects for review or policy decisions, but the spec reserves extension points for both.

Reserved field names for future extension joins:

- `subject_type`
- `subject_id`

### Future Review Extension

A future review layer should join to existing runtime objects by:

- `subject_type`
- `subject_id`

Expected future decision values include:

- `approved`
- `rejected`
- `commented`
- `needs_changes`

Reserved naming prefix:

- `review_*`

### Future Policy Extension

A future policy layer should also join by:

- `subject_type`
- `subject_id`

Expected future fields include:

- `enforced: bool`
- `mode: advisory | enforcing`

Reserved naming prefix:

- `policy_*`

These extensions should be introduced only when:

- AI-to-AI review becomes a real workflow requirement
- regulated or governed environments require policy evidence

## V1 Success Criteria

The MVP is successful if it can do all of the following:

1. Create and persist an `Intent`
2. Create multiple isolated `Attempt` objects under one intent
3. Support concurrent active attempts under one intent
4. Link attempt output to one or more Git commits
5. Generate a minimal but useful `EvidenceSummary`
6. Query intents and attempts by structured filters
7. Support intent-aware inspection such as `ait intent show` and `ait blame`
8. Detect and clean up crashed attempts through heartbeat and reaper logic

If these eight work, the system has moved beyond a metadata wrapper and into a real AI-oriented version control layer.

## Open Questions

The following questions remain intentionally open for later design work, but they must not block v1:

- when should `Workspace` become a first-class object?
- when should `claimed` and `derived` evidence be populated?
- what prompt redaction pipeline is required before blob persistence?
- what is the right long-term repo identity scheme once cross-machine sync exists?
- when does a standalone `Change` object become justified by the CLI or query surface?

## Review Focus

This document should be reviewed against these criteria:

- architectural consistency
- v1 feasibility
- future extensibility to multi-agent workflows
- support for AI-heavy review without forcing it into v1
- resistance to both over-design and short-term hacks
