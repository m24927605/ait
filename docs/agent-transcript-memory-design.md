# Agent Transcript Memory Design

## Goal

Close the long-term memory gap so that what the agent **said and decided**
during a session — not just what it changed — is durable, queryable, and
made available to future agents (same or different).

Today `ait` records intent, files, status, commits, and (for Claude Code
in hook mode) a *reference* to Claude's external `~/.claude/projects/...`
jsonl. The reference can break across machines or after a Claude Code
upgrade, and the conversation contents are not summarized for cross-agent
recall. Other agents (Codex, Aider, Gemini, Cursor) only have stdout.

This design closes that gap by:

1. **Persisting transcripts under `.ait/transcripts/`** so they survive
   external file churn and travel with the repo's `.ait/` directory.
2. **Adding hook adapters for non-Claude agents** so transcripts exist
   for every supported agent.
3. **Summarizing each transcript into a compact memory note** so cross-
   agent recall does not require rereading raw conversation text.
4. **Feeding the summary plus a bounded raw slice into the next agent's
   `AIT_CONTEXT_FILE`** with an explicit budget policy.

The four parts compose; this doc defines the shared surfaces so they
land cleanly in sequence.

## Non-Goals

- Do not claim the model itself has internal memory.
- Do not sync transcripts across machines or upload to any service.
- Do not require an external LLM dependency in `ait` runtime; summarizer
  must be optional and pluggable.
- Do not retain transcripts indefinitely without bound; storage policy
  applies.
- Do not redesign the existing memory note schema; transcripts and
  summaries plug into the existing memory layer.

## Architecture Overview

```
agent session
    |
    v
hook / wrapper captures transcript
    |
    v                        (step 2 + 3)
.ait/transcripts/<attempt>.jsonl   ←——— durable, repo-local
    |
    v                        (step 4)
summarizer (heuristic or LLM)
    |
    v
memory note (kind=transcript-summary)
    |
    v                        (step 1)
AIT_CONTEXT_FILE for next session
```

Each box is one of the four steps; arrows are the data flow. The
boundaries between steps are stable interfaces so they can be built and
shipped one at a time.

## Step 2 — Local-First Transcript Storage

### Layout

```
.ait/
  transcripts/
    <attempt-id>.jsonl     # raw, line-delimited JSON or plain text
    <attempt-id>.meta.json # source, agent, captured_at, byte_size
```

- One file per attempt. Filename uses the existing attempt ULID.
- Format follows whatever the upstream agent emits (jsonl for Claude
  Code; a normalized envelope for others — see Step 3).
- A `.meta.json` sibling carries provenance for redaction, age-based
  pruning, and `transcript_excluded` policy decisions without parsing
  the body.

### Capture path

For Claude Code hooks today, `claude_code_hook.py` reads
`payload["transcript_path"]` and stores it as `raw_trace_ref`. Step 2
adds:

1. Copy (or hardlink, when on the same filesystem) the upstream file
   into `.ait/transcripts/<attempt-id>.jsonl` at session end.
2. Write `<attempt-id>.meta.json` with `{source, agent_id, original_path,
   captured_at, byte_size, sha256}`.
3. Set `raw_trace_ref` to the **internal** relative path
   `transcripts/<attempt-id>.jsonl`.
4. The existing `_normalized_trace_path` already supports relative paths
   under the repo root; no consumer-side change is needed.

### Pruning policy

Adds `[transcripts]` block to `.ait/memory-policy.json`:

```jsonc
{
  "transcripts": {
    "retain_days": 90,            // 0 = forever
    "max_total_bytes": 524288000, // 500 MB cap
    "exclude_paths": ["secrets/**"]
  }
}
```

Pruning runs in the daemon reaper alongside `reap_stale_attempts`.

### Schema additions

`attempts` table gains two nullable columns (additive migration):

| Column | Type | Purpose |
| --- | --- | --- |
| `transcript_path` | TEXT | Internal `transcripts/<id>.jsonl` path |
| `transcript_byte_size` | INTEGER | For policy enforcement, no need to stat |

`raw_trace_ref` is kept for backward compatibility but its semantics
narrow to "the resolved path" — internal when present, external
otherwise.

## Step 3 — Hook Adapters for Other Agents

Goal: every supported adapter produces a `.ait/transcripts/<id>.jsonl`
on session end.

### Common envelope

Different agents use different formats. Step 3 normalizes them into a
**single jsonl envelope** that the summarizer (Step 4) can consume:

