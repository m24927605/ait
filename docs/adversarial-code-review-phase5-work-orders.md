# AIT Review Orchestration Phase 5 Work Orders

Status: Proposed work orders

Phase 5 加入 profile-based multi-reviewer、consensus、finding lifecycle 與查詢/report 強化。此階段必須避免 review fatigue。

## Phase 5A: Profile Policy

### Objective

實作 required profiles by path/risk。

### Files To Change

- `src/ait/review_policy.py`
- `src/ait/policy.py`
- `tests/test_review_profiles.py`

### Acceptance

- auth path -> security + regression。
- workflow path -> security。
- migration path -> regression + release。
- low-risk generic path 不觸發 multi-reviewer。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_profiles.py -q
```

### Review Checklist

- profiles are policy-driven。
- default does not enable multi-reviewer for all。

## Phase 5B: Multi-Reviewer Orchestration With Fake Reviewers

### Objective

用 fake reviewers 驗證 multi-profile orchestration 和 consensus。

### Files To Change

- `src/ait/review.py`
- `tests/test_review_consensus.py`
- `tests/test_cli_review_adversarial.py`

### Acceptance

- all required profiles pass -> passed。
- any high blocking finding -> blocked。
- required profile missing -> hold/blocked。
- disagreement -> needs human review or documented blocked reason。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_consensus.py tests/test_review_profiles.py -q
```

### Review Checklist

- consensus fails closed。
- raw per-profile results preserved。
- no real LLM required in CI。

## Phase 5C: Finding Lifecycle Commands

### Objective

支援 finding lifecycle update，不刪除原始 finding。

### Files To Change

- `src/ait/cli_parser.py`
- `src/ait/cli/review.py`
- review repositories
- `tests/test_review_findings.py`

### Acceptance

- list findings by status/severity。
- update open -> acknowledged。
- update open -> false_positive requires reason。
- update open -> accepted_risk requires reason and audit。
- original title/body/evidence unchanged。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_findings.py -q
```

### Review Checklist

- accepted risk not treated as passed。
- lifecycle changes auditable。
- no target attempt mutation。

## Phase 5D: Review Query And Report Refinement

### Objective

讓 humans 可以追蹤 open findings、overrides、profile results。

### Files To Change

- `src/ait/query/*` or review-specific list command
- `src/ait/report/text.py`
- `src/ait/report/html.py` if applicable
- `tests/test_review_query.py`

### Acceptance

- list open high findings。
- list overridden reviews。
- report shows profile result。
- report shows disagreement。
- report shows accepted risk separately from passed。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_query.py tests/test_review_findings.py -q
```

### Phase 5 Exit Criteria

- Multi-reviewer only for configured high/critical risk。
- Consensus fail-closed。
- Finding lifecycle preserves audit history。
- Query/report supports human triage。
