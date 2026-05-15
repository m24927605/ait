# AIT Live Federated Memory Design

Status: design, implementation, test, acceptance, and code review standard
Owner: AIT Staff Engineering Team
Scope: single-agent long-term memory, cross-agent shared memory, cross-agent
long-term memory, live recall, zero-touch source discovery, and review
standards.

## Executive Summary

AIT 要解決的 memory 問題不是「把 Claude、Codex、Cursor 的記憶匯入
`.ait/`」。

正確方向是：

> AIT provides a live federated repo memory view. Every agent sees the same
> current project memory, assembled at read time from AIT-native evidence and
> live repo-local agent memory sources.

這代表：

- `CLAUDE.md`、`AGENTS.md`、`.cursor/rules` 等檔案仍是自己的 source of truth。
- AIT 不預設 copy、import、materialize、backfill 這些外部 agent memory。
- AIT 每次 `run`、`review`、`memory recall` 都即時讀最新來源。
- AIT 自己產生的 attempts、prompts、traces、review findings、accepted facts
  才是 AIT-native long-term memory，存在 `.ait/`。
- Read-only memory commands 不寫 `.ait/`，也不修改來源檔。
- 若未來需要把外部 memory 轉成 AIT-owned facts，必須是明確的
  `adopt` / `materialize` 類指令，而且文件必須標成 mutation，不得稱為
  zero-interference。

## Product Standard

AIT memory 的產品標準：

> One repo, one live memory view, many agents.

使用者期待的是：

1. 單一 agent 長期記憶：同一個 agent 下次回來時知道過去 AIT evidence。
2. 跨 agent 共同記憶：Claude、Codex、Aider、Gemini、Cursor 看到同一份 repo
   context。
3. 跨 agent 長期記憶：一個 agent 的成功 attempts、review findings、accepted
   facts，能在之後被另一個 agent 使用。
4. 隨時即時：改了 `CLAUDE.md` 或 `AGENTS.md` 後，下一次 recall/run/review
   馬上看到，不需要 import。
5. 零干擾：只是 inspect / sources / recall，不應該建立或修改 `.ait/`。

## Current Gap

目前 AIT 已有 repo-local memory、attempt memory、memory search、memory recall、
agent memory import/backfill 等能力，但有一個產品語意問題：

- `ait init` / `ait run` 會呼叫 `ensure_agent_memory_imported(...)`，把已知
  repo-local agent memory 檔案寫成 `.ait/` memory notes。
- `ait memory backfill --import` 會寫 `.ait/`。
- 這些行為不會修改來源檔，但仍然是 AIT-local mutation。
- 因此它們不能被稱為 zero-interference。

本文件修正方向：

> AIT should see external agent memory live, not adopt it by default.

## Definitions

| Term | Meaning |
| --- | --- |
| AIT-native memory | AIT 自己產生並擁有的長期記憶，例如 attempts、prompts、traces、review findings、accepted facts、apply history。 |
| Live external memory source | Repo 內既有 agent/project memory 檔，例如 `CLAUDE.md`、`AGENTS.md`、`.cursor/rules`。AIT 可即時讀，但不擁有。 |
| Federated recall | 每次 recall/run/review 即時組合 AIT-native memory 與 live external sources。 |
| Source manifest | AIT 在某次 run/review 中實際使用的 memory source 清單、hash、mtime、byte range、policy result。 |
| Adopt/materialize | 使用者明確要求 AIT 把外部 memory 轉成 AIT-owned copy/fact。這是 mutation，不是零干擾。 |
| Cache/index | 可重建的加速資料，不是 source of truth。若來源變更，必須失效或 read-through 更新。 |

## Non-Negotiable Principles

1. **Live by default.** External agent memory is read at use time.
2. **No auto adoption.** AIT must not automatically import external memory into
   `.ait/`.
3. **Zero-touch read commands.** `ait memory sources`, read-only
   `ait memory recall`, and status-style commands must not write `.ait/`.
4. **AIT runs may write AIT evidence.** A wrapped `ait run` already creates
   AIT-native attempt evidence under `.ait/`. It may record which live memory
   sources were used for that attempt.
5. **Source of truth stays outside AIT.** `CLAUDE.md` remains Claude/project
   memory; `AGENTS.md` remains agent/project instructions; `.cursor/rules`
   remains Cursor rules.
6. **No hidden global scan.** Repo-local sources can be discovered. Global or
   out-of-repo agent memory requires explicit path and flag.
7. **No hidden network.** Memory discovery, recall, indexing, and source
   federation must not call external services.
8. **Policy first.** Path allow/deny, redaction, max bytes, symlink handling,
   and source authority must be applied before content reaches a context file.
