# Zero-Interference Attempt Provenance And Memory Backfill Spec

Status: design and acceptance standard
Owner: AIT Staff Engineering Team
Scope: prompt capture, failure evidence, bypass detection, live inspection,
repo memory import, agent memory folder backfill, and code review standards.

## Executive Summary

AIT's attempt-first positioning remains valid only if the record around each
agent run is truthful and non-invasive. Worktree isolation, commits, review
gates, and apply/recover are useful, but they are not enough for an audit or
governance story when the prompt is missing, failed attempts have no error
context, or existing agent memory folders are ignored.

The product standard is:

> Every attempt must be explainable, and every backfilled memory item must be
> explicitly sourced, advisory by default, and imported with zero interference.

Zero interference means:

- never modify project source files during inspect, import, backfill, status,
  graph, or memory recall commands
- never modify agent global memory, session stores, or config files while
  reading them
- never create fake AIT attempts from inferred history
- never scan global agent folders unless the user explicitly opts in
- never send prompts, code, transcripts, or memory to a network service
- write durable imported metadata only under `.ait/`, and only after an
  explicit non-dry-run import/backfill command
- keep root checkout untouched until an explicit apply/merge/recover workflow

## Product Boundaries

AIT has two different evidence classes. They must never be blurred.

| Class | Source | Confidence | Allowed claim |
| --- | --- | --- | --- |
| Captured attempt evidence | A wrapped AIT run after adoption | Captured / verified | "AIT recorded this attempt." |
| Backfilled project memory | Repo files, Git history, agent memory folders, local session logs | Advisory unless manually accepted | "AIT imported or inferred this memory from a local source." |

Backfill can make an old project useful on day one. It cannot honestly
reconstruct the full prompt, transcript, review evidence, discarded attempts,
or agent decisions unless those exact artifacts already exist in local files.

## Problem Statement

When a project adopts AIT midstream, useful knowledge may already exist in:

- `CLAUDE.md`, `AGENTS.md`, `.cursor/rules*`, `.cursorrules`
- repo documentation, ADRs, READMEs, changelogs, and design notes
- Git commit messages and diffs
- Claude/Codex/Aider/Gemini/Cursor local memory folders or session logs
- developer-maintained notes outside the repo

The current implementation already imports some repo-local agent memory files
and can search AIT-recorded attempts. The remaining gap is a safe, explicit,
zero-interference way to discover and import broader local memory without
pretending it is native AIT provenance.

Current high-risk gaps:

1. `.ait/prompts/<attempt>.txt` can contain only the launched binary path,
   which is not the user's real prompt.
2. Failed attempts can appear with empty files, empty commits, missing exit
   context, and no obvious stderr/stdout path.
3. Repos can be initialized for AIT while users accidentally invoke a real
   agent binary directly; detection is passive or absent in the moment.
4. Agent global memory/session stores may contain relevant context, but
   scanning them by default would violate privacy and project boundaries.
5. `.ait/report/*` and repo brain reports are snapshots, but users may read
   them as live state.
6. `ait query --on attempt` is powerful but not discoverable as the answer to
   "what happened?"

## Goals

- A developer can inspect the latest attempt without knowing the query DSL.
- A failed attempt always has actionable evidence: exit code, failure reason,
  stderr/stdout tail when available, trace paths, workspace path, and next
  commands.
- A prompt record never pretends that a command path is the user's prompt.
- AIT records prompt capture status explicitly: captured, redacted,
  external-reference, unavailable, or bypassed.
- Direct-agent bypass is visible whenever AIT has a supported signal path.
- Midstream adoption can import existing local project knowledge as memory.
- Agent memory folders and session logs can be discovered and imported only by
  explicit opt-in, with source and confidence labels.
- Reports clearly distinguish generated snapshots from live inspection.
- All storage stays local under `.ait/`; no telemetry, no SaaS, no provider SDK
  dependency.

## Non-Goals

- Do not guarantee that generated code is correct.
- Do not block all direct agent execution globally; AIT may warn or record
  bypasses, but the user controls their shell.
- Do not auto-scan `~/.claude`, `~/.codex`, Cursor state, shell history, or
  other global agent folders during `ait init`.
- Do not mutate or clean up agent global memory/session stores.
- Do not scrape private upstream logs without an explicit local policy and
  bounded redaction path.
- Do not create AIT attempts from inferred Git history or imported session
  logs.
- Do not require cloud APIs or external LLMs to summarize or inspect attempts.
- Do not break existing `.ait/` state; migrations must be additive.

