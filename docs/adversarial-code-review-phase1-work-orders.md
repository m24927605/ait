# AIT Review Orchestration Phase 1 Work Orders

Status: Proposed work orders

Phase 1 目標是建立 deterministic review skeleton。此階段不得新增 DB migration、LLM reviewer、baseline artifact 或 apply gate。

## Phase 1A: CLI Surface And Empty Handler

### Objective

新增 `ait review attempt <selector>` CLI surface，但 handler 可以先只解析參數並回傳未實作錯誤或 minimal stub。

### Files To Change

- `src/ait/cli_parser.py`
- `src/ait/cli/main.py` 或現有 dispatch 檔案
- `src/ait/cli/review.py`
- `tests/test_cli_review.py`

### Files Not To Change

- `src/ait/db/schema.py`
- `src/ait/landing.py`
- `src/ait/runner.py`
- `src/ait/verifier.py`

### Acceptance

- `ait review attempt latest-reviewable --format json` 被 parser 接受。
- `--format` 支援 `text`、`json`。
- `ait review latest` 不存在。
- 無效 format 由 argparse 擋下。
- 未實作狀態不可 crash。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review.py -q
```

### Review Checklist

- CLI 語意是否避免 ambiguous latest？
- 是否沒有新增 runtime side effect？
- 是否沒有碰 DB/apply/verifier？

## Phase 1B: Selector Resolution

### Objective

實作 `latest-reviewable` 和 explicit attempt selector。

### Files To Change

- `src/ait/review.py`
- `src/ait/cli/review.py`
- `tests/test_review.py`
- `tests/test_cli_review.py`

### Contract

`latest-reviewable` 必須跳過：

- failed
- running
- discarded
- promoted
- noop / no committed file changes

選擇：

- 最新的 succeeded、finished、unapplied、changed attempt。

### Acceptance

- 有多個 attempts 時選到正確 target。
- 找不到時 exit 1。
- 找不到時提示 `ait attempt list --verified-status succeeded`。
- explicit full attempt id 可解析。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review.py tests/test_cli_review.py -q
```

### Review Checklist

- selector 是否和 existing attempt ordering 一致？
- no-reviewable error 是否 actionable？
- 是否沒有建立 review DB record？

## Phase 1C: Changed Files And JSON Contract

### Objective

輸出 stable JSON contract，不做 risk scoring 或只輸出 low/0 placeholder。

### Files To Change

- `src/ait/review.py`
- `src/ait/cli/review.py`
- `tests/test_cli_review.py`

### JSON Required Fields

- `schema_version`
- `target_attempt_id`
- `selector`
- `verified_status`
- `reported_status`
- `changed_files`
- `risk_level`
- `risk_score`
- `risk_reasons`
- `review_required`
- `suggested_mode`

### Acceptance

- JSON 可 parse。
- changed files 排序穩定。
- text output 第一行顯示 target attempt。
- 不依賴 workspace 存在時可以從 attempt commits 取得 changed files。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review.py tests/test_review.py -q
```

### Review Checklist

- JSON field names 是否和 spec 一致？
- changed files 是否 deterministic？
- 是否沒有把 Python repr 當 JSON？

## Phase 1D: Risk Scoring V0

### Objective

新增 deterministic risk scoring v0。

### Files To Change

- `src/ait/review_policy.py`
- `src/ait/review.py`
- `tests/test_review_policy.py`
- `tests/test_cli_review.py`

### Contract

Risk levels:

- `low`: 0-19
- `medium`: 20-49
- `high`: 50-79
- `critical`: 80-100

Reason object:

```json
{
  "code": "missing_test_evidence",
  "message": "attempt changed files but no test evidence was observed",
  "paths": []
}
```

### Acceptance

- sensitive paths 增加風險。
- workflows/lockfiles/migrations 增加風險。
- missing test evidence 增加風險。
- score capped at 100。
- suggested mode follows risk level。
- Phase 1 `review_required` remains false。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_policy.py tests/test_cli_review.py -q
```

### Review Checklist

- reason codes 是否 stable？
- scoring 是否 deterministic？
- 是否沒有讀 network/LLM？

## Phase 1E: Regression Hardening

### Objective

確認 Phase 1 沒破壞既有 run/apply/verifier。

### Files To Change

- tests only, if needed

### Acceptance

- `ait run` existing CLI tests pass。
- `ait apply` existing tests pass。
- verifier tests pass。
- review command unused 時無 behavior change。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_landing.py tests/test_app_flow.py -q
```

### Phase 1 Exit Criteria

- First vertical slice 可用。
- 無 DB migration。
- 無 LLM。
- 無 apply gate。
- CLI/JSON/risk scan 有測試。
