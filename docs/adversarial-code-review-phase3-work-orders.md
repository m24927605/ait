# AIT Review Orchestration Phase 3 Work Orders

Status: Proposed work orders

Phase 3 引入第一個真正 LLM reviewer，但必須先用 fake reviewer 把 parser、brief、persistence、gate 測穩。

## Phase 3A: Structured Output Parser

### Objective

實作 reviewer JSON parser，不執行 reviewer。

### Files To Change

- `src/ait/review.py` 或 `src/ait/review_parser.py`
- `tests/test_review_parser.py`

### Acceptance

- parses raw JSON。
- parses fenced JSON。
- malformed JSON fails closed。
- high/critical finding missing path/title/body fails closed。
- unknown severity handled by documented rule。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_parser.py -q
```

### Review Checklist

- parser 不接受任意 prose 當 pass。
- parser error creates failed review path in later slices。
- no LLM invocation。

## Phase 3B: Reviewer Brief Rendering

### Objective

產生 reviewer brief，清楚分離 trusted baseline 與 advisory evidence。

### Files To Change

- `src/ait/review_baseline.py`
- `src/ait/review.py`
- `tests/test_review_prompt.py`

### Acceptance

- brief contains target attempt id。
- brief contains changed files。
- brief contains baseline_ref。
- producer transcript labeled advisory/evidence。
- output schema included。
- policy-blocked facts absent from trusted section。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_prompt.py tests/test_review_baseline.py -q
```

### Review Checklist

- reviewer prompt 不把 producer self-assessment 當 fact。
- brief 不塞入全部 memory。
- brief size 有 budget 控制。

## Phase 3C: Fake Reviewer Invocation

### Objective

透過 fake reviewer command/adapter 回傳 deterministic JSON，驗證 invocation/persistence/gate。

### Files To Change

- `src/ait/review.py`
- `src/ait/cli/review.py`
- `tests/test_cli_review_adversarial.py`

### Acceptance

- fake no findings -> passed。
- fake low finding -> warning/passed with warning。
- fake high blocking finding -> blocked。
- fake malformed output -> failed。
- target attempt `verified_status` unchanged。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review_adversarial.py tests/test_review_gate.py -q
```

### Review Checklist

- fake reviewer path covers all gate outcomes。
- no real model required in CI。
- failure path preserves artifacts。

## Phase 3D: Real Single Reviewer Adapter

### Objective

支援 opt-in 真 reviewer invocation。

### Files To Change

- `src/ait/review.py`
- `src/ait/adapters.py` or review adapter helper
- `src/ait/cli_parser.py`
- `src/ait/cli/review.py`
- tests with fake command, not real network/model

### Acceptance

- `--mode adversarial` required。
- `--review-adapter` configurable。
- missing adapter gives actionable error。
- nonzero reviewer exit -> review failed。
- reviewer stdout/stderr captured in artifact。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review_adversarial.py tests/test_review_parser.py -q
```

### Review Checklist

- real reviewer is opt-in。
- AIT core does not add direct network dependency。
- reviewer cannot mutate target workspace。
- malformed output cannot pass。

## Phase 3E: Gate Hardening

### Objective

確保 LLM reviewer 結果和 apply gate 整合正確。

### Files To Change

- `src/ait/landing.py`
- `tests/test_review_gate.py`
- `tests/test_landing.py`

### Acceptance

- required adversarial review failed -> hold。
- required adversarial review blocked -> hold。
- passed -> existing apply checks continue。
- override -> continue with audit。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_gate.py tests/test_landing.py tests/test_cli_review_adversarial.py -q
```

### Phase 3 Exit Criteria

- First real LLM reviewer exists。
- It is opt-in。
- Parser fails closed。
- Fake reviewer tests cover CI。
- No default run slowdown。