## Zero-Interference Rules

These rules are release blockers. Any violation is a Critical code review
finding.

1. **Dry-run means no writes.** `--dry-run` discovery/backfill commands must not
   write `.ait/`, source files, Git refs, or agent folders.
2. **Import writes only `.ait/`.** Non-dry-run import/backfill may write only
   AIT-owned files and database rows under `.ait/`.
3. **No source mutation.** AIT must never edit, chmod, move, delete, compact, or
   reformat imported source files or agent memory files.
4. **No global auto-discovery.** Repo-local discovery can be automatic; global
   agent folders require an explicit flag and source.
5. **No fake provenance.** Imported historical data must be `advisory` or
   `inferred` unless the source is exact captured AIT evidence.
6. **No hidden network.** Backfill, prompt capture, inspect, graph, recall, and
   status must not call external services.
7. **No checkout changes.** Discovery/import/inspect commands must leave
   `git status --short` unchanged except for ignored `.ait/` metadata.
8. **Bounded reads.** Source scans must honor file count, byte, age, and path
   limits so a repo or home directory cannot be accidentally vacuumed.
9. **Redaction first.** Durable prompt/transcript/memory content must pass
   redaction and memory policy before storage.
10. **Explain refusal.** If AIT refuses to read a source, the result must say
    why and how to opt in safely.

## Source Classes

### Class A - Repo-Local Agent Memory

These files are project-scoped and safe to discover automatically because they
live under the repo root:

```text
CLAUDE.md
.claude/memory.md
.claude/CLAUDE.md
AGENTS.md
.codex/memory.md
.codex/AGENTS.md
.cursor/rules
.cursor/rules.md
.cursorrules
```

Current behavior: AIT can import these as memory notes with
`source=agent-memory:<agent>:<path>` and advisory confidence.

Required behavior:

- Read only.
- Apply memory policy exclusions.
- Redact before storing.
- Store imported note under `.ait/`.
- Re-import only when source signature changes.
- Never edit the source memory file.

### Class B - Repo Documentation And Git History

Repo docs and Git history can seed project memory but not attempt provenance.

Allowed sources:

- tracked Markdown and text docs
- ADRs, changelogs, design docs, release notes
- commit messages and selected diff metadata

Required behavior:

- Imported or inferred facts are advisory by default.
- Commit-derived records must cite commit SHA and path/diff summary.
- No commit-derived record may claim a prompt, agent identity, review result,
  or discarded attempt unless that exact evidence exists.

### Class C - Agent Global Memory And Session Stores

Examples:

- Claude local project/session directories
- Codex local session/log directories
- Aider chat history outside the repo
- Gemini local state
- Cursor local/global rules or agent history

Required behavior:

- Never scanned by default.
- Requires explicit source and opt-in flag, for example:

```bash
ait memory backfill --source claude --global --dry-run
ait memory backfill --source codex --sessions --since 30d --dry-run
ait memory import --path ~/.claude/projects/<repo-id>/session.jsonl
```

- Source files are read-only.
- Imported records are advisory unless the source has an exact repo/project
  match.
- Project matching must be explicit in metadata:
  `project_match=exact|inferred|unknown`.
- Unknown or inferred project matches must not be auto-recalled into future
  agent context unless policy allows them.

### Class D - Captured AIT Attempts

Attempts created after AIT adoption remain the highest-confidence source.

Required behavior:

- Prompt, transcript, failure, files, commits, review, and apply state are
  attached to the attempt record.
- These records can become accepted facts only through the existing memory
  policy and fact lifecycle.

## Data Contracts

### Prompt Record

Each attempt should have a prompt record and metadata:

```json
{
  "schema_version": 1,
  "attempt_id": "repo:install:01...",
  "adapter": "codex",
  "capture_status": "captured",
  "capture_source": "argv:prompt-flag",
  "redacted": false,
  "truncated": false,
  "prompt_ref": ".ait/prompts/<attempt-id>.txt",
  "external_ref": null,
  "unavailable_reason": null
}
```

Allowed `capture_status` values:

| Status | Meaning |
| --- | --- |
| `captured` | AIT captured prompt text locally. |
| `redacted` | AIT captured content but redacted sensitive portions. |
| `external_ref` | AIT only has a local upstream transcript path or session ID. |
| `unavailable` | No supported prompt source existed. |
| `bypassed` | Evidence indicates an agent session ran outside the wrapper. |

