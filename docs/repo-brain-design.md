# AIT Repo Brain Design

## Staff-Level Team

This feature is owned by a small Staff+ team:

- Staff AI Infrastructure Architect: owns context injection and agent
  workflow integration.
- Staff Data Systems Engineer: owns the graph model, rebuildability,
  and local storage boundaries.
- Staff Developer Experience Engineer: owns CLI behavior and the
  low-interruption user path.
- Staff Test/Release Engineer: owns regression coverage and release
  acceptance.
- Staff Security/Privacy Engineer: owns local-only memory, redaction,
  and policy exclusion behavior.

## Goal

AIT should make every supported AI coding agent behave as if it has
durable, repo-scoped, verifiable memory without requiring the user to
remember workflow commands.

The first production slice adds a repo brain that is:

- local to `.ait/`
- rebuildable from Git, SQLite state, docs, notes, and traces
- represented as a typed graph
- searchable without external services
- automatically refreshed and injected before wrapped agent runs

## Non-Goals

- Do not add a network database or hosted vector service.
- Do not claim the model itself has permanent memory.
- Do not make graph maintenance a required manual workflow.
- Do not store raw secrets in graph output.
- Do not replace the existing long-term memory summary.

## Architecture

AIT already has durable workflow state:

- intents
- attempts
- agents
- evidence files
- commits
- traces
- curated memory notes
- repo docs

The repo brain materializes these into graph nodes and edges:

```text
repo -> intent -> attempt -> file
attempt -> commit
attempt -> agent
note -> topic
repo -> doc
```

The graph is not the source of truth. It is a derived index. If it is
deleted, AIT can rebuild it from durable state.

The implementation boundary is intentionally narrow:

- `src/ait/brain.py` owns graph construction, rendering, file output,
  and graph query.
- `src/ait/memory.py` remains the long-term memory facade.
- `src/ait/runner.py` is the only automatic context injection point.
- adapter modules only expose wrapper contracts and environment hints.
- hooks and daemon events record evidence; they do not decide prompt
  content.

## Storage

Generated files live under:

```text
.ait/brain/graph.json
.ait/brain/REPORT.md
```

The JSON file is intended for tooling. The report is intended for agents
and humans. Both are safe to regenerate.

The first implementation does not add SQLite tables. A future persistent
index may add `memory_documents`, `memory_edges`, or embedding metadata,
but only after the derived sidecar model proves useful and the migration
need is clear.

## Confidence Labels

Each node and edge carries a confidence label:

- `extracted`: directly derived from Git, SQLite, docs, notes, or traces
- `inferred`: derived by deterministic local rules
- `ambiguous`: not used by the first implementation, reserved for later
  model-assisted extraction

The first implementation only writes `extracted` and `inferred`.

## CLI

```bash
ait memory graph build
ait memory graph show
ait memory graph query "release pypi"
```

`build` writes `.ait/brain/graph.json` and `.ait/brain/REPORT.md`.
`show` renders the current derived brain without requiring a prior
manual build. `query` searches graph nodes and includes directly
connected context.

## Automatic Agent Integration

Before a wrapped agent starts, AIT refreshes the repo brain and includes
a compact `AIT Repo Brain` section in `.ait-context.md`.

This means the intended user flow stays:

```bash
claude
codex
aider
```

after the one-time shell and repo setup.

## Search Strategy

The first production slice uses deterministic local lexical ranking over
graph nodes. AIT already has local TF-IDF search in `ait memory search`;
the graph query layer complements it by returning relationships, not
only similar text.

External vector databases remain an implementation detail behind a
future index interface. They must not become required for the default
local workflow.

The current `ait memory search --ranker vector` is local TF-IDF ranking,
not an external embedding vector database. User-facing repo brain docs
must avoid implying otherwise.

## Privacy And Policy

The repo brain follows the active memory policy:

- policy-excluded paths are not emitted as file/doc nodes
- transcript exclusion is preserved through existing trace handling
- note and trace text is redacted before it can appear in reports

The graph stores compact summaries and identifiers. It does not store
full file contents.

Claude native hook traces, Codex/Aider transcripts, memory notes, and
future indexable text must pass through the same redaction and policy
filters before they can appear in graph output.

## Production Rules

1. Graph output must be deterministic enough for tests.
2. Missing `.ait/` state must produce a valid empty brain.
3. Build output must be idempotent.
4. Query must not require a previously written graph file.
5. Context injection failure should fail the agent run rather than
   silently giving stale memory.
6. The implementation must stay dependency-light until a real external
   index is explicitly configured.
7. Existing long-term memory behavior must remain compatible.
8. Generated graph files must be written to the repo root `.ait/brain/`
   even when the agent runs from an attempt worktree.
9. Failed and unpromoted attempts may appear as evidence, but reports
   must label status clearly so agents treat them as advisory.
10. The first implementation must avoid duplicate memory records from
    overlapping wrapper and native hook flows by deriving from persisted
    attempts and stable identifiers only.

## Document Review Log

Completed before implementation:

1. Architecture review: keep retrieval and graph construction out of
   adapters; use `memory.py` and `runner.py` as integration boundaries.
2. Data model review: start with derived `.ait/brain/` sidecar files
   instead of adding schema and migration surface prematurely.
3. Developer experience review: preserve the direct `claude`, `codex`,
   and `aider` flow after one-time setup.
4. Security/privacy review: apply existing memory policy and redaction
   before writing graph outputs.
5. Test/release review: extend existing `unittest` tests, fake adapter
   smoke tests, and JSON parse checks.