9. **Truthful confidence.** Live external memory can be trusted as current
   source text, but not as AIT provenance.
10. **No stale claims.** Cached/indexed content must never be presented as live
    if source hash/mtime changed.

## Memory Source Model

### AIT-Native Sources

AIT owns these and may write them under `.ait/`:

- attempt records
- prompt records
- transcript/trace records
- changed files and commit metadata
- review records and findings
- apply/recover outcomes
- accepted memory facts
- retrieval evidence created during an AIT run/review

These are the strongest sources because AIT captured them.

### Live Repo-Local Agent Sources

AIT should discover these by default, read-only:

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

Rules:

- Discovery is allowed.
- Reading is allowed.
- Source mutation is forbidden.
- Auto import into `.ait/` is forbidden.
- Recall must read current file content at execution time.
- Source metadata must include path, source kind, hash, size, mtime, and policy
  result.

### Repo Documentation Sources

Optional live sources:

- `README.md`
- `docs/**/*.md`
- ADRs
- changelogs
- design notes

These can be included by policy and ranking, but should not drown out explicit
agent memory sources.

### Global Or Out-Of-Repo Sources

Examples:

- `~/.claude/**`
- `~/.codex/**`
- Cursor global state
- shell history
- Aider chat history outside the repo

Rules:

- Never scanned by default.
- Requires explicit `--global --path ...`.
- Must be read-only.
- Must be labeled `project_match=exact|inferred|unknown`.
- Unknown/inferred global memory must not be injected by default.

## Proposed CLI Surface

### Source Discovery

Read-only. No `.ait/` writes.

```bash
ait memory sources
ait memory sources --format json
ait memory sources --source claude
ait memory sources --include-docs
ait memory sources --global --path ~/.claude/projects/<id>
```

Output should answer:

- What live sources does AIT see?
- Which agent/project source does each represent?
- Is it allowed by memory policy?
- What is its current hash/mtime/size?
- Would it be eligible for run/review context?
- Why was a source skipped?

### Live Recall

Read-only by default. No `.ait/` writes.

```bash
ait memory recall "auth flow"
ait memory recall "auth flow" --format json
ait memory recall "auth flow" --include-sources
```

Result contains:

- ranked live external source excerpts
- ranked AIT-native memory facts/attempt summaries
- source manifest
- policy exclusions
- no durable retrieval event unless explicitly requested

If recording recall diagnostics is needed:

```bash
ait memory recall "auth flow" --record
```

`--record` is a mutation and must say it writes `.ait/`.

### Run / Review Context Injection

Wrapped runs and reviews assemble memory live:

```bash
ait run --adapter claude-code -- claude
ait review attempt latest-reviewable --mode adversarial --review-adapter codex
```

At execution time AIT should:

1. discover allowed live sources
2. read current source content
3. combine with AIT-native memory
4. rank and budget the context
5. write `AIT_CONTEXT_FILE` for the child process
6. record a source manifest in attempt/review evidence

Recording the manifest is allowed because the user is executing an AIT-owned
run/review, which already writes AIT evidence.

### Adoption / Materialization

If AIT keeps a command that writes external memory into `.ait/`, it must not be
named or described as zero-touch.

Preferred future command:

```bash
ait memory adopt CLAUDE.md
ait memory adopt --source codex AGENTS.md
ait memory materialize --source cursor .cursor/rules
```

Required copy:

```text
This writes an AIT-owned copy/fact under .ait/. It does not modify the source
file, but it is not zero-touch.
```

`ait memory backfill --import` should be deprecated or kept only as an alias
with a mutation warning.

## Data Contracts

### LiveMemorySource

```json
{
  "schema_version": 1,
  "source_id": "live:claude:CLAUDE.md",
  "source_kind": "agent_memory",
  "agent": "claude",
  "scope": "repo",
  "path": "CLAUDE.md",
  "absolute_path": "/repo/CLAUDE.md",
  "exists": true,
  "allowed_by_policy": true,
  "policy_reasons": [],
  "size_bytes": 1234,
  "mtime": "2026-05-14T08:00:00Z",
  "sha256": "abc123...",
  "authority": "live_external",
  "source_of_truth": true,
  "writes": []
}
```

### FederatedRecallResult

```json
{
  "schema_version": 1,
  "query": "auth flow",
  "write_mode": "read_only",
  "sources": [
    {
      "source_id": "live:claude:CLAUDE.md",
      "sha256": "abc123...",
      "mtime": "2026-05-14T08:00:00Z",
      "used": true,
      "policy_status": "allowed"
    }
  ],
  "items": [
    {
      "kind": "live_source_excerpt",
      "source_id": "live:claude:CLAUDE.md",
      "rank": 0.91,
      "body": "redacted excerpt..."
    },
    {
      "kind": "ait_native_fact",
      "source_id": "memory-fact:...",
      "rank": 0.84,
      "body": "accepted fact..."
    }
  ],
  "writes": []
}
```

