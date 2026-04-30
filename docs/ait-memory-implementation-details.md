# AIT Memory Implementation Details

## Purpose

This document turns the memory architecture into implementable work.

It defines:

- schema additions
- extraction pipeline
- retrieval pipeline
- context injection
- CLI behavior
- tests
- release gates

## Current Baseline

AIT already has:

- intents
- attempts
- workspaces
- raw traces
- normalized traces
- outcome classification
- memory notes
- memory search
- memory policy
- graph text and HTML reports
- wrappers for Claude Code, Codex, and Gemini

The next implementation should evolve this into structured temporal
memory without breaking the existing commands.

## Schema Additions

### `memory_facts`

Purpose:

- canonical structured durable and candidate memory

Columns:

- `id TEXT PRIMARY KEY`
- `schema_version INTEGER NOT NULL`
- `kind TEXT NOT NULL`
- `topic TEXT NOT NULL`
- `body TEXT NOT NULL`
- `summary TEXT NOT NULL`
- `status TEXT NOT NULL`
- `confidence TEXT NOT NULL`
- `source_attempt_id TEXT`
- `source_trace_ref TEXT`
- `source_commit_oid TEXT`
- `source_file_path TEXT`
- `valid_from TEXT NOT NULL`
- `valid_to TEXT`
- `superseded_by TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Status values:

- `candidate`
- `accepted`
- `rejected`
- `superseded`

Kind values:

- `decision`
- `rule`
- `workflow`
- `failure`
- `entity`
- `current_state`
- `manual`

### `memory_fact_entities`

Purpose:

- support entity-aware retrieval without a graph database

Columns:

- `memory_fact_id TEXT NOT NULL`
- `entity TEXT NOT NULL`
- `entity_type TEXT NOT NULL`
- `weight REAL NOT NULL`

Indexes:

- `(entity)`
- `(entity_type, entity)`
- `(memory_fact_id)`

### `memory_fact_edges`

Purpose:

- model simple temporal and semantic relationships

Columns:

- `id TEXT PRIMARY KEY`
- `source_fact_id TEXT NOT NULL`
- `target_fact_id TEXT NOT NULL`
- `edge_type TEXT NOT NULL`
- `confidence TEXT NOT NULL`
- `created_at TEXT NOT NULL`

Edge types:

- `supersedes`
- `supports`
- `contradicts`
- `related_to`
- `derived_from`

### `memory_retrieval_events`

Purpose:

- audit what memory was injected into agent context

Columns:

- `id TEXT PRIMARY KEY`
- `attempt_id TEXT NOT NULL`
- `query TEXT NOT NULL`
- `selected_fact_ids_json TEXT NOT NULL`
- `ranker_version TEXT NOT NULL`
- `budget_chars INTEGER NOT NULL`
- `created_at TEXT NOT NULL`

## Migration Strategy

1. Add tables without changing existing `memory_notes`.
2. Backfill `memory_facts` from existing durable memory notes.
3. Keep `ait memory` rendering compatible.
4. Gradually migrate recall to read from `memory_facts`.
5. Keep `memory_notes` as compatibility and manual note surface until a
   later major release.

## Extraction Pipeline

Input:

- normalized transcript
- attempt metadata
- outcome classification
- changed files
- commits
- test/build signals if available

Steps:

1. Load normalized transcript.
2. Apply memory policy exclusions.
3. Redact secrets.
4. Extract candidate lines or blocks.
5. Classify kind:
   - decision
   - rule
   - workflow
   - failure
   - entity
   - current_state
6. Attach evidence references.
7. Assign confidence.
8. Detect duplicate or near-duplicate facts.
9. Detect supersession candidates.
10. Insert or update `memory_facts`.
11. Render generated markdown.

## Candidate Acceptance Rules

Accept automatically when:

- attempt outcome is `succeeded` or `promoted`
- fact is supported by transcript and file/commit evidence
- policy allows source
- no high-confidence contradiction exists
- confidence is `high`

Keep as candidate when:

- attempt failed
- evidence is transcript-only
- fact looks useful but unsupported by files or commits
- contradiction exists but cannot be resolved

Reject when:

- secret or excluded path/pattern
- known prompt injection instruction
- purely conversational filler
- terminal UI noise
- command echo
- duplicate of existing accepted fact

## Supersession Rules

A new fact may supersede an old fact when:

- same topic and overlapping entities
- newer attempt timestamp
- newer source has equal or higher confidence
- body indicates replacement, migration, or changed rule

Examples:

- "Use npm test" superseded by "Use pnpm test."
- "Auth uses REST" superseded by "Auth moved to GraphQL."

Supersession should:

- set old fact `status=superseded`
- set old fact `valid_to`
- set old fact `superseded_by`
- create `memory_fact_edges(edge_type='supersedes')`

## Entity Extraction

Initial deterministic entities:

- file paths
- package names from manifest files
- command names
- test commands
- agent names
- API route-like strings
- module names from changed files

Do not require LLM extraction in the first implementation.

Future optional extraction:

- LLM-assisted entities
- AST symbols
- import graph entities

## Retrieval Pipeline

Input:

- intent title
- command text
- agent adapter
- changed file hints if available
- user query for explicit search

Steps:

1. Build query text.
2. Search accepted memory facts.
3. Search recent relevant attempts.
4. Search failure memories separately.
5. Score candidates with hybrid ranker.
6. Remove rejected and superseded facts unless explicitly requested.
7. Apply policy.
8. Fit result into token/character budget.
9. Record `memory_retrieval_events`.
10. Inject context.

## Ranker Version 1

Signals:

- literal substring match
- token overlap
- CJK literal match
- entity overlap
- file path overlap
- recency
- confidence
- outcome class
- supersession penalty

Pseudo-score:

```text
score =
  10.0 * literal_match
  + 3.0 * lexical_overlap
  + 4.0 * entity_overlap
  + 5.0 * file_overlap
  + 2.0 * confidence_weight
  + 1.0 * recency_weight
  + 2.0 * promoted_or_succeeded_weight
  - 8.0 * superseded_penalty