The prompt text file may include the command for context, but command path alone
does not satisfy `captured`.

### Backfilled Memory Record

Backfilled memory must carry source, confidence, and project-match metadata:

```json
{
  "schema_version": 1,
  "record_id": "memory-backfill:claude:...",
  "source_kind": "agent-global-session",
  "source": "claude",
  "source_path": "~/.claude/projects/.../session.jsonl",
  "source_sha256": "...",
  "project_match": "inferred",
  "confidence": "advisory",
  "status": "candidate",
  "body_ref": ".ait/memory/imports/<record-id>.txt",
  "created_at": "2026-05-14T00:00:00Z",
  "redacted": true,
  "truncated": false,
  "never_fake_attempt": true
}
```

Allowed `source_kind` values:

- `repo-agent-memory`
- `repo-doc`
- `git-commit`
- `agent-global-memory`
- `agent-global-session`
- `manual-path`

Allowed `project_match` values:

- `exact`
- `inferred`
- `unknown`

Allowed `confidence` values:

- `captured`
- `extracted`
- `inferred`
- `advisory`

Only captured AIT attempt evidence can default to trusted. Backfilled records
default to advisory.

### Failure Context

Every failed attempt should expose:

```json
{
  "schema_version": 1,
  "attempt_id": "repo:install:01...",
  "exit_code": 1,
  "failure_phase": "agent-command",
  "failure_reason": "command exited non-zero",
  "stdout_tail_ref": ".ait/traces/<attempt-id>.stdout.tail.txt",
  "stderr_tail_ref": ".ait/traces/<attempt-id>.stderr.tail.txt",
  "raw_trace_ref": ".ait/traces/<attempt-id>.txt",
  "last_event": {
    "event_type": "tool_result",
    "tool": "Bash",
    "ok": false
  },
  "workspace_ref": ".ait/workspaces/attempt-0001-...",
  "recommended_commands": [
    "ait inspect latest",
    "ait attempt show <attempt-id>",
    "ait recover <attempt-id>"
  ]
}
```

Failure phases:

- `preflight`
- `wrapper`
- `agent-command`
- `hook`
- `harness`
- `postprocess`
- `verification`
- `review`
- `apply`

### Bypass Event

```json
{
  "schema_version": 1,
  "ts": "2026-05-14T00:00:00Z",
  "adapter": "codex",
  "command": "codex",
  "cwd": "/repo",
  "reason": "native hook ran without AIT_ATTEMPT_ID",
  "recommended_command": "eval \"$(ait init --shell)\""
}
```

Bypass events must never create fake successful attempts. They can appear in
`ait status`, `ait inspect`, and graph health panels.

## Prompt Capture Design

### Capture Priority

1. Explicit AIT input: future `ait run --prompt`, `--prompt-file`, or adapter
   wrapper-provided prompt metadata.
2. Adapter-specific argv extraction, for flags such as `-p`, `--prompt`,
   `--message`, or equivalent.
3. Non-TTY stdin capture, with a byte budget and redaction.
4. Native transcript ingestion from Claude Code, Codex, Gemini, Aider, Cursor,
   or shell adapter output.
5. External reference to upstream local session log, when AIT can prove the
   path belongs to the attempt.
6. Explicit unavailable record with `unavailable_reason`.

### Required Behavior

- `_record_command_as_prompt` must be renamed or narrowed so it cannot be
  mistaken for a true prompt capture.
- Adapter prompt extractors must return structured metadata, not just text.
- Interactive sessions without accessible transcript must produce a prompt
  record like:

```text
# capture_status: unavailable
# unavailable_reason: interactive session had no supported transcript source
# command: /path/to/codex
```

- When capture is unavailable, `ait inspect` and `ait attempt show` must say
  where to look next, or state that AIT has no reliable source.

### Privacy Rules

- Prompt and transcript capture must pass through existing redaction.
- Policy exclusions must apply before writing durable raw content.
- Large content is truncated with an explicit marker and metadata.
- Secrets found in prompt/transcript tests are release blockers.

## Failure Evidence Design

AIT must write a trace record even when:

- the real agent binary is missing
- wrapper recursion is detected
- the command exits before hooks initialize
- the daemon is unavailable and the run falls back to local-only mode
- the agent exits non-zero without file changes
- postprocessing fails after the agent exits

`ait attempt show` should include a compact failure block in text and JSON.
`ait graph --html` should show failure reason and trace availability, not only
status counts.

## Bypass Detection Design