### Attempt Context Manifest

```json
{
  "schema_version": 1,
  "attempt_id": "repo:install:01...",
  "context_file_ref": ".ait/context/<attempt>.md",
  "live_sources": [
    {
      "source_id": "live:codex:AGENTS.md",
      "path": "AGENTS.md",
      "sha256": "def456...",
      "mtime": "2026-05-14T08:01:00Z",
      "bytes_used": 1800,
      "policy_status": "allowed"
    }
  ],
  "ait_native_sources": [
    "memory-fact:...",
    "attempt-memory:..."
  ],
  "redacted": false,
  "truncated": true
}
```

This manifest is AIT evidence. It does not make live source content AIT-owned
memory.

## Implementation Plan

### Phase 0 - Correct Semantics

- Stop describing `.ait/` writes as zero-interference.
- Update docs to distinguish:
  - zero-touch read
  - AIT-local mutation
  - source mutation
- Add deprecation warning to `ait memory backfill --import`, or rename it to
  `adopt` / `materialize`.
- Add a release note that existing auto-import behavior is being replaced by
  live source federation.

### Phase 1 - Live Source Discovery

Add module:

```text
src/ait/memory/live_sources.py
```

Responsibilities:

- enumerate repo-local source patterns
- optionally enumerate explicit global paths
- normalize source IDs
- reject path traversal and unsafe symlinks
- apply memory policy before content read
- calculate hash/mtime/size
- return structured `LiveMemorySource` records
- perform no writes

Add CLI:

```text
ait memory sources
```

Acceptance:

- Works before `ait init`.
- Does not create `.ait/`.
- Does not open SQLite.
- Does not mutate source files.

### Phase 2 - Federated Recall

Refactor recall into a live read-through pipeline:

```text
src/ait/memory/federated_recall.py
```

Input:

- query
- policy
- budget
- source selectors

Sources:

- live external memory sources
- AIT-native notes/facts/attempt summaries, when `.ait/` exists
- optional repo docs, if policy enables them

Default behavior:

- no writes
- no retrieval event
- no cache mutation

Optional behavior:

- `--record` writes retrieval evidence under `.ait/`

### Phase 3 - Run And Review Context

Replace current import-first behavior with live federation:

- remove auto `ensure_agent_memory_imported(...)` from `ait init`
- remove auto `ensure_agent_memory_imported(...)` from `ait run`
- build `AIT_CONTEXT_FILE` from live sources plus AIT-native memory at run time
- record attempt context manifest
- make review briefs use the same live federation pipeline

Important:

- The context file can be an AIT run artifact.
- Source files are still read live.
- Attempt evidence records what was read.

### Phase 4 - Cache / Index Without Staleness

If performance requires an index:

- index lives under `.ait/cache/`
- index is optional and rebuildable
- source hash/mtime is checked before use
- changed source triggers read-through or rebuild
- stale cache must never be returned as live memory
- `ait memory sources` and default `recall` stay no-write unless explicitly
  asked to update cache

### Phase 5 - Explicit Adoption

Add:

```bash
ait memory adopt <path>
ait memory adopt --source claude CLAUDE.md
```

Behavior:

- writes only `.ait/`
- source file remains unchanged
- record source path/hash/mtime
- mark fact/note as `adopted_external`
- never claim it is captured AIT provenance

## Testing And Acceptance

### Zero-Touch Source Discovery

Test:

1. Create temp Git repo with `CLAUDE.md`.
2. Do not run `ait init`.
3. Run `ait memory sources --format json`.
4. Assert:
   - `.ait/` does not exist
   - `git status --short` unchanged
   - source file hash unchanged
   - output includes `live:claude:CLAUDE.md`

### Live Recall Sees Updates Immediately

Test:

1. Write `CLAUDE.md` with `rule=v1`.
2. Run `ait memory recall "rule" --format json`.
3. Update `CLAUDE.md` to `rule=v2`.
4. Run recall again.
5. Assert second result contains `v2` and does not require import/backfill.

### Cross-Agent Federation

Test repo:

```text
CLAUDE.md
AGENTS.md
.cursor/rules
```

Run:

```bash
ait memory sources --format json
ait memory recall "project policy" --include-sources --format json
```

Assert all allowed source IDs can appear in the federated source manifest.

### No Global Discovery By Default

