# AIT Production Hardening Design

## Scope

This document defines an implementable plan for the remaining production
hardening work after `ait-vcs 0.55.3`.

Cursor and aider are explicitly out of scope for this plan. The supported
agent CLIs for this phase are:

- Claude Code
- Codex
- Gemini

## Current Proven Baseline

The following capabilities are proven by automated tests, local smoke
tests, and manual `ulivebuy` usage:

- `ait init` can initialize a Git repository and install wrappers for
  detected agent CLIs.
- Claude, Codex, and Gemini can be routed through repo-local wrappers.
- Wrapped sessions are recorded as intents and attempts.
- Attempt traces can be persisted under `.ait/traces/`.
- `ait graph` can show recorded intents and attempts.
- `ait memory` can render attempt memory notes and recent attempts.
- `ait graph --html` can render attempt transcript text through
  `raw_trace_ref`.
- Attempt workspaces can auto-commit agent changes.
- Attempt promote, rebase, and discard workflows exist.
- Some interrupted AIT post-agent cleanup paths no longer raise Python
  tracebacks.

## Remaining Problems

### P1. Memory Search Is Not Reliable Enough

Observed fact:

- `rg` finds `你是誰` in `.ait/traces/...txt`.
- `ait memory search 你是誰` returns no results.

Problem:

- The trace was captured, but the search layer did not recall a short
  Chinese query.

Impact:

- Users must know implementation details such as `.ait/traces` and `rg`.
- This violates the low-interruption product goal.

### P2. TUI Transcript Text Is Captured But Noisy

Observed fact:

- Codex full-screen TUI traces include duplicated prompt fragments,
  progress spinner text, layout redraw text, and terminal UI remnants.

Problem:

- ANSI control stripping is not enough. Full-screen TUIs redraw content
  repeatedly, and the resulting trace is searchable but not clean.

Impact:

- `graph.html` can show the conversation, but the transcript is hard to
  read and may confuse downstream memory extraction.

### P3. Memory Governance Is Still Mostly Mechanical

Observed fact:

- AIT records attempt memory notes and trace refs.
- Existing governance mostly covers policy exclusion, redaction, and
  context rendering.

Problem:

- The system does not yet classify which facts should become durable
  project memory.
- It does not distinguish durable decisions from transient chat.
- It does not merge repeated evidence into stable memory.

Impact:

- Long-term memory is useful as an audit trail, but not yet a strong
  project knowledge layer.

### P4. Semantic Outcome Verification Is Still Shallow

Observed fact:

- AIT can detect some refusal patterns and mark no-output refusal as
  failed.
- Most success/failure judgment still depends on process exit code,
  changed files, and commits.

Problem:

- A session can exit successfully but fail the user's actual intent.
- A session can produce no files because the task was informational and
  still be successful.

Impact:

- AIT cannot yet reliably govern whether an AI agent did the requested
  work.

### P5. Daemon Lifecycle Needs Stronger Guarantees

Observed fact:

- Test and smoke runs have produced many orphan `ait.cli daemon serve`
  processes.
- Idle timeout was added, but the lifecycle needs direct acceptance
  coverage in realistic process scenarios.

Problem:

- Long-running usage could still accumulate daemons if sockets, pid files,
  or process state drift.

Impact:

- Process table exhaustion or confusing daemon status can occur.

### P6. HTML Report Is Useful But Not Yet A Strong Investigation UI

Observed fact:

- `graph.html` can show attempts and transcript text.

Problem:

- It does not yet provide conversation-focused navigation, search,
  status badges tied to verification evidence, or trace cleanliness
  indicators.

Impact:

- Users can inspect history, but the report is not yet a polished
  debugging and governance interface.

## Product Principles

1. Low interruption:
   Users should keep invoking `claude`, `codex`, and `gemini`.

2. Local first:
   Memory, traces, graph, and reports remain repo-local unless the user
   explicitly exports them.

3. Evidence before claims:
   AIT should never claim an agent completed work without trace,
   file/commit evidence, tests, or an explicit classification reason.

4. Auditability:
   Every high-level memory or verification judgment must be traceable to
   attempts, traces, files, commits, or tests.

