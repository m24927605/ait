# Long-Term LLM Memory Design

## Staff-Level Team

The first implementation is owned by a small Staff-level team with clear
decision boundaries:

- Staff AI Infrastructure Engineer: owns memory extraction, context
  injection, and adapter integration.
- Staff Developer Experience Engineer: owns CLI behavior, user-facing
  commands, and onboarding clarity.
- Staff Data/Storage Engineer: owns persistence boundaries and ensures
  memory is derived from durable repo state instead of model session
  state.
- Staff Test/Release Engineer: owns acceptance scenarios, smoke tests,
  and regression coverage.
- Staff Security/Privacy Engineer: owns the rule that long-term memory
  remains local repo state and is only injected into agent runs that the
  user explicitly starts.

## Goal

Make Claude Code feel like it has durable project memory by rebuilding
memory from `ait` state before each wrapped run. The model does not
receive permanent internal memory. Instead, `ait` externalizes memory as
repo-local facts and injects a compact summary into the agent context.

## Non-Goals

- Do not claim the LLM itself remembers forever.
- Do not sync memory across machines.
- Do not upload memory to a remote service.
- Do not build embeddings or vector search in the first version.
- Do not inject unbounded history into the prompt.

## Memory Source

The first version builds memory from existing durable data:

- intents
- attempts
- verified statuses
- result exit codes
- changed files
- attempt-linked commits
- hot files derived from changed/touched evidence

This avoids a new storage schema and keeps memory rebuildable from the
SQLite state plus Git commit metadata.

## User Interface

Inspect memory directly:

```bash
ait memory
ait memory --format json
ait memory --path src/
ait memory --topic architecture
ait memory --promoted-only
ait memory --budget-chars 4000
ait memory search "auth adapter"
ait memory search "auth adapter" --format json
ait memory search "auth adapter" --ranker lexical
ait memory note add --topic architecture "Keep adapter layers thin."
ait memory note list
ait memory note remove <note-id>
```

Claude Code receives the same memory automatically through the
repo-local wrapper because the Claude Code adapter enables context by
default. The wrapper calls `ait run --adapter claude-code`, which writes
`.ait-context.md` into the attempt worktree before launching Claude.

## Injection Contract

`.ait-context.md` now contains two sections:

1. intent-local context for the current run
2. `AIT Long-Term Repo Memory`

Claude Code is expected to read `AIT_CONTEXT_FILE` before editing. The
adapter already exposes:

```text
AIT_CONTEXT_HINT=Read AIT_CONTEXT_FILE before starting work.
```

## Safety Model

Memory is advisory. The generated context explicitly tells agents to
verify current files before editing. This matters because:

- previous attempts can be stale
- failed attempts can contain incorrect direction
- root branches can move after an attempt was recorded

## Future Extensions

Implemented increments:

- memory filtering by file path or topic
- promoted-only memory mode
- manually curated memory notes
- compaction policies
- local evidence search with the `ait memory search <query>` command
- local TF-IDF vector ranking for memory search
- adapter support beyond Claude Code for Aider and Codex repo-local
  wrappers

The next natural increments are:

- external embedding-backed ranking over local evidence, if explicitly
  configured by the user
- native tool-level hooks beyond Claude Code
