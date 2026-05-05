<!--
Sync Impact Report
Version change: N/A -> 1.0.0
Modified principles:
- Template placeholders -> I. Spec-Kit Traceability
- Template placeholders -> II. Low Coupling, High Cohesion
- Template placeholders -> III. Stable Public Behavior
- Template placeholders -> IV. Local Safety And Data Integrity
- Template placeholders -> V. Verification Before Completion
Added sections:
- Project Constraints
- Spec-Kit Workflow
Removed sections:
- Template placeholder sections
Templates requiring updates:
- Updated: .specify/templates/plan-template.md
- Updated: .specify/templates/spec-template.md
- Updated: .specify/templates/tasks-template.md
Follow-up TODOs: none
-->
# AIT Constitution

## Core Principles

### I. Spec-Kit Traceability
Every feature, refactor, and bug fix MUST move through the Spec Kit flow:
constitution, specification, plan, tasks, implementation, and verification.
Changes MUST be traceable from a user request to `spec.md`, `plan.md`,
`tasks.md`, code, tests, and final evidence. Existing documents in `docs/`
remain authoritative for the product surface, but new implementation work MUST
be represented in the active `specs/` feature directory before code changes
start.

### II. Low Coupling, High Cohesion
Production modules MUST have a single clear responsibility and explicit
dependency direction. Business decisions, persistence access, CLI rendering,
process orchestration, and external commands MUST not be mixed in the same
function unless the plan documents why the smaller boundary would be worse.
Refactors MUST prefer narrow modules with stable dataclasses, repository
interfaces, or command handlers over hidden cross-module imports or duplicated
connection logic.

### III. Stable Public Behavior
AIT is a CLI and library surface layered on Git. Refactors MUST preserve public
command names, flags, exit codes, JSON keys, SQLite semantics, daemon protocol
envelopes, resource file locations, and documented import shims unless a spec
explicitly declares a compatibility change. A behavior/spec mismatch is a bug
to fix or document, not an implementation detail to hide.

### IV. Local Safety And Data Integrity
AIT MUST remain local-first and dependency-light. Runtime code MUST avoid new
third-party dependencies unless a spec and plan justify the dependency and its
failure modes. Worktree, cleanup, daemon, and database changes MUST be bounded
to AIT-owned paths and MUST not delete user work, mutate Git refs, or alter
SQLite records without an explicit policy and tests for the unsafe edge cases.

### V. Verification Before Completion
No task is complete until the evidence covers the requirement being claimed.
Tests, manifests, and green commands are useful only when they exercise the
changed behavior and architecture gates. Every implementation slice MUST run
targeted tests, repository-wide tests appropriate to the touched surface,
`git diff --check`, and any spec-specific acceptance checks. Completion claims
MUST name the commands run and any residual risk.

## Project Constraints

AIT targets Python 3.14+ and uses only the Python standard library at runtime.
SQLite storage, Git subprocesses, shell hooks, daemon sockets, and generated
agent resources are core integration boundaries and MUST stay independently
testable. Documentation SHOULD stay concise; when a document becomes hard to
review, split it by concern rather than appending unrelated material.

Production modules SHOULD stay below 600 lines after a refactor slice unless
the plan records why a larger cohesive module is acceptable. Any production
module above 1,000 lines is a gate failure unless the plan includes an explicit
temporary exception, owner, and follow-up task.

## Spec-Kit Workflow

1. Run the relevant Spec Kit command or extension hook before each phase.
2. Keep exactly one active feature directory recorded in `.specify/feature.json`
   while executing a slice.
3. Use `spec.md` for user-visible behavior and measurable success criteria.
4. Use `plan.md` for technical boundaries, dependency direction, and
   constitution gate decisions.
5. Use `tasks.md` for ordered implementation steps and mark each completed task.
6. Stop and revise the spec or plan if implementation discovers a bug, hidden
   coupling, unsafe behavior, or a public compatibility risk outside the
   current task scope.

## Governance

This constitution supersedes ad hoc refactor preferences when using Spec Kit.
Amendments require updating this file, synchronizing affected templates, and
recording the version change in the Sync Impact Report. Versioning follows
semantic rules: MAJOR for incompatible governance changes, MINOR for new or
expanded principles, and PATCH for clarifications. Reviews MUST check
constitution compliance before accepting a spec, plan, task list, or completed
implementation.

**Version**: 1.0.0 | **Ratified**: 2026-05-06 | **Last Amended**: 2026-05-06