5. Graceful degradation:
   If intelligent extraction fails, raw trace and graph still work.

## Target Architecture

### Data Flow

```text
agent CLI
  -> AIT wrapper
  -> attempt workspace
  -> PTY/stdout transcript capture
  -> raw trace
  -> normalized transcript
  -> evidence extraction
  -> attempt verification
  -> durable memory candidates
  -> curated memory / graph / report / context injection
```

### Storage Layers

1. Raw trace:
   Stored as captured evidence under `.ait/traces/`.

2. Normalized transcript:
   A cleaned, readable transcript derived from raw trace.

3. Evidence index:
   Queryable facts derived from attempts, traces, files, commits, and
   tests.

4. Durable memory:
   Stable project facts that should be injected into future agent
   contexts.

5. Report:
   Static HTML generated from the graph, evidence index, and normalized
   transcript.

## Proposed Schema Additions

### `attempt_transcripts`

Purpose:

- Store normalized transcript metadata without replacing raw traces.

Columns:

- `attempt_id TEXT PRIMARY KEY`
- `raw_trace_ref TEXT NOT NULL`
- `normalized_trace_ref TEXT`
- `normalizer_version TEXT NOT NULL`
- `line_count INTEGER NOT NULL`
- `char_count INTEGER NOT NULL`
- `truncated INTEGER NOT NULL`
- `redacted INTEGER NOT NULL`
- `created_at TEXT NOT NULL`

### `memory_candidates`

Purpose:

- Store extracted candidate facts before promoting them into curated
  memory.

Columns:

- `id TEXT PRIMARY KEY`
- `attempt_id TEXT NOT NULL`
- `source_ref TEXT NOT NULL`
- `kind TEXT NOT NULL`
- `topic TEXT NOT NULL`
- `body TEXT NOT NULL`
- `confidence TEXT NOT NULL`
- `status TEXT NOT NULL`
- `reason TEXT NOT NULL`
- `created_at TEXT NOT NULL`

Allowed `kind`:

- `decision`
- `constraint`
- `workflow`
- `architecture`
- `test`
- `failure`
- `open-question`

Allowed `status`:

- `candidate`
- `accepted`
- `rejected`
- `superseded`

### `attempt_outcomes`

Purpose:

- Store semantic outcome judgments separate from process exit code.

Columns:

- `attempt_id TEXT PRIMARY KEY`
- `schema_version INTEGER NOT NULL`
- `outcome_class TEXT NOT NULL`
- `confidence TEXT NOT NULL`
- `reasons_json TEXT NOT NULL`
- `classified_at TEXT NOT NULL`

Allowed `outcome_class`:

- `pending`
- `succeeded`
- `succeeded_noop`
- `promoted`
- `failed`
- `failed_with_evidence`
- `failed_interrupted`
- `failed_infra`
- `discarded`
- `needs_review`

## Implementation Plan

### Milestone 1: Reliable Search Recall

Goal:

- `ait memory search <query>` must find literal trace content, including
  short Chinese queries.

Implementation:

1. Add a literal substring fallback in `src/ait/memory.py`.
2. Normalize query and evidence text with:
   - lowercase for ASCII
   - Unicode NFKC normalization
   - whitespace compaction
3. If query length is short or contains CJK characters, run literal
   matching before vector ranking.
4. Search sources must include:
   - curated notes
   - attempt memory notes
   - raw trace text
   - normalized transcript text when available
5. Return metadata:
   - `ranker=literal` for literal hits
   - `raw_trace_ref`
   - `match_start`
   - `match_end`
   - `snippet`

Files:

- `src/ait/memory.py`
- `tests/test_memory.py`
- `tests/test_cli_run.py`

Acceptance:

1. A trace containing `你是誰` is returned by:

   ```bash
   ait memory search 你是誰
   ```

2. A trace containing `我是 Codex` is returned by:

   ```bash
   ait memory search "我是 Codex"
   ```

3. A short session id fragment such as `019dd9ba` is returned when it
   exists in a trace.
4. JSON output includes `ranker: literal` for literal fallback hits.
5. Existing lexical and vector rankers still pass current tests.