Test:

1. Create fake global `~/.claude/...` under temp HOME.
2. Create repo with no memory files.
3. Run `ait memory sources --format json`.
4. Assert global source is absent.
5. Run `ait memory sources --global --path <explicit>`.
6. Assert global source appears and is labeled `scope=global`.

### Policy And Redaction

Tests:

- excluded path is listed as skipped, content absent
- possible secret is redacted before excerpt/context output
- symlink outside repo is blocked unless explicit global path is provided
- max bytes and max files are enforced

### Run Context Manifest

Test:

1. Create `AGENTS.md` with a unique policy string.
2. Run a wrapped shell/agent command.
3. Assert attempt evidence contains context manifest with:
   - source ID
   - hash
   - mtime
   - bytes used
   - policy status
4. Modify `AGENTS.md`.
5. Assert old attempt manifest remains unchanged while new run sees new hash.

### Review Context Uses Same Pipeline

Test:

- adversarial review brief includes live source manifest
- stale or policy-blocked memory is advisory or excluded
- reviewer findings cite attempt and source evidence

### Backward Compatibility

Tests:

- existing `.ait/` memory notes remain searchable
- old imported notes are labeled as AIT-owned imported/adopted external memory
- `backfill --import` emits mutation warning or deprecation notice
- no migration deletes existing memory

## Manual Acceptance Checklist

Before shipping:

```bash
git diff --check
PYTHONPATH=src .venv/bin/pytest tests/test_memory.py tests/test_memory_security.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_live_memory_sources.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_federated_recall.py -q
/tmp/ait-docs-venv/bin/mkdocs build --strict --site-dir /tmp/ait-site-build
```

Manual smoke:

```bash
tmp="$(mktemp -d)"
cd "$tmp"
git init
printf "AIT_LIVE_MEMORY_RULE=v1\n" > CLAUDE.md
ait memory sources --format json
ait memory recall "AIT_LIVE_MEMORY_RULE" --format json
test ! -e .ait

printf "AIT_LIVE_MEMORY_RULE=v2\n" > CLAUDE.md
ait memory recall "AIT_LIVE_MEMORY_RULE" --format json
test ! -e .ait
```

Expected:

- `v1` appears in first recall.
- `v2` appears in second recall.
- `.ait/` is not created by read-only commands.

## Code Review Standards

### Critical Findings

Request changes if any patch:

- writes `.ait/` during `ait memory sources`
- writes `.ait/` during default `ait memory recall`
- auto-imports `CLAUDE.md`, `AGENTS.md`, or `.cursor/rules` during `ait init`
- auto-imports external memory during `ait run`
- mutates source memory files
- scans global memory without explicit path and flag
- uses a cache without hash/mtime validation
- treats external live memory as captured AIT provenance
- injects policy-blocked memory into run/review context
- calls network services for source discovery or recall
- lacks zero-write tests for new read-only commands

### High Findings

Request changes unless justified:

- unbounded recursive reads
- unsafe symlink traversal
- missing redaction before context output
- missing source manifest for injected memory
- stale cache returned as current memory
- CJK/Chinese search regressions
- global memory source lacks project match metadata
- `--import` / `adopt` copy does not clearly warn that it writes `.ait/`

### Required Reviewer Questions

Every memory PR reviewer should answer:

1. Which commands are read-only, and do tests prove they write nothing?
2. Which commands write `.ait/`, and is that explicit in CLI help and docs?
3. Are live sources read at execution time?
4. If a source changes between two recalls, does the second recall see it?
5. Can a stale cache affect run/review context?
6. Are policy-blocked and redacted sources excluded before context injection?
7. Does the attempt/review evidence say exactly which live sources were used?
8. Are external memory sources never represented as native AIT provenance?
9. Are existing `.ait/` users migrated additively?
10. Does the final UX support single-agent and cross-agent memory without an
    import ceremony?

## Documentation Requirements

README and website copy must use these terms consistently:

- "live repo memory view"
- "live external memory sources"
- "AIT-native memory"
- "federated recall"
- "adopt/materialize writes `.ait/`"

Avoid:

- "zero-interference import"
- "backfill" as the primary memory story
- "AIT imports agent memory automatically"
- "shared memory" without explaining live federation

## Final Positioning

The desired user-facing claim:

> AIT gives every agent the same live repo memory: current `CLAUDE.md`,
> `AGENTS.md`, Cursor rules, prior attempts, review findings, and accepted
> facts, assembled at run time without adopting or mutating another agent's
> memory by default.

The internal engineering claim:

> External memory is federated live. AIT-native memory is persisted. Adoption
> is explicit. Read-only commands are zero-touch.
