# Slice 02: Deterministic Description Builder

狀態：Ready after Slice 01
目標：產生可信、離線、可重建的 attempt title 與 description。

## Objective

Implement a deterministic description builder that updates `attempt_identities` from local AIT metadata.

This slice does not expose new CLI commands and does not add AI summaries.

## Files To Change

- `src/ait/attempt_identity.py` or equivalent focused new module
- `src/ait/db/core_repositories.py`
- `src/ait/db/repositories.py`
- `src/ait/db/__init__.py`
- `src/ait/app.py`
- `tests/test_attempt_identity.py`

## Files Not To Change

- `src/ait/idresolver.py`
- `src/ait/cli/*`
- `src/ait/transcript_llm.py`
- any adapter code
- any network or provider integration

## Description Rules

Inputs:

- intent title and description
- attempt statuses
- `result_exit_code`
- `evidence_files(kind='changed')`
- `attempt_commits.touched_files_json`, `insertions`, `deletions`
- integration result artifact when present
- observed test counts from `evidence_summaries`

Output:

```python
AttemptDescription(
    display_title: str,
    deterministic_description: str,
    description_source: str,
    description_fingerprint: str,
)
```

Rules:

- Prefer intent title for `display_title`.
- Use changed file facts for the description when available.
- Mention status only when it adds information, for example `failed`, `crashed`, `integration_created`.
- Mention tests only when observed test fields are non-zero or explicitly known.
- Do not mention workspace paths.
- Do not infer purpose from file names alone when intent title exists.
- Clip human strings for display in renderers, not in stored DB fields.

Example outputs:

```text
Intent title: fix recover latest integration metadata
Description: changed recovery.py and test_integration.py; status succeeded.
```

```text
Intent title: release 1.2.0
Description: 7 files changed across packaging and docs; status succeeded.
```

Fallback:

```text
Attempt 01K... has no indexed changed files yet; status pending.
```

## Refresh Semantics

Add:

```python
refresh_attempt_identity(conn, attempt_id: str) -> AttemptIdentityRecord
refresh_stale_attempt_identities(conn) -> int
```

`description_fingerprint` should include only local source facts used by the builder. If the fingerprint is unchanged, refresh should avoid updating `updated_at`.

Call refresh after:

- attempt commit creation
- attempt verification
- attempt discard/promote
- integration attempt creation

Do not refresh during read-only list commands in this slice.

## Tests

Required tests:

1. `test_description_prefers_intent_title`
   - Intent title appears as display title.

2. `test_description_uses_changed_files`
   - Seed changed evidence files.
   - Assert description mentions file count or representative paths.

3. `test_description_uses_status_without_overclaiming_tests`
   - Succeeded attempt with no observed tests does not say tests passed.

4. `test_description_refresh_is_idempotent`
   - Run refresh twice without source changes.
   - Assert fingerprint unchanged and no unnecessary update.

5. `test_description_changes_after_commit_metadata_changes`
   - Add evidence/commit metadata.
   - Refresh.
   - Assert fingerprint and description change.

6. `test_integration_attempt_description_mentions_classification`
   - Seed integration artifact.
   - Assert description includes classification or integration status.

## Verification Commands

```bash
uv run pytest tests/test_attempt_identity.py tests/test_integration.py -q
```

## Acceptance

- Every identity row has a useful deterministic description.
- Description refresh is local, deterministic, and idempotent.
- No LLM/network code is introduced.
- No description overclaims test results or safety.
- Existing CLI output remains unchanged until later slices.
