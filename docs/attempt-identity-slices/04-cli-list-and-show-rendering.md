# Slice 04: CLI List And Show Rendering

狀態：Ready after Slices 01 and 02
目標：在 `ait attempt list` 與 `ait attempt show` 中顯示 handle 和 description。

## Objective

Improve human-facing attempt discovery without breaking machine output.

## Files To Change

- `src/ait/cli/query_helpers.py`
- `src/ait/cli/attempt.py`
- `src/ait/app.py` only if `show_attempt` payload needs additive identity metadata
- `tests/test_cli_attempt_list.py`
- new or existing `tests/test_cli_attempt_show.py`

## Files Not To Change

- `src/ait/idresolver.py`
- `src/ait/recovery.py`
- `src/ait/landing.py`
- `src/ait/cli/status_helpers.py`
- `src/ait/cli/continue_cmd.py`

## Human Output Contract

`ait attempt list` table:

```text
handle status     agent       exit files started          description
a7     succeeded  codex       0    2     2026-05-26...   stabilize recover latest integration metadata
```

Rules:

- Use `handle`, not raw short id, in the first column.
- Keep status, agent, exit, files, started.
- Replace or supplement intent column with description only if width remains readable.
- Clip long description to a fixed width in table output.
- Do not show `workspace_ref` or `ownership_token`.

`ait attempt show <selector>` text mode can be introduced if current output is JSON-only, but keep JSON as default if that is current contract. If adding text mode is too large, only add identity metadata to JSON in this slice and defer text rendering.

## Machine Output Contract

JSON/JSONL rows must keep existing fields and add:

```json
{
  "attempt_handle": "a7",
  "attempt_display_title": "...",
  "attempt_description": "..."
}
```

Do not rename `id`.
Do not remove `workspace_ref`.

## Tests

Required tests:

1. `test_attempt_list_table_shows_handle_and_description`
   - Assert `a1` appears.
   - Assert description appears.
   - Assert full attempt id does not appear.
   - Assert `workspace_ref` and `ownership_token` do not appear.

2. `test_attempt_list_jsonl_keeps_full_machine_readable_rows`
   - Existing assertions stay.
   - Assert `attempt_handle` and `attempt_description` added.

3. `test_attempt_list_backfills_missing_identity_readably`
   - Seed attempt with no identity if supported.
   - Assert table still renders and does not crash.

4. `test_attempt_show_json_includes_identity`
   - Assert identity metadata appears in show payload.

5. `test_attempt_list_description_clipping_does_not_break_columns`
   - Long title/description.
   - Assert one row per attempt and no leaked raw id.

## Verification Commands

```bash
uv run pytest tests/test_cli_attempt_list.py tests/test_query.py -q
```

## Acceptance

- `ait attempt list` is enough to recognize recent work.
- JSON/JSONL compatibility is preserved.
- Human output does not expose sensitive fields.
- No selector behavior changes in this slice.
