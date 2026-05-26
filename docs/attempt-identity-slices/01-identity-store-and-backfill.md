# Slice 01: Identity Store And Backfill

狀態：Ready for implementation
目標：建立 attempt handle 的持久資料模型，並為既有 attempts backfill 穩定 `aN` handle。

## Objective

新增 repo-local attempt identity store：

- 每個 attempt 有唯一、穩定、自動產生的 handle，例如 `a1`。
- 新 attempt 建立時自動分配下一個 handle。
- 既有 DB migration 後可 deterministic backfill。
- 不改任何 CLI selector 行為。

## Files To Change

- `src/ait/db/schema.py`
- `src/ait/db/records.py`
- `src/ait/db/core_repositories.py`
- `src/ait/db/repositories.py`
- `src/ait/db/__init__.py`
- `src/ait/app.py`
- `tests/test_db_migrations.py` or new `tests/test_attempt_identity.py`

## Files Not To Change

- `src/ait/idresolver.py`
- `src/ait/cli/*`
- `src/ait/query/*`
- `src/ait/recovery.py`
- site docs and README files

## Data Contract

Add table:

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

Initial values:

- `handle_index`: monotonic integer starting at 1.
- `handle`: `a{handle_index}`.
- `display_title`: intent title if available, otherwise short attempt id.
- `deterministic_description`: same as display title for this slice.
- `description_source`: `identity-bootstrap:v1`.
- `description_fingerprint`: stable hash of attempt id plus initial title source.

Repository APIs:

```python
ensure_attempt_identity(conn, attempt_id: str) -> AttemptIdentityRecord
get_attempt_identity(conn, attempt_id: str) -> AttemptIdentityRecord | None
get_attempt_identity_by_handle(conn, handle: str) -> AttemptIdentityRecord | None
list_attempt_identities(conn, attempt_ids: tuple[str, ...]) -> dict[str, AttemptIdentityRecord]
backfill_attempt_identities(conn) -> int
```

## Implementation Notes

- Assign handles inside the same transaction as attempt insertion when possible.
- If `create_attempt()` cannot keep the transaction cleanly, call `ensure_attempt_identity()` immediately after insert while holding a write transaction.
- Use `BEGIN IMMEDIATE` for backfill and next handle allocation to avoid duplicate handles under concurrent attempt creation.
- Backfill order must be deterministic: `started_at ASC, id ASC`.
- Re-running backfill must be a no-op for existing rows.

## Tests

Required tests:

1. `test_create_attempt_assigns_handle`
   - Create repo, intent, attempt.
   - Assert identity row exists with `handle='a1'`.

2. `test_multiple_attempts_get_monotonic_handles`
   - Create three attempts.
   - Assert handles are `a1`, `a2`, `a3`.

3. `test_backfill_existing_attempts_is_stable`
   - Seed attempts without identities.
   - Run migration/backfill twice.
   - Assert same handles after both runs.

4. `test_concurrent_identity_assignment_has_no_duplicate_handles`
   - Use two threads or processes creating attempts.
   - Assert unique handles and no orphan workspace.

5. `test_identity_deletes_with_attempt`
   - Delete an attempt row in a controlled DB test.
   - Assert identity row cascades.

## Verification Commands

```bash
uv run pytest tests/test_db_migrations.py tests/test_attempt_identity.py -q
uv run pytest tests/test_app_flow.py tests/test_concurrency.py -q
```

## Acceptance

- New attempts always get identity rows.
- Existing attempts get stable backfilled handles.
- No CLI behavior changes yet.
- Full ID and id-fragment resolution remain untouched.
- No source checkout files are modified.

## Rollback

Because this slice is additive, rollback is:

- stop reading the new table
- leave table data in place
- do not drop the table in user repos