Bypass detection cannot be perfect unless AIT controls the user's shell. The
standard is "no silent miss when AIT has a supported signal path."

### Signal Paths

| Signal path | Required behavior |
| --- | --- |
| `ait status <adapter>` | Detect wrapper not first on PATH and give exact shell command. |
| `eval "$(ait init --shell)"` | Put `.ait/bin` before real binaries for this shell. |
| Native hooks | If an agent hook fires without `AIT_ATTEMPT_ID`, record a bypass event under `.ait/bypass-events.jsonl`. |
| Optional shell integration | Preexec guard can warn when `claude`, `codex`, `aider`, `gemini`, or `cursor` is invoked in an AIT repo without wrapper PATH. |

Warning-only shell integration is allowed. Blocking direct agent execution is
not allowed unless the user has explicitly enabled an enforcement policy.

## Zero-Interference Backfill Design

### Discovery Command Shape

Future command shape:

```bash
ait memory backfill --dry-run
ait memory backfill --source auto --repo-only --dry-run
ait memory backfill --source claude --global --since 30d --dry-run
ait memory backfill --source codex --sessions --path ~/.codex/sessions --dry-run
ait memory backfill --source claude --global --import
```

Required modes:

- `--dry-run`: discover and report candidate sources; no writes anywhere.
- `--repo-only`: restrict to repo root.
- `--global`: permit explicit global agent memory discovery.
- `--path`: import only an explicit path.
- `--since`: cap session/log age.
- `--max-files` and `--max-bytes`: enforce bounded reads.
- `--import`: write selected imported records under `.ait/`.

### Discovery Output

Dry-run output must make side effects obvious:

```json
{
  "schema_version": 1,
  "mode": "dry-run",
  "writes_performed": false,
  "candidate_count": 3,
  "candidates": [
    {
      "source_kind": "repo-agent-memory",
      "source": "codex",
      "path": "AGENTS.md",
      "project_match": "exact",
      "would_import": true,
      "confidence": "advisory"
    }
  ],
  "skipped": [
    {
      "path": "~/.claude/projects/other-repo/session.jsonl",
      "reason": "project match unknown; use --include-unknown to import as advisory"
    }
  ]
}
```

### Import Behavior

Import writes only:

- `.ait/memory/imports/*`
- `.ait/state.sqlite3`
- `.ait/memory/*` import state files

Import must not write:

- source files
- Git index
- Git refs
- worktree files outside `.ait/`
- agent global memory/session folders
- agent config files

## Live Inspection And Discoverability

Add or standardize task-oriented commands:

| User question | Command |
| --- | --- |
| What just happened? | `ait inspect latest` |
| What did this attempt do? | `ait inspect <attempt-id>` |
| Where is the raw evidence? | `ait inspect <attempt-id> --json` |
| What memory can AIT import without touching anything? | `ait memory backfill --dry-run` |
| What global agent memory could I opt into? | `ait memory backfill --source claude --global --dry-run` |
| Show recent agent work | `ait attempt list --limit 10` |
| Open the visual report | `ait graph --html` |

`ait --help` should include a short "Common questions" section:

```text
What did the latest agent run do?  ait inspect latest
Why did it fail?                  ait inspect latest --json
What can AIT import safely?       ait memory backfill --dry-run
Did my shell bypass AIT?          ait status claude-code
Where is the visual report?       ait graph --html
```

Snapshot reports must show:

- `generated_at`
- `latest_attempt_id`
- "This is a snapshot"
- refresh command
- live inspection command

## Implementation Plan

### Phase 0 - Baseline Characterization

- Add failing tests that reproduce command-only prompt files.
- Add failing tests for empty failed-attempt evidence.
- Add failing tests for native hook events without `AIT_ATTEMPT_ID`.
- Add failing tests proving dry-run backfill writes nothing.
- Add help snapshot tests for the discoverability section.

### Phase 1 - Zero-Interference Source Registry

Files likely touched:

- new `src/ait/memory/backfill.py`
- `src/ait/memory/importers.py`
- `src/ait/memory_policy.py`
- `src/ait/cli_parser.py`
- `src/ait/cli/memory.py`

Work:

- Model repo-local, explicit path, and global agent memory sources.
- Implement dry-run source discovery.
- Enforce file count, byte, age, path, and symlink traversal limits.
- Return skipped reasons instead of raising for normal privacy boundaries.
- Add tests that source mtimes/hashes and Git status do not change.

### Phase 2 - Prompt Capture Contract

Files likely touched:

