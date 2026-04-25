# Parallel Development Policy

## Purpose

This document defines when and how parallel development should be used in this repository.

It is an execution policy, not a product spec.

The goal is to:

- shorten delivery time without increasing integration risk
- keep sub-task ownership clear
- prevent overlapping edits and avoidable merge conflicts
- keep implementation aligned with the frozen docs

## Core Rules

1. Parallelize only when work items have clear ownership boundaries.
2. Do not parallelize the critical path if the next step depends on one unresolved result.
3. Do not assign two agents to edit the same file unless one is explicitly the integrator.
4. Follow the current docs and milestone boundaries. Do not invent side work outside the current phase.
5. Prefer narrow, file-bounded tasks over broad exploratory delegation.
6. Small functionality should remain the unit of commit.

## When To Parallelize

Parallel development is appropriate when:

- two tasks touch different modules
- one task is implementation and another is supporting infrastructure
- one task can proceed from a stable interface already defined in docs
- one task is read-heavy and another is write-heavy with low overlap

Parallel development is not appropriate when:

- the work is still being designed
- the same data model is still changing
- two tasks need to edit the same workflow or command path
- the interface between tasks is still unclear
- the next step is blocked on one unresolved implementation detail

## Ownership Rules

Every parallel task must define:

- goal
- owner
- allowed write scope
- forbidden write scope
- expected output
- handoff target

Minimum ownership example:

```text
Owner: Agent A
Goal: Implement SQLite migrations
Allowed write scope: src/db/**, migrations/**
Forbidden write scope: src/query/**, src/daemon/**
Expected output: migration runner + initial schema
Handoff target: main integrator
```

If ownership cannot be written this clearly, the work is not ready to parallelize.

## Integration Rules

One agent must remain responsible for integration.

The integrator is responsible for:

- preserving alignment with docs
- sequencing merges
- resolving interface mismatches
- deciding whether a sub-task result is accepted, revised, or deferred

Sub-agents may implement bounded work, but they do not own final integration.

## Conflict Rules

If two tasks need the same file or module:

1. stop parallel execution on that area
2. assign one owner
3. move the other task to a dependency queue or reduce its scope

If a sub-agent discovers a likely refactor:

1. do not silently expand scope
2. record or update the relevant refactor note
3. return the finding to the integrator for sequencing

## Commit Rules

1. Commit by small, self-contained functionality.
2. Do not mix unrelated outputs from different sub-tasks into one commit.
3. Commit messages must include referenced docs and keywords.
4. Review each change three times before commit.
5. If a sub-agent produced work, the integrator must still review before commit.

Required commit message pattern:

```text
<summary> docs:../path/a.md,../path/b.md keyword:xxxx,oooo
```

## Review Rules

A sub-task is not complete just because code exists.

It is complete only when:

1. the output matches the assigned scope
2. no forbidden files were changed
3. the change aligns with current docs
4. the integrator has reviewed it
5. the result is ready to merge without reopening the same design question

## Phase-Based Parallelization

Parallelization should follow the current implementation milestone.

### M1: Persistence And Attempt Bootstrap

Allowed parallel work:

- schema and migrations
- config and `ait init`
- repo identity and local config
- worktree provisioning
- `ait intent new`
- `ait attempt new`

Avoid parallel overlap on:

- the same database models
- the same CLI command path
- ownership token flow before the interface is fixed

Recommended split:

- worker 1: schema and migrations
- worker 2: config and repo identity
- worker 3: workspace and worktree bootstrap
- integrator: CLI wiring for `init`, `intent new`, `attempt new`

### M2: Daemon Ingest And Evidence Accumulation

Allowed parallel work:

- daemon transport
- envelope validation and dedupe
- token validation
- event handlers
- evidence accumulation

Avoid parallel overlap on:

- event schema definitions
- lifecycle state transitions
- shared daemon state management

Recommended split:

- worker 1: socket transport and envelope parsing
- worker 2: dedupe and token validation
- worker 3: event accumulation into evidence tables
- integrator: daemon lifecycle and cross-handler consistency

### M3: Query, Verification, And Cleanup

Allowed parallel work:

- query parser
- SQL lowering
- verifier
- reaper
- rewrite reconciliation

Avoid parallel overlap on:

- query field registry
- status transition semantics
- shared Git verification helpers

Recommended split:

- worker 1: query parser and whitelist validation
- worker 2: SQL lowering and output formatting
- worker 3: verifier and promotion checks
- worker 4: reaper and startup recovery
- integrator: `ait blame` and cross-module integration

## Stop Conditions

Pause parallel development and return to centralized execution if:

- multiple tasks need the same files
- the spec changes mid-task
- integration defects exceed implementation progress
- sub-agents are reopening settled design decisions
- the team is producing work faster than it can be reviewed

## Notes For AI Agents

1. Do not guess. If an interface is unclear, stop and verify.
2. Do not fabricate completion or results.
3. Keep scope tight.
4. If attention quality drops, notify the user.
5. Do not keep exploring after the current phase objective is already satisfied.
