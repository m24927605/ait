# AIT Attempt Identity And Description Design

狀態：Draft
日期：2026-05-26
範圍：attempt 自動別名、自動描述、selector 解析、CLI 呈現、測試與驗收。

## 背景

AIT 現在已經能用 full attempt id、唯一 id fragment、`latest` 來定位 attempt。這解決了機器識別，但沒有解決人的日常工作流：

- full attempt id 太長，不適合輸入或口頭討論。
- `latest` 只適合「最近一次」，不適合「昨天那個修 CI 的 attempt」。
- `ait attempt list` 目前顯示短 id、狀態、agent、intent title，但使用者仍可能忘記 attempt 實際做了什麼。
- `recover/apply/resume/continue/status/review` 等命令輸出中的 attempt 呈現不一致。

產品方向應該是：

```text
每個 attempt 都要能被快速指定，也要能被快速認出。
```

## 目標

1. **自動短別名**
   - 每個 attempt 建立或首次 backfill 時取得穩定 handle，例如 `a1`、`a2`。
   - handle 是 repo-local，保證同一個 `.ait/` store 內唯一。
   - full attempt id 仍是 canonical ID，handle 只是人類 selector。

2. **自動描述**
   - 每個 attempt 都有 deterministic summary，優先由 intent title、changed files、狀態、測試/exit 資訊產生。
   - 描述不能只靠 LLM 生成，因為 CLI 顯示必須可信、可重建、離線可用。
   - AI summary 可作為後續 enhancement，但必須標示來源與 freshness。

3. **低干擾 CLI**
   - 使用者可執行 `ait apply a7`、`ait recover fix-ci`、`ait attempt show a3`。
   - `ait attempt list` 預設顯示 handle、狀態、時間、agent、檔案數、短描述。
   - JSON/JSONL 保留 full canonical id、workspace_ref、machine fields。

4. **可逐步交付**
   - 每個 slice 都小到可以獨立 review、測試、merge。
   - 每個 slice 都有明確不做事項，避免把資料模型、CLI、AI summary、UI 全塞進一個 PR。

## 非目標

- 不移除 full attempt id。
- 不改變現有 `.ait/workspaces/attempt-*` 命名。
- 不讓 `a7` 跨 repo 唯一。
- 不讓自訂 alias 覆蓋 canonical id、`latest`、`latest-reviewable` 等保留 selector。
- 不在 v1 依賴雲端 LLM 來產生描述。
- 不用描述文字作為安全決策依據；apply/recover/review 仍必須看 canonical state。

## 使用者體驗

### Attempt List

```text
handle status     age   agent       files description
a8     active     4m    codex       3     add auto-continue for interrupted agent sessions
a7     succeeded  18m   codex       2     stabilize recover latest integration metadata
a6     succeeded  1h    human       7     release 1.2.0
```

### Attempt Show

```text
Attempt: a7
Status: succeeded
Canonical ID: repo:nonce:01K...
Intent: fix recover latest integration metadata
Description: recover latest now breaks same-second ties with attempt ULID.
Changed:
  src/ait/recovery.py
  tests/test_integration.py
Tests:
  uv run pytest -q passed
Next:
  ait apply a7
```

### Selectors

All attempt-taking commands should accept:

```text
latest
latest-reviewable
full attempt id
unique id fragment
auto handle, for example a7
manual alias, for example fix-ci
```

Resolution precedence:

1. reserved selectors such as `latest`
2. full canonical id
3. exact auto handle
4. exact manual alias
5. unique id fragment fallback

Ambiguity must fail closed with candidates.

## Data Model

Use additive tables instead of altering existing attempt semantics in the first implementation. This reduces migration risk and keeps canonical attempt rows focused on execution state.

### `attempt_identities`