- `src/ait/runner.py`
- `src/ait/runner_transcript.py`
- `src/ait/transcript.py`
- adapter resources under `src/ait/resources/*`
- `src/ait/db/schema.py`
- `src/ait/db/*repositories.py`
- `src/ait/app.py`
- `src/ait/cli/attempt.py`

Work:

- Add additive prompt metadata storage.
- Build adapter-specific prompt extractors.
- Capture non-TTY stdin within budget.
- Write unavailable records instead of misleading command-only prompt records.
- Surface prompt capture status in `show_attempt`.

### Phase 3 - Failure Context

Files likely touched:

- `src/ait/runner.py`
- `src/ait/events.py`
- `src/ait/verifier.py`
- `src/ait/run_report.py`
- `src/ait/report/html.py`
- `src/ait/cli/attempt.py`

Work:

- Always write trace evidence for failed phases.
- Build `failure_context` from runner, hook, harness, and verifier paths.
- Add stdout/stderr tail refs with redaction and truncation.
- Surface failure context in `ait attempt show`, `ait graph --html`, and
  future `ait inspect`.

### Phase 4 - Bypass Detection

Files likely touched:

- `src/ait/adapter_doctor.py`
- `src/ait/adapter_setup.py`
- `src/ait/resources/claude-code/claude_code_hook.py`
- `src/ait/resources/codex/codex_hook.py`
- `src/ait/resources/gemini/gemini_hook.py`
- `src/ait/shell_integration.py`
- `src/ait/cli/status_helpers.py`

Work:

- Record bypass events from native hooks that lack AIT attempt env.
- Add shell integration warning path where supported.
- Show recent bypass events in `ait status`.
- Keep detection local-only, warning-only by default, and non-blocking.

### Phase 5 - Advisory Memory Import

Files likely touched:

- `src/ait/memory/backfill.py`
- `src/ait/memory/importers.py`
- `src/ait/memory/repository.py`
- `src/ait/db/schema.py`
- `src/ait/memory/recall.py`

Work:

- Import selected backfill records into `.ait/` only.
- Mark all global/session imports as advisory unless exact project evidence is
  present.
- Keep advisory backfill out of trusted recall unless policy opts in.
- Add source, hash, project match, confidence, redaction, and truncation
  metadata.
- Never create attempts from imported history.

### Phase 6 - Inspection UX

Files likely touched:

- `src/ait/cli_parser.py`
- new `src/ait/cli/inspect.py` or equivalent
- `src/ait/report/*`
- `site-docs/reference/commands.md`

Work:

- Add `ait inspect latest|<attempt-id>` with text and JSON.
- Make `ait --help` route common questions.
- Add docs examples for "what did Codex do?"
- Clarify snapshot vs live report semantics.

## Test Plan

### Unit Tests

- Prompt extractor per adapter:
  - Codex argv prompt
  - Claude `-p` prompt
  - Aider message input
  - Gemini prompt flag
  - shell adapter command/stdin
- Redaction and truncation for prompt, stdout, stderr, transcript, and
  imported memory.
- Prompt unavailable records are explicit and queryable.
- Failure context builder maps each phase to stable `failure_phase`.
- Bypass event parser validates schema and ignores malformed hook payloads.
- Backfill source registry rejects global sources unless explicitly enabled.
- Backfill dry-run returns candidates without creating files or DB rows.
- Schema migration is additive and preserves old attempts.

### Integration Tests

- `ait memory backfill --dry-run` leaves `git status --short` unchanged and
  creates no `.ait/memory/imports` files.
- Repo-local `AGENTS.md` import writes only `.ait/` records and does not touch
  `AGENTS.md`.
- Explicit global source import reads from a temp fake home directory, writes
  only `.ait/`, and marks records advisory.
- Unknown project match is skipped by default or imported only with an explicit
  advisory override.
- Symlink and path traversal fixtures cannot cause writes outside `.ait/`.
- `ait run --adapter codex -- fake-codex --prompt "fix auth"` records the
  user prompt, not only the fake binary path.
- Non-TTY stdin prompt is captured with redaction.
- Interactive fake agent without transcript writes `capture_status=unavailable`.
- Missing real binary creates a failed attempt with wrapper failure context.
- Non-zero fake agent with stderr creates trace, stderr tail, and recommended
  commands.
- Native hook without `AIT_ATTEMPT_ID` records a bypass event but no fake
  successful attempt.
- `ait inspect latest` answers prompt status, outcome, files, commits, trace,
  failure context, and imported-memory warnings.