```

## Generated Markdown

Path:

```text
.ait/memory/repo-memory.md
```

Sections:

- Project Rules
- Architecture Decisions
- Workflows
- Failed Approaches To Avoid
- Important Entities
- Current State
- Superseded Facts

Each item should include:

- short fact
- confidence
- source attempt short id
- source commit short oid if present
- last updated time

Markdown is generated output. SQLite remains the source of truth.

## Context Injection Format

`.ait-context.md` should include:

```markdown
## AIT Relevant Memory

Use this as advisory project memory. Verify current files before editing.

### Project Rules

- ...

### Relevant Decisions

- ...

### Failed Approaches To Avoid

- ...

### Recent Related Attempts

- ...

### Evidence References

- ...
```

## CLI Changes

New commands:

```bash
ait memory facts
ait memory facts --format json
ait memory facts --status candidate
ait memory facts --kind decision
ait memory facts accept <fact-id>
ait memory facts reject <fact-id>
ait memory facts supersede <old-fact-id> <new-fact-id>
ait memory recall <query> --explain
ait memory render
```

Existing commands must keep working:

```bash
ait memory
ait memory search <query>
ait graph
ait graph --html
```

## HTML Report Changes

`graph.html` should add:

- Memory Facts panel
- Candidate vs accepted count
- Superseded facts view
- Retrieval explanation for each attempt
- Source links to attempts, traces, commits, and files

## Testing Plan

### Unit Tests

- schema migration creates new tables
- fact insertion and update
- entity extraction
- ranker scoring
- supersession detection
- markdown rendering
- policy filtering
- redaction

### Integration Tests

- successful attempt creates accepted fact
- failed attempt creates failure candidate
- later attempt supersedes older workflow fact
- recall excludes superseded facts by default
- recall includes failed approaches separately
- context injection writes relevant memory
- graph HTML displays facts and evidence

### Regression Tests

- CJK literal search still works
- Codex prompt/exec echo does not become durable memory
- empty Git repo still creates baseline before worktree
- no remote service is required
- `.env` and secret patterns never enter durable facts

## Acceptance Gates

The implementation is not complete until:

1. Full test suite passes.
2. A fresh empty repo can run `ait init`, `direnv allow`, and `codex`
   without manual Git commit.
3. A successful agent run creates an accepted memory fact when the
   transcript contains a durable rule.
4. A failed agent run creates a failure candidate, not accepted durable
   memory.
5. A superseded workflow rule is not injected by default.
6. `ait memory search` can find accepted facts by CJK and ASCII queries.
7. `graph.html` shows memory facts with source attempts.
8. Generated markdown is deterministic.
9. No external memory service is required.
10. Package can be installed from PyPI in a clean virtualenv.

## Rollout Plan

### Phase 1: Schema And Read Models

- add tables
- add repositories
- add migrations
- add JSON rendering

### Phase 2: Deterministic Extraction

- classify existing candidate patterns
- extract entities deterministically
- write candidates and accepted facts

### Phase 3: Recall And Injection

- rank facts
- render context
- record retrieval events
- inject through wrappers

### Phase 4: Supersession

- detect replacement patterns
- mark old facts superseded
- expose in CLI and HTML

### Phase 5: Optional Semantic Ranking

- add embedding provider interface
- keep disabled by default
- store vectors only if configured

## Correctness Risks

- False memory extraction from agent speculation.
- Old facts injected after project changed.
- Prompt injection stored as memory.
- Memory grows until it harms token cost.
- Agent-specific transcript noise pollutes facts.

Mitigations:

- evidence references required
- conservative acceptance rules
- policy filtering
- supersession
- budgeted recall
- regression tests using real transcript patterns

## Implementation Decision

Implement AIT-native temporal memory first.

Do not add Graphiti, Mem0, or a vector database as required
dependencies in the default install. Add optional integration points only
after the local evidence-backed system is stable and benchmarked.
