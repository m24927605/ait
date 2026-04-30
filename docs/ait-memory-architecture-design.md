# AIT Long-Term Memory Architecture Design

## Goal

AIT should provide long-term memory for AI coding agents without making
users operate a separate memory system.

Users should continue running:

```bash
claude
codex
gemini
```

AIT should work behind the scenes:

1. capture the run
2. normalize the transcript
3. extract evidence
4. derive memory candidates
5. govern and persist durable memory
6. inject relevant memory into the next agent run
7. expose the history in graph and report views

## Product Claim Boundary

AIT may claim:

- repo-local long-term memory foundation
- evidence-backed memory recall
- lower need for repeated user explanation
- better cross-agent continuity

AIT must not claim without benchmarks:

- complete memory
- hallucination elimination
- guaranteed token savings
- fully autonomous multi-agent orchestration

## Design Principles

### 1. Evidence First

Every durable memory item must link to evidence:

- attempt id
- raw trace ref
- normalized trace ref
- changed file
- commit oid
- outcome classification
- test/build evidence when available

Memory without evidence is allowed only as manual user-provided memory
and must carry `source=manual`.

### 2. Temporal, Not Mutable

Memory should not be overwritten in place when facts change. A newer
fact should supersede the older fact while both remain auditable.

### 3. Local First

Default storage is repo-local:

- SQLite under `.ait/state.sqlite3`
- traces under `.ait/traces/`
- generated markdown under `.ait/memory/`
- reports under `.ait/report/`

No remote service is required by default.

### 4. Low Interruption

Memory commands are diagnostics and controls, not daily workflow.

Normal workflow:

```bash
ait init
direnv allow
codex
claude
gemini
```

### 5. Advisory Context

Retrieved memory tells agents what previous evidence suggests. It must
also instruct agents to verify current files before editing.

## Target Pipeline

```text
agent CLI
  -> AIT wrapper
  -> attempt workspace
  -> command / PTY transcript capture
  -> raw trace
  -> normalized transcript
  -> evidence extraction
  -> outcome classification
  -> memory candidate extraction
  -> policy filter and redaction
  -> temporal memory consolidation
  -> generated markdown memory
  -> hybrid recall
  -> context injection into next run
```

## Storage Layers

### Raw Evidence

Purpose:

- preserve what actually happened
- support audit and debugging
- allow future extractors to improve without losing data

Examples:

- `.ait/traces/<attempt>.txt`
- `.ait/traces/normalized/<attempt>.txt`
- file evidence rows
- commit evidence rows

### Candidate Memory

Purpose:

- store extracted facts before they are accepted as durable memory
- keep failed-attempt lessons separate from high-confidence rules

Candidate states:

- `candidate`
- `accepted`
- `rejected`
- `superseded`

### Durable Memory

Purpose:

- compact, reusable project knowledge
- injected into later agent runs
- displayed in `ait memory` and `graph.html`

Durable memory should be limited and structured.

### Generated Markdown

Purpose:

- human-readable memory surface
- easy for coding agents to consume
- reviewable in Git if the user chooses to export it

Generated files should be derived from SQLite and may be regenerated.

## Memory Object Model

Core fields:

- `id`
- `kind`
- `topic`
- `body`
- `summary`
- `source_attempt_id`
- `source_trace_ref`
- `source_commit_oid`
- `source_file_path`
- `confidence`
- `status`
- `valid_from`
- `valid_to`
- `superseded_by`
- `created_at`
- `updated_at`

Kinds:

- `decision`
- `rule`
- `workflow`
- `failure`
- `entity`
- `current_state`
- `manual`

Confidence:

- `high`: succeeded/promoted attempt with supporting evidence
- `medium`: succeeded_noop or informational attempt
- `low`: failed attempt or weak transcript-only evidence
- `manual`: user-authored note

## Temporal Rules

1. A newer memory can supersede an older memory.
2. Superseded memory remains searchable but should not be injected by
   default.
3. Failed attempt memory is retained as a lesson but must be labeled as
   failure evidence.
4. Current-state memory should expire or be refreshed frequently.
5. Manual memory has high authority but can still be superseded by a
   newer manual note.

## Retrieval Design

AIT should rank memory with multiple signals:

1. literal match
2. lexical terms
3. entity match
4. file path overlap
5. recent attempt activity
6. success/outcome confidence
7. optional semantic score
8. supersession penalty

Initial scoring formula:

```text
score =
  literal_score
  + lexical_score
  + entity_score
  + file_overlap_score
  + recency_score
  + confidence_score
  + optional_semantic_score
  - stale_penalty
```

## Context Injection

Wrappers should call memory recall before launching the real agent.

Injected context should include:

- current intent
- relevant durable memory
- recent related attempts
- known failed approaches
- active project rules
- source references

Injected context should not include:

- raw full transcripts by default
- secrets
- rejected memory
- superseded memory unless explicitly relevant
- excessive unrelated history

## Governance

Governance inputs:

- `.ait/memory-policy.json`
- redaction rules
- excluded paths
- excluded transcript patterns
- source allow/block lists
- confidence thresholds

Governance outputs:

- accepted durable memory
- candidate memory
- rejected memory with reason
- lint warnings
- report visibility

## Interaction With Git

Git is central to AIT memory.

Memory confidence should increase when:

- attempt succeeded
- attempt produced commit
- commit was promoted
- tests passed
- files changed match the claimed memory

Memory confidence should decrease when:

- attempt failed
- attempt was discarded
- no evidence supports the claim
- later commits touch related files and contradict it

## Graph / Report Requirements

`ait graph --html` should show:

- memory facts linked to attempts
- accepted vs candidate memory
- superseded facts
- failed-approach lessons
- why a memory was retrieved
- source trace and commit references

The report should help users answer:

- What does AIT think this project knows?
- Why does it think that?
- Which agent created the evidence?
- Is this fact current?
- What changed after this memory was created?

## Extension Points

Optional future integrations:

- embedding provider
- vector store
- Graphiti-style graph backend
- MCP memory server
- team-shared memory export/import

These should be optional. The default AIT install must remain useful
with only Python, Git, SQLite, and local files.

## Architecture Decision

AIT should not adopt a single external memory framework as its core.

Reason:

- AIT's unique asset is Git-grounded provenance.
- Generic memory tools usually optimize chat personalization.
- Coding memory must track commits, files, attempts, outcomes, and
  supersession.

Decision:

- Implement AIT-native repo memory.
- Borrow retrieval and temporal modeling ideas from Mem0, Graphiti,
  LangMem, Letta, Supermemory, Hindsight, MemMachine, and ByteRover.
- Keep external memory backends optional.
