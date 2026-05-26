# Slice 06: Status Recover Continue Integration

狀態：Ready after Slices 01 through 04
目標：讓 status/recover/resume/continue/apply/review 的人類輸出一致顯示 handle 和描述。

## Objective

Complete the UX loop so users see the same attempt identity everywhere:

- `ait status`
- `ait recover`
- `ait resume`
- `ait continue`
- `ait apply`
- `ait review`
- shell integration reminder text

This slice is display and additive JSON metadata only. It must not change apply/recover safety behavior.

## Files To Change

- `src/ait/cli/status_helpers.py`
- `src/ait/cli/recover.py`
- `src/ait/cli/resume.py`
- `src/ait/cli/continue_cmd.py`
- `src/ait/cli/apply.py`
- `src/ait/cli/review.py`
- `src/ait/resume.py`
- `src/ait/recovery.py`
- `src/ait/landing.py`
- `tests/test_cli_resume.py`
- `tests/test_cli_continue.py`
- `tests/test_integration.py`
- `tests/test_landing.py`
- review CLI tests as needed

## Files Not To Change

- DB schema
- selector resolution
- integration merge logic
- cleanup policy
- agent adapters

## Output Contract

Human output should prefer:

```text
Attempt: a7
Description: stabilize recover latest integration metadata
```

Debug output may include:

```text
Canonical ID: repo:nonce:01K...
Workspace: /repo/.ait/workspaces/attempt-...
```

JSON output should add fields without removing existing ones:

```json
{
  "attempt_id": "repo:nonce:01K...",
  "attempt_handle": "a7",
  "attempt_description": "...",
  "workspace_ref": "..."
}
```

Rules:

- Default human output should not require users to copy full ids.
- Debug output can show canonical id and workspace.
- JSON output remains machine complete.
- Recovery decision reports can include handle/description in `debug` or additive top-level fields, but must not remove current fields.

## Tests

Required tests:

1. `test_status_shows_attempt_handle`
   - Latest attempt appears as `a1`.

2. `test_recover_text_shows_handle_and_debug_keeps_full_id`
   - Default text shows handle.
   - `--debug` shows canonical id/workspace.

3. `test_recover_json_includes_identity_metadata`
   - Existing JSON fields remain.
   - New handle and description fields exist.

4. `test_resume_text_shows_handle`
   - `ait resume a1` output references `a1`.

5. `test_continue_plan_includes_identity_metadata`
   - JSON plan includes handle/description.

6. `test_apply_text_shows_handle`
   - Apply result shows handle.

7. `test_review_target_text_shows_handle`
   - Review target output includes handle where attempt id is currently printed.

8. `test_shell_continue_reminder_uses_handle`
   - Reminder says interrupted attempt `aN` is recoverable.

## Verification Commands

```bash
uv run pytest tests/test_cli_resume.py tests/test_cli_continue.py tests/test_integration.py tests/test_landing.py tests/test_cli_review.py -q
```

## Acceptance

- A user can recognize and refer to the same attempt across list/status/recover/resume/continue/apply/review.
- Existing JSON consumers do not break.
- Debug still exposes canonical details for support.
- No apply/recover behavior changes beyond selector and display.
- No workspace path appears in default text unless the command's existing contract already requires it, such as `ait resume`.
