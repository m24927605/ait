# Slice 03: First Success CLI Output

狀態：Ready for implementation
目標：讓第一次使用者從 install/init/run/apply 能看到清楚、短、可執行的 human output。

## Problem

`ait run` 預設輸出 JSON；docs daily flow 直接示範 `ait run`；`ait attempt show` 只有
JSON；`ait status` 預設是 `claude-code` adapter readiness dashboard。這讓第一次成功
run 的體感像 debug dump，而不是產品成功路徑。

## Objective

建立 daily CLI human contract：

- TTY 預設 human text，`--json` 或 non-TTY automation 才用 JSON。
- `ait attempt show <selector> --format text` 顯示摘要與下一步。
- `ait status` 與 `ait doctor` 分工更清楚：status 偏 current AIT work，doctor 偏 adapter/install health。
- Docs 中的日常命令在 terminal 預設都是人可讀。

## Files To Change

- `src/ait/cli_parser.py`
- `src/ait/cli/run_helpers.py` or existing run CLI helper
- `src/ait/cli/attempt.py`
- `src/ait/cli/status_helpers.py`
- `tests/test_cli_run.py`
- `tests/test_cli_attempt_list.py`
- `tests/test_cli_adapters.py`
- README/site command docs only if behavior changes require alignment

## Files Not To Change

- Transcript redaction internals
- Release workflow
- SQLite schema
- Apply/recover state machine beyond output text

## Design

Human output should answer:

1. What happened?
2. Which attempt handle?
3. What changed?
4. Is it safe to apply?
5. What exact command should I run next?

Suggested `ait run --format text` success shape:

```text
AIT recorded a successful attempt.
Attempt: a1
Description: changed result.txt; +1/-0; status succeeded.
Changed: 1 files
Next: ait apply a1
```

Suggested `ait attempt show a1 --format text`:

```text
Attempt: a1
Status: succeeded
Description: changed result.txt; +1/-0; status succeeded.
Changed files:
- result.txt
Next:
- ait apply a1
- ait review attempt a1
```

JSON output must remain stable:

- Keep existing fields.
- Add fields only if useful, e.g. `attempt_handle`, `next_steps`.
- Do not hide `workspace_ref` from JSON.

## Tests

Required tests:

1. `test_run_default_tty_outputs_text`
   - Simulate TTY.
   - Assert output includes `Attempt: a1`, `Next: ait apply a1`.

2. `test_run_json_remains_machine_contract`
   - `--json` or `--format json` still parseable and includes existing keys.

3. `test_attempt_show_text_outputs_summary`
   - No raw workspace path or ownership token by default.

4. `test_attempt_show_json_includes_identity`
   - Existing JSON identity test remains.

5. `test_status_text_prioritizes_current_work`
   - In repo with latest attempt, status shows latest result before adapter internals or points to `doctor`.

6. `test_docs_daily_commands_do_not_default_to_json`
   - Optional docs smoke for command examples.

## Verification Commands

```bash
uv run pytest tests/test_cli_run.py tests/test_cli_attempt_list.py tests/test_cli_adapters.py -q
uv run pytest tests/test_agent_first_workflow.py -q
```

Manual smoke:

```bash
tmp=$(mktemp -d)
cd "$tmp"
git init
printf 'hello\n' > README.md
git add README.md
git commit -m initial
ait init --no-shell-install
ait run --adapter shell --intent smoke -- python3.14 -c "open('result.txt','w').write('ok\n')"
ait attempt show a1
ait apply a1
```

## Acceptance

- A first-time terminal user does not see giant JSON unless they request JSON.
- `ait attempt show` has human output.
- `--json` remains stable for automation.
- Docs daily commands align with actual default output.
- Adapter health remains available through `ait doctor` or explicit status flags.

## Review Checklist

- Confirm output text has one primary next step.
- Confirm no default human output prints full workspace path, ownership token, or raw trace path.
- Confirm `--json` tests parse exact fields needed by existing users.
- Confirm no broad refactor of runner/apply internals.

## Rollback

Changing CLI defaults may be user-visible. If risk is high, ship as:

1. Add `--format text` and warning first.
2. Change TTY default in a minor release.
3. Keep non-TTY JSON or require explicit migration note.

