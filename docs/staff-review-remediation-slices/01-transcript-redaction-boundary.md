# Slice 01: Transcript Redaction Boundary

狀態：Ready for implementation
目標：確保 Claude/Codex upstream transcript 不會以 raw secret 形式進入 memory、report、
review context 或公開 artifact。

## Problem

Claude Code 與 Codex hook 目前直接把 upstream transcript byte-copy 到
`.ait/transcripts/`，並把該路徑當作 `raw_trace_ref`。下游 memory search、HTML report、
graph/report rendering 會讀取 trace text。這會讓 upstream transcript 裡的 secret、
prompt 或 private context 繞過 AIT 的 redaction pipeline。

## Evidence

- `src/ait/resources/claude-code/claude_code_hook.py` `persist_transcript()` writes `dest.write_bytes(src.read_bytes())`.
- `src/ait/resources/codex/codex_hook.py` 同樣 byte-copy upstream JSONL。
- `tests/test_claude_code_hook.py` 與 `tests/test_codex_hook.py` 目前 assert copied bytes 等於 upstream bytes。
- `src/ait/memory/search.py` 讀 `raw_trace_ref` 後直接把 `trace_text` 放進 document text。
- `src/ait/report/html.py` 會把 transcript 放進 HTML `<pre>`。

## Objective

新增 transcript retention boundary：

- Raw upstream transcript 可選擇保留，但不得成為 memory/report/review 預設資料源。
- Redacted transcript 必須成為 `raw_trace_ref` 或新的 safe trace ref。
- Memory search、graph、HTML report、review context 只能使用 redacted transcript。
- 若 transcript 被 policy exclude，body 不得進入 search/context，只可保留 excluded marker。

## Files To Change

- `src/ait/resources/claude-code/claude_code_hook.py`
- `src/ait/resources/codex/codex_hook.py`
- `src/ait/redaction.py`
- `src/ait/runner_transcript.py`
- `src/ait/memory/search.py`
- `src/ait/report/graph.py`
- `src/ait/report/html.py`
- hook/report/memory tests covering transcript leakage

## Files Not To Change

- Release workflow
- CLI default output behavior unrelated to transcript safety
- SQLite schema unless a safe ref requires an additive metadata field
- External provider SDK behavior

## Design

Preferred design:

1. Add a shared helper, e.g. `persist_agent_transcript_safely(repo_root, attempt_id, source_path, source_kind)`.
2. The helper writes:
   - `.ait/transcripts/redacted/<attempt-id>.jsonl` or `.txt`
   - optional `.ait/transcripts/raw/<attempt-id>.jsonl` only when policy explicitly allows raw retention
3. The helper applies:
   - terminal/control normalization when relevant
   - `redact_text()`
   - memory policy exclusion check
   - sidecar metadata such as `redacted: true`, `raw_retained: false`, `source_kind`
4. Hook `finish()` should pass the safe redacted ref as the attempt trace ref.
5. Reports and memory search must fail closed: if only raw ref exists from old attempts, redact on read before display/search.

## Data Contract

- Do not remove existing `raw_trace_ref` JSON fields.
- If a new field is added, it must be additive, e.g. `safe_trace_ref`, `raw_trace_retained`.
- Human output must not show raw transcript paths by default.
- Debug output may show storage refs but never secret body text.

## Tests

Required tests:

1. `test_claude_hook_persists_redacted_transcript`
   - Upstream contains API key/JWT/DB URL.
   - Persisted safe transcript does not contain original secret.

2. `test_codex_hook_persists_redacted_transcript`
   - Same as Claude path.

3. `test_memory_search_uses_redacted_trace`
   - Secret appears in upstream.
   - `ait memory search` or underlying search document never includes raw secret.

4. `test_graph_html_uses_redacted_trace`
   - HTML report contains redaction marker, not secret.

5. `test_old_raw_trace_is_redacted_on_read`
   - Simulate an older `.ait/transcripts/<attempt>.jsonl`.
   - Report/search redacts at read time.

6. `test_policy_excluded_trace_body_is_not_indexed`
   - Policy exclude marker prevents body from entering document text.

## Verification Commands

```bash
uv run pytest tests/test_redaction.py tests/test_claude_code_hook.py tests/test_codex_hook.py -q
uv run pytest tests/test_runner.py tests/test_memory_security.py tests/test_report*.py -q
```

## Acceptance

- No raw secret from upstream transcript appears in memory search, graph JSON, HTML report, review context, or default CLI text output.
- Existing attempts with old raw refs are read safely.
- Raw retention, if kept, is explicit and documented.
- Tests no longer assert byte-for-byte copy for default safe path.
- Failure to read or redact a transcript does not block attempt finalization, but it must fail closed for memory/report body use.

## Review Checklist

- Search for `read_bytes()` / `read_text()` on transcript paths and verify redaction boundary.
- Search for `raw_trace_ref` downstream and verify safe read helpers are used.
- Confirm no test fixture includes real credentials.
- Confirm default output does not print workspace or raw transcript internals.

## Rollback

Rollback must leave redacted transcript files in place. Do not delete user `.ait/transcripts`.
If new fields were added, stop reading them before removing writer logic in a later release.