### Milestone 2: Transcript Normalization

Goal:

- Raw TUI capture remains available, while reports and memory search use
  readable normalized transcripts.

Implementation:

1. Add `src/ait/transcript.py`.
2. Implement `normalize_transcript(text: str, adapter: str)`.
3. Common normalization:
   - strip ANSI and OSC control sequences
   - normalize CRLF/CR to LF
   - remove repeated adjacent identical progress lines
   - remove empty redraw fragments
   - cap repeated spinner/progress tokens
4. Codex-specific normalization:
   - preserve user turns after `›`
   - preserve assistant responses after bullet-style response markers
   - preserve token usage and resume command
   - drop repeated `Working`, `Starting MCP servers`, and title redraws
5. Claude/Gemini normalization:
   - use common normalization first
   - keep conservative rules until real traces prove safe adapter-specific
     cleanup.
6. Write normalized transcript to `.ait/traces/normalized/<attempt>.txt`.
7. Insert or update `attempt_transcripts`.
8. `graph.html` uses normalized transcript when available and raw trace
   as fallback.

Files:

- `src/ait/transcript.py`
- `src/ait/runner.py`
- `src/ait/report.py`
- `src/ait/db/schema.py`
- `src/ait/db/repositories.py`
- `tests/test_runner.py`
- `tests/test_cli_run.py`

Acceptance:

1. Raw trace still exists after a Codex TUI session.
2. Normalized trace exists after the same session.
3. Normalized trace contains:
   - `你是誰?`
   - `我是 Codex`
   - `codex resume ...`
4. Normalized trace does not contain large repeated `WorkingWorking`
   fragments.
5. `ait graph --html` displays normalized transcript by default.
6. If normalized transcript is missing, `graph.html` falls back to raw
   trace and indicates fallback mode.

### Milestone 3: Smart Memory Candidate Extraction

Goal:

- AIT should intelligently decide what is worth remembering, without
  requiring users to manually curate every fact.

Implementation:

1. Add deterministic extractor first, no LLM dependency.
2. Extract candidates from:
   - commit messages
   - changed file paths
   - test commands/results
   - transcript lines containing durable markers
3. Durable markers include:
   - "決定"
   - "以後"
   - "規則"
   - "不要"
   - "must"
   - "should"
   - "decision"
   - "constraint"
   - "workflow"
4. Reject noisy candidates:
   - greetings
   - pure token usage lines
   - progress UI
   - one-off questions without answer
5. Store in `memory_candidates`.
6. Promote high-confidence candidates into curated memory notes when:
   - attempt succeeded
   - confidence is `high`
   - memory policy does not exclude the source
7. Keep medium-confidence candidates visible in report, but do not
   inject automatically.

Files:

- `src/ait/memory.py`
- `src/ait/memory_policy.py`
- `src/ait/report.py`
- `src/ait/db/schema.py`
- `tests/test_memory.py`
- `tests/test_cli_run.py`

Acceptance:

1. A transcript containing `以後所有 API route 要使用 zod 驗證` creates a
   `constraint` memory candidate.
2. A successful attempt promotes the high-confidence candidate into a
   curated memory note.
3. A failed attempt keeps the candidate as advisory and does not inject
   it automatically.
4. Token usage lines do not become memory candidates.
5. `ait memory` shows accepted durable memory separately from recent
   attempts.
6. `graph.html` shows memory candidates under each attempt.

### Milestone 4: Semantic Outcome Verification

Goal:

- AIT should separate process success from task success.

Implementation:

1. Add outcome classifier in `src/ait/outcome.py`.
2. Inputs:
   - process exit code
   - raw/normalized transcript
   - changed files
   - commits
   - tests observed
   - prompt/intent title
3. Deterministic rules:
   - non-zero process exit -> `failed`, `failed_with_evidence`,
     `failed_interrupted`, or `failed_infra`
   - Ctrl-C during AIT cleanup -> `failed_interrupted`
   - refusal phrases with no changes -> `failed`
   - no changes and no durable evidence -> `succeeded_noop`
   - no file changes but durable memory candidates -> `succeeded`
   - successful changes plus commit -> `succeeded`