```sql
CREATE TABLE attempt_identities (
  attempt_id TEXT PRIMARY KEY REFERENCES attempts(id) ON DELETE CASCADE,
  handle_index INTEGER NOT NULL UNIQUE,
  handle TEXT NOT NULL UNIQUE,
  display_title TEXT NOT NULL,
  deterministic_description TEXT NOT NULL,
  description_source TEXT NOT NULL,
  description_fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

Rules:

- `handle` is `a{handle_index}`.
- `handle_index` is monotonic per repo, assigned under `BEGIN IMMEDIATE`.
- Existing attempts are backfilled by `(started_at ASC, id ASC)`.
- `display_title` should be short and stable; prefer intent title clipped to CLI width.
- `deterministic_description` should be one sentence, derived from local metadata only.
- `description_fingerprint` changes when source metadata changes, so stale descriptions can be refreshed safely.

### `attempt_aliases`

```sql
CREATE TABLE attempt_aliases (
  alias TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

Rules:

- Alias is repo-local.
- Allowed pattern: lowercase letters, numbers, dot, underscore, dash; must start with a letter or number.
- Reserved names are rejected: `latest`, `latest-reviewable`, strings matching `a[0-9]+`, and existing command names.
- Rebinding requires `--force`.

## Description Generation

Description generation is deterministic and local in the first release.

Input priority:

1. intent title
2. attempt verified/reported status
3. changed file list from `evidence_files(kind='changed')`
4. touched file count and dominant directory
5. result exit code and observed test counts when present
6. integration artifact metadata when the attempt is an integration attempt

Output fields:

```json
{
  "handle": "a7",
  "title": "fix recover latest integration metadata",
  "description": "2 files changed in recovery and integration tests; latest selection tie-breaker stabilized.",
  "source": "deterministic:v1",
  "fingerprint": "sha256:..."
}
```

Quality rules:

- Never claim tests passed unless evidence exists.
- Never claim files changed unless indexed evidence or commit metadata exists.
- Never include workspace path in the default description.
- Clip display text without corrupting JSON fields.
- If metadata is missing, fall back to intent title plus status, not hallucinated content.

## Command Surface

Minimum command additions:

```text
ait attempt alias set <attempt> <alias> [--force]
ait attempt alias unset <alias>
ait attempt alias list
ait attempt describe <attempt> [--refresh] [--format json|text]
```

Formatting changes:

- `ait attempt list` table adds `handle` and `description`.
- `ait status`, `ait recover`, `ait resume`, `ait continue`, `ait apply`, and `ait review` include handle in human text.
- Machine output adds `attempt_handle` and `attempt_description` without removing existing fields.

Selector changes:

- `resolve_attempt_id()` should remain canonical-id focused.
- Add a wrapper resolver, for example `resolve_attempt_selector(conn, given)`, that knows reserved selectors, handles, aliases, and id fragments.
- Migrate command handlers incrementally to the wrapper resolver.

## Safety And Compatibility

- Existing full id selectors remain valid.
- Existing id-fragment selectors remain valid unless they collide with a new exact alias or handle; exact handle/alias wins.
- JSON consumers keep existing keys.
- New keys are additive.
- DB migrations must be idempotent and backfill existing attempts.
- All identity writes must happen in `.ait/state.sqlite3`; no source checkout mutation.
- Description refresh must be deterministic and safe to run repeatedly.

## Implementation Slices

Implement in this order:

1. [Slice 01: Identity Store And Backfill](attempt-identity-slices/01-identity-store-and-backfill.md)
2. [Slice 02: Deterministic Description Builder](attempt-identity-slices/02-deterministic-description-builder.md)
3. [Slice 03: Selector Resolution For Handles](attempt-identity-slices/03-selector-resolution-for-handles.md)
4. [Slice 04: CLI List And Show Rendering](attempt-identity-slices/04-cli-list-and-show-rendering.md)
5. [Slice 05: Manual Alias Commands](attempt-identity-slices/05-manual-alias-commands.md)
6. [Slice 06: Status Recover Continue Integration](attempt-identity-slices/06-status-recover-continue-integration.md)

Do not implement AI-generated summaries until these slices are merged and stable. AI summary should be a later optional slice with explicit source, cache, refresh, privacy, and offline fallback rules.

## Test Strategy

Test layers:

- DB migration and backfill tests in `tests/test_db_migrations.py` or a focused new test file.
- Repository helper tests for identity assignment, alias CRUD, and description refresh.
- Selector tests in `tests/test_idresolver.py`.
- CLI tests in `tests/test_cli_attempt_list.py`, `tests/test_cli_resume.py`, `tests/test_cli_continue.py`, `tests/test_integration.py`.
- Query formatting tests for table and JSONL compatibility.

Required regression cases:

- Existing full attempt id still resolves.
- Existing unique id fragment still resolves.
- `latest` still resolves through activity semantics.
- Two attempts created in the same second get stable handles and descriptions.
- Backfilled handles are stable across repeated migration runs.
- Alias collision fails closed.
- JSONL output keeps full `id` and `workspace_ref`.
- Default human output does not expose `ownership_token`.

## Acceptance

Product acceptance:

- A user can identify recent attempts from `ait attempt list` without copying full IDs.
- A user can run `ait recover aN`, `ait apply aN`, and `ait resume aN`.
- A user can understand what an attempt did from a one-line description.
- A user can set a custom alias for a memorable attempt.

Engineering acceptance:

- Every slice passes its own verification commands.
- Full `uv run pytest -q` passes before release.
- No slice changes unrelated behavior outside its declared files.
- No command removes existing JSON fields.
- Migrations are additive and idempotent.
- All ambiguity and collision cases fail closed with actionable messages.
