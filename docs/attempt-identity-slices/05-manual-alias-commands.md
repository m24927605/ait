# Slice 05: Manual Alias Commands

狀態：Ready after Slices 01 and 03
目標：讓使用者可替重要 attempt 設定可記憶 alias，例如 `fix-ci`。

## Objective

Add explicit, low-risk manual alias CRUD:

```text
ait attempt alias set <attempt> <alias> [--force]
ait attempt alias unset <alias>
ait attempt alias list
```

Manual alias is optional. Auto handle remains the primary zero-configuration path.

## Files To Change

- `src/ait/db/schema.py`
- `src/ait/db/records.py`
- `src/ait/db/core_repositories.py`
- `src/ait/db/repositories.py`
- `src/ait/db/__init__.py`
- `src/ait/idresolver.py`
- `src/ait/cli_parser.py`
- `src/ait/cli/attempt.py`
- `tests/test_idresolver.py`
- new `tests/test_cli_attempt_alias.py`

## Files Not To Change

- `src/ait/runner.py`
- adapter resources
- `src/ait/review.py`
- `src/ait/integration.py`

## Data Contract

Add:

```sql
CREATE TABLE attempt_aliases (
  alias TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

Alias validation:

- regex: `^[a-z0-9][a-z0-9._-]{0,63}$`
- reject reserved words:
  - `latest`
  - `latest-reviewable`
  - `review`
  - `apply`
  - `recover`
  - `resume`
  - `continue`
- reject `a[0-9]+` because auto handles own that namespace.
- reject strings containing `:` to avoid canonical id confusion.

## Selector Contract

Update `resolve_attempt_selector()` precedence:

1. exact canonical id
2. exact auto handle
3. exact manual alias
4. unique id fragment

If alias and id fragment both match different attempts, alias wins because it is exact.

## CLI Behavior

Set:

```bash
ait attempt alias set a7 fix-ci
```

Output:

```text
Alias fix-ci -> a7
```

Unset:

```bash
ait attempt alias unset fix-ci
```

List:

```text
alias   handle attempt
fix-ci  a7     01K...
```

Rebind:

```bash
ait attempt alias set a8 fix-ci
```

Fails unless `--force`.

## Tests

Required tests:

1. `test_alias_set_and_resolve`
   - Set alias.
   - `resolve_attempt_selector(conn, "fix-ci")` returns canonical id.

2. `test_alias_rejects_reserved_names`
   - `latest`, `a1`, `recover`, `foo:bar` fail.

3. `test_alias_rebind_requires_force`
   - Existing alias cannot point to a new attempt without `--force`.

4. `test_alias_unset_removes_selector`
   - Unset then resolver fails.

5. `test_alias_list_shows_handle`
   - Human table includes alias and auto handle.

6. `test_alias_commands_accept_handle_or_full_id`
   - Set alias using `a1` and full id.

## Verification Commands

```bash
uv run pytest tests/test_cli_attempt_alias.py tests/test_idresolver.py -q
```

## Acceptance

- Manual aliases are explicit and optional.
- Reserved names are protected.
- Rebinding is deliberate.
- Alias resolution is deterministic and repo-local.
- Existing handle and full-id behavior remains unchanged.