4. Store result in `attempt_outcomes`.
5. Report outcome in:
   - `ait graph`
   - `ait memory`
   - `graph.html`
6. Do not override `verified_status` until the outcome model proves
   stable. Surface semantic outcome as additional evidence first.

Files:

- `src/ait/outcome.py`
- `src/ait/runner.py`
- `src/ait/report.py`
- `src/ait/memory.py`
- `src/ait/db/schema.py`
- `tests/test_runner.py`
- `tests/test_cli_run.py`

Acceptance:

1. `I don't have permission...` with no changes yields:
   - effective exit `3`
   - verified status `failed`
   - outcome class `failed`
2. `hi` or pure chat with no changes yields:
   - process exit `0`
   - verified status `succeeded`
   - outcome class `succeeded_noop`
3. A file edit with auto commit yields:
   - outcome class `succeeded`
4. Ctrl-C during AIT cleanup yields:
   - command exit `130`
   - outcome class `failed_interrupted` when the interrupted process
     exit is persisted as non-zero
5. `graph.html` shows process status and semantic outcome separately.

Implemented status:

- `src/ait/outcome.py` contains the deterministic classifier.
- Migration v5 creates `attempt_outcomes`.
- `verify_attempt` writes the classification without changing the
  legacy `verified_status` enum.
- `ait run` JSON and text output include the outcome.
- `ait graph` and `graph.html` include `outcome=...`.
- Memory promotion now refuses to promote durable memory from
  `succeeded_noop` attempts.

### Milestone 5: Daemon Lifecycle Guarantees

Goal:

- AIT daemon processes must not accumulate under normal use.

Implementation:

1. Strengthen `daemon_status`:
   - verify pid belongs to an AIT daemon
   - verify the daemon socket is connectable
   - expose `pid_running`, `pid_matches`, `socket_connectable`, and
     `stale_reason`
   - clean stale pid/socket pairs
2. Add `ait daemon prune`.
3. On `start_daemon`, prune stale daemon state for the repo before
   launching.
4. Add idle timeout acceptance test with real daemon process:
   - start daemon
   - wait beyond configured short timeout
   - assert process exits
5. Add config override for tests:
   - `daemon_idle_timeout_seconds`
6. Do not kill unrelated user processes.
7. `ait doctor` and `ait status` should report daemon health:
   - running
   - stale pid
   - stale socket
   - idle timeout

Files:

- `src/ait/daemon.py`
- `src/ait/config.py`
- `src/ait/cli.py`
- `tests/test_daemon_concurrency.py`
- new `tests/test_daemon_lifecycle.py`

Acceptance:

1. A stale pid file is cleaned without traceback.
2. A stale socket is cleaned without traceback.
3. A daemon exits after configured idle timeout.
4. Starting AIT after stale state creates exactly one daemon.
5. Test suite leaves zero `ait.cli daemon serve` processes after daemon
   lifecycle tests.

Implemented status:

- `daemon_status` validates pid ownership and socket connectivity.
- `start_daemon` prunes stale daemon state before launching.
- `ait daemon prune` removes stale pid/socket state without starting a
  daemon.
- `stop_daemon` refuses to kill unrelated live pids.
- Real CLI smoke verifies stale cleanup, start/status/stop, and idle
  timeout shutdown.

### Milestone 6: Investigation-Grade HTML Report

Goal:

- `graph.html` should be useful for understanding past AI agent work
  without opening raw files.

Implementation:

1. Add top-level search/filter UI in static HTML JavaScript:
   - filter by agent
   - filter by status
   - filter by outcome
   - filter by transcript text
   - filter by file path
2. Add attempt cards inside graph nodes:
   - process exit
   - semantic outcome
   - changed files
   - commits
   - trace mode: normalized/raw/fallback
   - memory candidates
3. Show readable transcript mode:
   - normalized
   - raw fallback
4. Keep all content static and local.
5. Escape all injected content.
6. Do not load remote assets.

Files:

- `src/ait/report.py`
- `tests/test_cli_run.py`

Acceptance:

1. `ait graph --html` creates a self-contained HTML file.
2. The HTML contains transcript content for attempts with traces.
3. The HTML contains semantic outcome when available.
4. The HTML search box can hide/show attempts by text.
5. The HTML has no remote script, style, font, or image dependencies.
6. Sensitive excluded transcript text does not appear in HTML.

Implemented status:

- `graph.html` now includes local-only filter controls for text, agent,
  status, and outcome.
- Attempt nodes include `data-*` search metadata for client-side
  filtering.
- Outcome badges, status badges, changed files, commits, outcome
  reasons, memory candidates, and transcript mode are shown per attempt.
- The report remains self-contained: inline CSS/JS only, no remote
  assets.
- CLI smoke verified transcript search text, durable memory candidate
  display, and no `http://` / `https://` dependencies.

## Test Strategy

### Unit Tests

Required coverage:

- CJK literal search normalization
- literal fallback result metadata
- transcript normalizer common rules
- Codex transcript normalizer rules
- memory candidate extraction
- outcome classifier
- daemon stale pid/socket cleanup
- HTML transcript escaping

### Integration Tests

Required coverage:

- `ait run --adapter codex` with fake binary emitting Chinese text
- `ait memory search 你是誰`
- `ait graph --html` includes transcript
- `ait graph --html` excludes policy-blocked transcript
- interrupted AIT cleanup does not traceback
- daemon lifecycle exits on idle timeout

### Manual Smoke Tests

Use a temporary repo:

```bash
tmpdir="$(mktemp -d)"
mkdir "$tmpdir/repo"
cd "$tmpdir/repo"
git init
git config user.email test@example.com
git config user.name "Test User"
printf 'hello\n' > README.md
git add README.md
git commit -m init
ait init
```

Codex conversational smoke:

```bash
codex
```

Inside Codex:

```text
你是誰?
```

After Codex exits:

```bash
ait graph --agent codex
ait memory search 你是誰
ait graph --html
open .ait/report/graph.html
```

Expected:

- graph shows a finished Codex attempt
- memory search returns the attempt
- HTML shows the transcript
- no Python traceback appears

Codex file-change smoke:

```bash
codex
```

Inside Codex:

```text
建立 ait-smoke.txt，內容是 AIT_SMOKE_055X
```

After Codex exits:

```bash
ait graph --agent codex
ait memory search AIT_SMOKE_055X
ait graph --html
```

Expected:

- graph shows changed file or attempt workspace commit
- memory search returns trace or memory evidence
- HTML shows transcript and file evidence

## Release Gates

A release containing this plan is blocked unless all of the following
are true:

1. Full automated test suite passes.
2. `python -m build` succeeds.
3. `twine check dist/*` succeeds.
4. Clean venv can install the built wheel.
5. Manual Codex Chinese query smoke passes.
6. Manual `graph.html` transcript smoke passes.
7. Daemon process count is zero after smoke cleanup.
8. Existing Claude and Gemini smoke tests still pass.

## Rollout Plan

1. Implement Milestone 1 and release as a patch version.
2. Implement Milestone 2 and release as a patch version.
3. Implement Milestone 3 and 4 behind conservative defaults.
4. Implement Milestone 5 before any broader dogfood.
5. Implement Milestone 6 after normalized transcript storage is stable.

## Non-Goals

- No Cursor work.
- No aider work.
- No cloud memory service.
- No remote analytics.
- No guarantee that the LLM itself has permanent internal memory.
- No automatic push to remote Git.
- No automatic merge into the user's main branch without existing
  promote/rebase semantics.

## Definition Of Done

This hardening phase is done when:

- A user can run Claude, Codex, or Gemini normally.
- AIT records the session without requiring extra workflow commands.
- The user can search for a short Chinese phrase from the conversation
  and get the correct attempt.
- The user can open `graph.html` and see the conversation without
  opening `.ait/traces` manually.
- The transcript is readable enough for investigation.
- AIT distinguishes process success from semantic outcome.
- AIT does not expose Python tracebacks during normal post-agent
  cleanup interruption.
- AIT daemon processes do not accumulate under normal usage.