```jsonc
// One JSON object per line.
{"ts": "2026-05-04T12:00:00Z", "role": "user",      "text": "..."}
{"ts": "2026-05-04T12:00:01Z", "role": "assistant", "text": "..."}
{"ts": "2026-05-04T12:00:02Z", "role": "tool_use",  "tool": "Bash", "input": {...}}
{"ts": "2026-05-04T12:00:03Z", "role": "tool_result","tool": "Bash", "output": "...", "ok": true}
{"ts": "2026-05-04T12:00:04Z", "role": "assistant", "text": "..."}
```

Roles: `system | user | assistant | tool_use | tool_result | meta`.

For Claude Code, the existing jsonl is **already close to this shape**;
Step 2 stores it verbatim and the summarizer parses it. For other
agents, an adapter converts the upstream format on capture.

### Per-agent capture

| Agent | Mechanism |
| --- | --- |
| Claude Code | Existing hook + Step 2 verbatim copy |
| Codex CLI | Codex hooks (PostToolUse / SessionEnd) parallel to Claude's |
| Aider | Wrap stdin/stdout of `aider --message-log` and convert |
| Gemini CLI | Wrap stdin/stdout (Gemini has limited hooks) |
| Cursor | Best-effort — Cursor has weak CLI hooks; capture stdout only |
| Shell adapter | stdout/stderr only, single `assistant` line |

Each adapter's `setup` writes the appropriate hook config or wrapper.
The capture target is always `.ait/transcripts/<attempt-id>.jsonl` in
the common envelope.

## Step 4 — Transcript Summarizer

### What "summary" means

A compact memory note (~300–800 chars) covering:

- **Decisions made** ("chose foo over bar because …")
- **Approaches tried and abandoned**
- **Errors encountered and how they were resolved**
- **Open questions left for the user**
- **Tool calls of structural interest** (file writes, migrations,
  network calls) — not every Read/Grep

Schema: a regular `MemoryNote` with `kind=transcript-summary`,
`source=transcript-summary:<agent_id>`, `metadata={attempt_id,
transcript_path, summarizer_kind, summarizer_model}`.

### Pluggable summarizer

Two implementations, selected by `[summarizer]` in
`.ait/memory-policy.json`:

```jsonc
{
  "summarizer": {
    "kind": "heuristic",   // or "llm"
    "llm": {
      "provider": "anthropic",     // or "openai", "openai-compat", "ollama"
      "model": "claude-haiku-4-5-20251001",
      "api_key_env": "ANTHROPIC_API_KEY",
      "max_chars": 600
    }
  }
}
```

- `heuristic` (default, zero-dep): keep the **last assistant message**,
  every `tool_use` whose tool is in `{Write, Edit, MultiEdit,
  NotebookEdit, Bash}` plus the matching `tool_result.ok`, every
  `tool_result` with `ok=false`, plus a roll-up of changed files.
- `llm`: stdlib `urllib.request` POST to the chosen provider with the
  envelope as input, returning a structured summary. Optional, off by
  default; `ait` keeps no runtime dependency on any LLM SDK.

The summarizer is invoked from the daemon, **not** in-band of the
session, so it never blocks the agent. Failures fall back to heuristic.

## Step 1 — Context Injection With a Budget

### Layered context

`_write_context_file` already composes:

1. agent context
2. memory recall (notes)
3. repo memory text
4. repo brain briefing

Step 1 adds two new layers between (2) and (3):

5. **transcript summaries**: the summary memory notes for the N most
   recent relevant attempts (cross-agent). Always included.
6. **bounded raw transcript slice**: from the most recent attempt of the
   same intent (or same `agent_id` if no intent match), include up to
   `raw_transcript_chars` bytes of the last `assistant` message + last
   tool call/result pair. Optional, dropped first under budget pressure.

### Budget allocation

Default `AIT_CONTEXT_BUDGET_CHARS` (currently a single number) becomes a
proportional split:

```jsonc
{
  "context_budget": {
    "total": 24000,
    "shares": {
      "agent_context": 0.10,
      "memory_recall": 0.20,
      "transcript_summary": 0.20,
      "raw_transcript": 0.15,
      "repo_memory": 0.20,
      "repo_brain": 0.15
    },
    "drop_order": ["raw_transcript", "repo_brain", "repo_memory",
                   "transcript_summary", "memory_recall", "agent_context"]
  }
}
```

