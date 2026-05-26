# Slice 03: Selector Resolution For Handles

狀態：Ready after Slice 01
目標：讓 attempt-taking commands 可以解析 auto handle，例如 `a7`。

## Objective

Add a selector resolver that accepts canonical ids, id fragments, reserved selectors, and auto handles.

This slice only wires handle resolution into low-risk commands first. It does not add manual aliases.

## Files To Change

- `src/ait/idresolver.py`
- `src/ait/app.py`
- `src/ait/recovery.py`
- `src/ait/resume.py`
- `src/ait/landing.py`
- `tests/test_idresolver.py`
- focused CLI tests if needed

## Files Not To Change

- `src/ait/cli/query_helpers.py`
- `src/ait/cli/attempt.py` rendering
- `src/ait/db/schema.py`, except if Slice 01 was not merged
- manual alias commands

## Selector Contract

Add:

```python
resolve_attempt_selector(conn, given: str) -> str
```

Resolution precedence:

1. reserved selector handled by caller, for example `latest`
2. exact canonical id
3. exact auto handle from `attempt_identities.handle`
4. unique id fragment fallback through existing resolution logic

Why reserved selectors remain caller-owned:

- `latest` means different things in recovery, apply, review, and continue contexts.
- Some commands already have specialized latest semantics.

Behavior:

- `a7` resolves only if an identity row exists.
- Unknown handle returns `IdResolutionError("no attempt matches: a7")`.
- Ambiguous id fragment still returns the existing ambiguity error.
- Exact handle wins over id fragment.

## Commands To Wire In This Slice

Wire through app/service layer functions, not by adding CLI-specific hacks:

- `show_attempt`
- `create_commit_for_attempt`
- `verify_attempt`
- `discard_attempt`
- `promote_attempt`
- `land_attempt`
- `rebase_attempt`
- `recover_attempt` for non-`latest` selectors
- `build_resume_result`

Do not change `latest` behavior.

## Tests

Required tests:

1. `test_resolve_attempt_selector_accepts_handle`
   - Seed identity `a1`.
   - Assert resolver returns canonical id.

2. `test_resolve_attempt_selector_keeps_full_id`
   - Full id still resolves unchanged.

3. `test_resolve_attempt_selector_keeps_unique_fragment`
   - Existing fragment behavior still works.

4. `test_exact_handle_wins_over_fragment`
   - Create id containing string `a1`.
   - Identity `a1` points to another attempt.
   - Assert `a1` resolves to handle target.

5. `test_recover_accepts_handle`
   - Run `ait recover a1 --format json`.
   - Assert canonical attempt id in payload.

6. `test_apply_accepts_handle`
   - Run safe apply path with handle.

## Verification Commands

```bash
uv run pytest tests/test_idresolver.py tests/test_cli_resume.py tests/test_integration.py tests/test_landing.py -q
```

## Acceptance

- Users can pass `aN` to core attempt commands.
- `latest` semantics are unchanged.
- Full id and fragment selectors are unchanged.
- Ambiguous selectors fail closed.
- No manual alias behavior exists yet.
