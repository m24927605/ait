# AIT Review Orchestration Phase 4 Work Orders

Status: Proposed work orders

Phase 4 把 LLM reviewer 放進 risk-based orchestration。這階段最容易影響 UX，必須拆小做。

## Phase 4A: Run Flag And Synchronous Required Gate

### Objective

新增 `ait run --review risk-based`，但先用同步 required gate，不急著做完整 async queue。

### Files To Change

- `src/ait/cli_parser.py`
- `src/ait/cli/run.py`
- `src/ait/review_policy.py`
- `tests/test_cli_run_review.py`

### Acceptance

- `--review never` keeps existing behavior。
- `--review risk-based` runs deterministic scan after attempt。
- low risk does not invoke fake LLM。
- high risk with `--apply auto` requires review passed or holds。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run_review.py tests/test_cli_run.py -q
```

### Review Checklist

- run without `--review` unchanged。
- no universal LLM wait。
- hold reason mentions review gate。

## Phase 4B: Review Queue V0

### Objective

新增 review queue/status model。可以是 simple local queue，不必一開始 daemon-heavy。

### Files To Change

- `src/ait/review_queue.py`
- `src/ait/cli/review.py`
- DB repository additions if needed
- `tests/test_review_queue.py`
- `tests/test_review_status.py`

### Acceptance

- queue creates job。
- duplicate required jobs dedupe。
- status transitions queued/running/passed/failed。
- crashed/stale job does not stay running forever。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_queue.py tests/test_review_status.py -q
```

### Review Checklist

- queue failure does not mutate target attempt。
- status is actionable。
- dedupe key includes target/mode/policy hash。

## Phase 4C: Async Run Integration

### Objective

`ait run --review risk-based --apply never` can queue review without blocking. `--apply auto` gates correctly.

### Files To Change

- `src/ait/cli/run.py`
- `src/ait/review_queue.py`
- `src/ait/run_report.py`
- `tests/test_cli_run_review.py`

### Acceptance

- apply never: run completes, review queued if needed。
- apply auto: required review queued/running -> hold。
- passed review -> apply may proceed through existing checks。
- blocked review -> hold。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run_review.py tests/test_landing.py -q
```

### Review Checklist

- async improves run latency for non-auto apply。
- auto apply fail-closed。
- report explains queued/running state。

## Phase 4D: Policy And Report Hardening

### Objective

把 risk-based orchestration 和 repo policy/report/status 打磨到可用。

### Files To Change

- `src/ait/policy.py`
- `src/ait/review_policy.py`
- `src/ait/report/text.py`
- `src/ait/report/html.py` if applicable
- tests for policy/report

### Acceptance

- missing policy defaults to review disabled。
- invalid policy falls back safely。
- sensitive paths trigger required review if configured。
- report shows next step。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_config.py tests/test_review_status.py tests/test_runner.py -q
```

### Phase 4 Exit Criteria

- Risk-based review usable from `ait run`。
- Low-risk runs are not slowed by LLM。
- Auto apply respects required review gate。
- Queue/status/report are coherent。