When the rendered text exceeds `total`, drop sections in `drop_order`
until it fits. This keeps the most decision-relevant content
(memory_recall, transcript_summary) and drops re-derivable content
(repo_brain, repo_memory) first.

## Memory Policy Extensions

`.ait/memory-policy.json` gains three new blocks. All optional with safe
defaults.

```jsonc
{
  "transcripts": { ... },     // Step 2 — pruning + exclusions
  "summarizer":  { ... },     // Step 4 — heuristic vs llm
  "context_budget": { ... }   // Step 1 — proportional allocation
}
```

Existing `transcript_excluded()` (which today only filters memory note
sources) is extended to also gate `.ait/transcripts/<id>.jsonl` capture
when the transcript content matches an exclusion rule (e.g., contains a
known secret pattern).

## Schema Migration

One new migration:

```sql
ALTER TABLE attempts ADD COLUMN transcript_path TEXT;
ALTER TABLE attempts ADD COLUMN transcript_byte_size INTEGER;
```

`raw_trace_ref` is kept. Reads prefer `transcript_path` and fall back to
`raw_trace_ref` for attempts created before the migration. No backfill
required — old external paths remain readable while they exist.

## Build Order

| Order | Step | Why first | Acceptance |
| --- | --- | --- | --- |
| 1 | **Step 2** | Portability blocks every other step | Claude transcript ends up in `.ait/transcripts/<id>.jsonl`; reaper prunes per policy |
| 2 | **Step 3** | Brings other agents to parity before summarizer is built | Codex + Aider produce envelope-format transcripts |
| 3 | **Step 4 (heuristic)** | Zero-dep, immediate value | Each attempt produces a `transcript-summary` memory note within seconds of session end |
| 4 | **Step 1** | Final consumer; needs everything above | New `transcript_summary` and `raw_transcript` layers appear in `AIT_CONTEXT_FILE` with budget enforcement |
| 5 | **Step 4 (llm, optional)** | Quality upgrade once heuristic is shipped | Configurable via memory-policy; falls back to heuristic on failure |

Each step ships in its own PR with its own acceptance test; later steps
must not regress earlier acceptance.

## Open Decisions (resolve before Step 4)

- **LLM provider abstraction.** Whether to ship `anthropic`,
  `openai-compat`, and `ollama` adapters from day one or start with
  `anthropic` only. Recommendation: start with `anthropic` + the
  zero-dep heuristic; add others on demand.
- **Summarizer trigger.** Daemon-side post-session vs. opportunistic on
  next session start. Recommendation: daemon-side, async, with
  on-the-fly fallback if a session starts before the summary lands.
- **Cross-machine portability.** Storing transcripts in `.ait/` means
  they may be `.gitignore`d by default (current behavior). Confirm: do
  we leave this off by default or expose a per-repo opt-in to commit
  summaries (not raw transcripts) into Git? Recommendation: keep all
  transcript artifacts out of Git; users can opt in via `.gitignore`
  override if desired.
- **Privacy in summaries.** A heuristic summary may reveal secret-bearing
  tool inputs (e.g., a `Bash` call containing an API key). Step 4 must
  redact via the existing `transcript_excluded` patterns before writing
  the summary note. Add explicit test coverage.

## Acceptance for Whole Design

A smoke test that exercises the full pipeline:

1. Run `ait init` + `ait adapter setup claude-code`.
2. Run a Claude session that edits a file and finishes.
3. Verify `.ait/transcripts/<id>.jsonl` exists.
4. Verify a `transcript-summary` memory note exists for the attempt.
5. Run `ait run --adapter codex -- codex` for a related intent.
6. Verify the new attempt's `AIT_CONTEXT_FILE` contains the previous
   Claude session's summary in a `Transcript summaries` section.
7. Verify the summary respects `transcripts.exclude_paths` if any
   matching tool input would otherwise leak.

## References

- `src/ait/runner.py` — `_write_context_file`, attempt lifecycle.
- `src/ait/memory/importers.py` — agent memory file import.
- `src/ait/memory/recall.py` — `build_relevant_memory_recall`.
- `src/ait/memory/common.py` — `_read_trace_text`, `_normalized_trace_path`.
- `src/ait/resources/claude-code/claude_code_hook.py` — current Claude
  hook capture path.
- `docs/long-term-memory-design.md` — existing memory layer it builds on.
- `docs/repo-brain-design.md` — repo brain context it composes with.
