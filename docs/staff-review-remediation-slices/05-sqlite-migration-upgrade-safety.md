# Slice 05: SQLite Migration Upgrade Safety

狀態：Ready for implementation
目標：讓 `.ait/state.sqlite3` schema migration 有真實舊版資料升級保護。

## Problem

AIT 的 SQLite schema 已經快速演進，且 `.ait/state.sqlite3` 是 attempt ledger、
review、memory、identity 的核心。現有 tests 覆蓋 fresh DB、idempotency、newer schema
reject 等基礎行為，但缺少從舊版 populated DB 升級後的資料保留與功能 smoke。

## Objective

建立 migration fixture matrix：

- 至少保留最近兩個 minor 版本的 populated DB fixture。
- 每個 fixture 升級後都要驗證 attempts、identities、reviews、memory、commits 仍可查。
- Migration failure path 必須 rollback 或 fail closed。
- Release gate 必須跑 migration fixtures。

## Files To Change

- `tests/test_db_migrations.py`
- `tests/fixtures/db_migrations/**`
- `src/ait/db/core.py` only if needed for safer migration execution
- `docs/release-checklist.md`

## Files Not To Change

- CLI UX defaults
- Transcript redaction
- Reviewer env policy
- Release publish behavior beyond adding migration gate commands

## Fixture Design

Create fixtures such as:

```text
tests/fixtures/db_migrations/
  v8_populated.sqlite3
  v9_populated.sqlite3
  v10_minimal.sqlite3
  README.md
```

Each fixture README must describe:

- source version
- how it was generated
- expected row counts
- sensitive data policy
- regeneration command

Fixtures must not contain real prompts, credentials, proprietary code, or user paths.

## Tests

Required tests:

1. `test_migrates_v8_populated_db_preserving_attempts`
   - Copy fixture to temp path.
   - Run `run_migrations`.
   - Assert schema version current, attempts visible, commits linked.

2. `test_migrates_v9_populated_db_preserving_identities`
   - Assert handles/descriptions are stable or backfilled deterministically.

3. `test_migrated_db_supports_core_queries`
   - Run attempt list/show query helpers against migrated DB.

4. `test_migration_failure_rolls_back`
   - Inject failing migration or monkeypatch execution.
   - Assert DB not partially advanced.

5. `test_newer_schema_rejected_without_mutation`
   - Existing newer schema test should assert no mutation.

## Implementation Notes

- Prefer `sqlite3.Connection.executescript()` over naive semicolon splitting if future migrations need triggers or strings with semicolons.
- Keep migrations additive when possible.
- Never drop user data without a backup/explicit migration note.
- If migration changes meaning of status fields, add compatibility read path.

## Verification Commands

```bash
uv run pytest tests/test_db_migrations.py -q
uv run pytest tests/test_query.py tests/test_cli_attempt_list.py tests/test_review_query.py -q
```

## Acceptance

- Old populated DB fixtures migrate to current schema.
- Core CLI/query paths work after migration.
- Migration failure does not leave `schema_version` falsely advanced.
- Release checklist includes migration fixture gate.
- Fixture generation process is documented and reproducible.

## Review Checklist

- Confirm fixtures contain no secrets or local user paths.
- Confirm tests copy fixtures before mutation.
- Confirm schema changes are versioned and backward compatible.
- Confirm rollback behavior is explicitly tested.

## Rollback

Never ship a rollback that deletes user `.ait/state.sqlite3`.
If a migration is flawed after release, ship a forward repair migration and document manual backup steps.