- `ait graph --html` displays generated timestamp, snapshot label, failure
  reason, and trace link.
- `ait --help` includes common questions.

### Privacy And Safety Tests

- Secret-like prompt text is redacted before durable storage.
- Secret-like imported memory is redacted before durable storage.
- `transcript_excluded` policy prevents durable raw transcript writes.
- Global agent memory is not scanned on `ait init`, `ait status`, `ait memory`,
  or `ait memory backfill --repo-only`.
- Bypass detection does not upload, phone home, or call provider SDKs.
- Failed run evidence never overwrites user files.
- Tests use fake agents and fake memory folders only; no real
  Claude/Codex/API/network dependency.

## Acceptance Criteria

This work is not accepted until all criteria are true:

1. For supported non-interactive prompts, `.ait/prompts/<attempt>.txt` contains
   the real user prompt or a redacted/truncated form of it.
2. No prompt record with only an executable path reports `capture_status` as
   `captured`.
3. Every failed attempt has a failure context visible from a single command.
4. `ait inspect latest --json` exposes prompt status, trace refs, failure
   context, files, commits, review status, imported-memory warnings, and
   bypass warning state.
5. Direct native-hook sessions without `AIT_ATTEMPT_ID` create bypass events.
6. `ait memory backfill --dry-run` performs zero writes.
7. Backfill import writes only under `.ait/`.
8. Source files, global agent folders, Git refs, and root checkout files remain
   byte-for-byte unchanged by import/backfill/inspect/status commands.
9. Global agent memory/session folders are never scanned unless explicitly
   requested.
10. Backfilled global/session records are advisory by default and never become
    fake AIT attempts.
11. Snapshot reports clearly identify themselves as snapshots and link to live
    inspection commands.
12. `ait --help` makes the "what did the agent do?" and "what can AIT import?"
    paths obvious.
13. Existing attempts from older schemas remain readable.
14. All new data remains local under `.ait/`.
15. Release docs stop making broad audit/governance claims unless these
    criteria pass.

## Code Review Standard

Reviewers must treat this area as a trust boundary. Findings should be graded
as follows:

| Severity | Release impact | Examples |
| --- | --- | --- |
| Critical | Block release | Prompt falsely marked captured; secrets stored unredacted; failed attempt loses evidence; migration breaks old state; backfill writes outside `.ait/`; global agent memory scanned without opt-in; source/global memory file modified. |
| High | Block release unless explicitly scoped out | Silent bypass in a supported hook path; `ait inspect` omits failure reason; trace/import path points outside allowed local policy; advisory global memory enters trusted recall by default. |
| Medium | Fix before broad release | Help text misleading; graph snapshot not labeled; unsupported adapter lacks unavailable reason; backfill skipped reason is unclear. |
| Low | Follow-up acceptable | Copy clarity, minor formatting, non-critical docs drift. |

Required review evidence:

- Show one passing prompt capture fixture per touched adapter.
- Show one failed attempt fixture with stderr/stdout evidence.
- Show one bypass fixture when hook/shell integration is touched.
- Show one zero-write dry-run backfill fixture.
- Show one explicit global-memory import fixture that writes only `.ait/` and
  marks records advisory.
- Show redaction/truncation behavior for prompt, transcript, or imported
  memory content.
- Show before/after CLI output for `ait inspect latest`, `ait memory backfill
  --dry-run`, and `ait --help`.
- Confirm no network/provider SDK dependency was added.
- Confirm schema migrations are additive and old attempts still load.
- Confirm source mtimes/hashes and `git status --short` are unchanged except
  for ignored `.ait/` metadata.

Required local checks before requesting review:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_query.py -q
PYTHONPATH=src uv run pytest tests/test_*transcript*.py tests/test_*hook*.py -q
PYTHONPATH=src uv run pytest tests/test_cli_adapters.py tests/test_cli_attempt_list.py -q
PYTHONPATH=src uv run pytest tests/test_memory*.py -q
git diff --check
```

If review, runner, DB schema, memory backfill, or report generation is touched,
also run:

```bash
PYTHONPATH=src uv run pytest -q
/tmp/ait-docs-venv/bin/mkdocs build --strict
```

## Release Gate

Any release that claims auditability, governance, attempt provenance, prompt
history, failure explainability, bypass detection, or memory backfill must pass
this spec's acceptance criteria. If a release only improves worktree isolation
or apply gating, the release notes must avoid implying complete agent-work
auditability or historical memory reconstruction.

