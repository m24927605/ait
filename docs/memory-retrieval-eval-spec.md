# AIT Memory Retrieval Eval Spec

## Purpose

AIT already records which long-term memory facts were injected into an
agent run through `memory_retrieval_events`. This spec defines the next
production slice: `ait memory eval`.

The goal is to make memory retrieval quality inspectable and testable
without requiring users to understand AIT internals. Users should keep
using Claude Code, Codex, or Gemini normally; AIT should evaluate memory
quality in the background and expose concise reports when needed.

## Non-Goals

`ait memory eval` does not claim to prove semantic correctness with
human-level judgment.

It does not require:

- network access
- external LLM calls
- external vector databases
- manual labeling before the command can run

It does not replace code review or test execution. It gives evidence
about whether AIT selected plausible, current, and policy-allowed memory
for an agent context.

## Scope

In scope:

- evaluate recorded `memory_retrieval_events`
- score selected facts for freshness, status, confidence, and evidence
- detect missing high-signal facts with deterministic lexical/entity
  matching
- detect stale or superseded facts selected for context
- detect policy-invalid facts selected for context
- render text and JSON output
- support filtering by attempt id
- expose enough data for graph/report integration later

Out of scope for this slice:

- LLM-as-judge scoring
- embedding/vector scoring
- automatic mutation of memory facts
- changing the retrieval ranker
- changing agent wrapper behavior

## Command

```bash
ait memory eval [--attempt ATTEMPT_ID] [--limit N] [--format text|json]
```

Defaults:

- `--limit 50`
- `--format text`

Exit codes:

- `0`: command ran and no hard eval failure was found
- `1`: command ran and at least one hard eval failure was found
- `2`: invalid command arguments or repo/state errors

Hard eval failures:

- selected fact has `status` other than `accepted`
- selected fact is superseded
- selected fact was expired through `valid_to` at the retrieval event's
  `created_at` timestamp
- selected fact violates memory policy source/path rules

Warnings:

- selected fact confidence is not `high`
- selected fact has no trace, commit, or file evidence
- retrieval selected no facts even though candidate relevant facts exist
- likely relevant accepted facts were not selected

## Data Inputs

Primary tables:

- `memory_retrieval_events`
- `memory_facts`
- `memory_fact_entities`

The current slice does not require joins to `attempts` or `intents`
because `memory_retrieval_events.query` already captures the retrieval
query used for context construction. Later report integrations may join
attempt and intent metadata for display.

Policy inputs:

- `.ait/memory-policy.json`

Derived query text:

- `memory_retrieval_events.query`

The query is the same text used when building the context recall. It may
include intent title, description, kind, agent id, and command text.

## Eval Model

Each retrieval event receives:

- `status`: `pass`, `warn`, or `fail`
- `score`: integer from `0` to `100`
- `selected_count`
- `issue_count`
- `warning_count`
- `missing_relevant_fact_ids`
- `issues`
- `warnings`

### Scoring

Start from `100`.

Subtract:

- `40` for each selected fact that is not `accepted`
- `40` for each selected fact that is superseded or expired
- `40` for each selected fact blocked by policy
- `15` for each selected fact with confidence below `high`
- `10` for each selected fact without trace, commit, or file evidence
- `15` when no facts are selected but relevant facts are available
- `5` for each likely relevant accepted fact that was not selected,
  capped at `20`

Clamp the final score to `0..100`.

Status:

- `fail` if any hard eval failure exists
- `warn` if no hard failure exists but score is below `85` or warnings
  exist
- `pass` otherwise

## Relevance Heuristic

This slice uses deterministic retrieval-quality checks so tests are
stable.

For each retrieval event:

1. Normalize the query and facts to lowercase ASCII-compatible tokens.
2. Remove short tokens with length below three characters.
3. Score each accepted, non-superseded, non-expired fact:
   - `+3` for token overlap with `summary`
   - `+2` for token overlap with `body`
   - `+4` for matching memory entity text
   - `+1` for same topic token
4. A fact is "likely relevant" when score is at least `4`.
5. A selected fact is "supported by relevance" when its score is at
   least `2`.

This is intentionally conservative. It should catch obvious misses and
stale selections without pretending to solve full semantic evaluation.

## Policy Checks

An eval must flag a selected fact when:

- a logical source such as `attempt-memory:*` is not allowed by
  `recall_source_allow`
- a logical source is blocked by `recall_source_block`
- `source_file_path` matches a blocked recall source pattern
- `source_trace_ref` matches a blocked recall source pattern
- fact status is blocked by recall lint severity policy when such lint
  evidence exists in future schema

For this slice, logical source allow/block checks and path/source pattern
checks are required. Lint-severity joins are reserved because current
lint results are not stored per fact.

## Text Output

Example:

```text
AIT Memory Eval
Events: 2
Status: warn
Average score: 87

- event=<id> attempt=<short> status=pass score=100 selected=2
  query: Build release automation
  selected:
  - <fact-id> rule/release confidence=high status=accepted

- event=<id> attempt=<short> status=warn score=75 selected=0
  warnings:
  - no facts selected but 1 likely relevant fact exists
  missing relevant facts:
  - <fact-id> Run pytest before release
```

## JSON Output

Top-level schema:

```json
{
  "repo_root": "...",
  "status": "pass|warn|fail",
  "event_count": 0,
  "average_score": 100,
  "events": []
}
```

Event schema:

```json
{
  "event_id": "...",
  "attempt_id": "...",
  "query": "...",
  "status": "pass|warn|fail",
  "score": 100,
  "selected_count": 1,
  "issue_count": 0,
  "warning_count": 0,
  "selected_fact_ids": ["..."],
  "missing_relevant_fact_ids": ["..."],
  "issues": [],
  "warnings": [],
  "selected_facts": [
    {
      "id": "...",
      "kind": "rule",
      "topic": "release",
      "summary": "...",
      "status": "accepted",
      "confidence": "high",
      "relevance_score": 8
    }
  ]
}
```

## Acceptance Criteria

1. `ait memory eval` works in an initialized repo with no retrieval
   events and reports an empty passing result.
2. `ait memory eval --format json` emits parseable JSON.
3. `ait memory eval --limit -1` exits with code `2`.
4. A selected accepted high-confidence fact with evidence passes.
5. A selected candidate/rejected/superseded fact fails.
6. A selected fact blocked by memory policy fails.
7. A selected low-confidence fact warns.
8. A selected fact with no evidence warns.
9. A retrieval selecting no facts warns when likely relevant accepted
   facts exist.
10. A retrieval missing a likely relevant accepted fact lists it in
    `missing_relevant_fact_ids`.
11. `--attempt` filters events to one attempt.
12. Text output includes status, score, selected facts, warnings, and
    missing relevant facts.
13. JSON output includes stable keys suitable for tests and later graph
    integration.
14. The implementation requires no network access.
15. The full automated test suite passes.

## Review Requirements

Before release, a Staff-level review must cover:

1. Architecture and module boundaries:
   - eval logic must not be embedded directly in CLI formatting
   - DB repository APIs remain simple and deterministic
2. Data correctness:
   - stale, superseded, rejected, and policy-blocked facts are not
     treated as healthy retrievals
3. Developer experience:
   - command output must explain actionable problems without requiring
     users to inspect SQLite manually
4. Test coverage:
   - acceptance criteria above must be covered by automated tests where
     practical
5. Release readiness:
   - full tests, build, package check, and clean install smoke must pass

## Future Work

Later slices may add:

- graph.html integration for eval status
- historical trend summaries
- LLM-as-judge optional eval mode
- vector recall comparison
- automatic retrieval ranker tuning
- per-fact lint evidence joins
