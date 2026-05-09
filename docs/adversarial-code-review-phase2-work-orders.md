# AIT Review Orchestration Phase 2 Work Orders

Status: Proposed work orders

Phase 2 讓 review 成為可保存、可審計、可 gate 的一等資料。此階段仍不得呼叫 LLM。

## Phase 2A: Review Schema And Repositories

### Objective

新增 review/finding/override tables 與 repository APIs。

### Files To Change

- `src/ait/db/schema.py`
- `src/ait/db/records.py`
- `src/ait/db/core_repositories.py` 或新 review repository module
- `src/ait/db/__init__.py`
- `tests/test_review_db.py`
- `tests/test_db_migrations.py`

### Files Not To Change

- `src/ait/landing.py`
- `src/ait/review_baseline.py`
- LLM/adapter files

### Acceptance

- migrations create `attempt_reviews`。
- migrations create `attempt_review_findings`。
- migrations create `attempt_review_overrides`。
- repository APIs can create/list/get reviews。
- override insertion does not modify original review。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_db.py tests/test_db_migrations.py -q
```

### Review Checklist

- schema fields match Phase 2 spec。
- indexes exist for target/status lookups。
- foreign keys are correct。
- no apply behavior changed。

## Phase 2B: Persist Deterministic Review Result

### Objective

Phase 1 risk scan can be persisted as a review record and artifact.

### Files To Change

- `src/ait/review.py`
- `src/ait/cli/review.py`
- `tests/test_cli_review.py`
- `tests/test_review_db.py`

### Acceptance

- `ait review attempt latest-reviewable` creates an `attempt_reviews` row。
- artifact_ref points to `.ait/` artifact。
- repeated command either creates new review or follows documented dedupe behavior。
- JSON output includes `review_id` when persisted。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review.py tests/test_review_db.py -q
```

### Review Checklist

- artifact is local。
- no LLM invocation。
- no baseline trusted/advisory confusion yet。

## Phase 2C: Baseline Snapshot V1

### Objective

建立 policy-filtered baseline snapshot artifact。

### Files To Change

- `src/ait/review_baseline.py`
- `src/ait/review.py`
- `tests/test_review_baseline.py`
- possibly `src/ait/memory_policy.py` read-only helper usage only

### Files Not To Change

- memory candidate generation logic
- memory acceptance logic

### Acceptance

- baseline_ref saved on review。
- baseline artifact distinguishes trusted/advisory/excluded。
- candidate memory excluded from trusted baseline。
- policy-blocked facts excluded。
- producer transcript can be referenced as advisory/evidence only。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_baseline.py tests/test_memory_security.py -q
```

### Review Checklist

- no unapproved facts in trusted baseline。
- baseline has policy hash。
- baseline artifact is reproducible enough for audit。

## Phase 2D: Review Policy And Apply Gate

### Objective

`ait apply` reads review gate policy, but only enforces it when policy explicitly requires review.

### Files To Change

- `src/ait/policy.py`
- `src/ait/review_policy.py`
- `src/ait/landing.py`
- `tests/test_review_gate.py`
- `tests/test_landing.py`

### Acceptance

- review policy disabled by default。
- apply behavior unchanged when disabled。
- required review missing -> hold。
- required review blocked/failed -> hold。
- required review passed -> continue existing apply checks。
- overridden -> continue with audit marker。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_review_gate.py tests/test_landing.py -q
```

### Review Checklist

- no global apply blocking。
- hold message is actionable。
- existing dirty/safe-patch logic still wins where relevant。

## Phase 2E: Report And Status Integration

### Objective

Expose review summary in reports/status surfaces.

### Files To Change

- `src/ait/run_report.py`
- `src/ait/report/text.py`
- `src/ait/report/html.py` if applicable
- tests for reports

### Acceptance

- report shows latest review status。
- report shows risk level。
- report shows baseline_ref。
- report shows overridden state。

### Tests

```bash
PYTHONPATH=src uv run pytest tests/test_runner.py tests/test_landing.py tests/test_local_artifacts.py -q
```

### Phase 2 Exit Criteria

- Review persistence exists。
- Baseline snapshot exists。
- Apply gate is policy-gated。
- Override audit trail exists。
- Still no LLM reviewer。
