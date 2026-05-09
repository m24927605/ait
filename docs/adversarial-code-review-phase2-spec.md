# AIT Review Orchestration Phase 2 Implementation Spec

Status: Proposed implementation spec

Phase 2 makes review a persisted, auditable first-class concept. It still does not introduce an LLM reviewer.

## Objective

Persist deterministic review results, baseline snapshots, findings, freshness metadata, and override audit records. Add review-aware apply gate behavior only when repo policy explicitly requires it.

## Non-Goals

Phase 2 不做：

- 不呼叫 LLM。
- 不建立 async queue。
- 不執行 reviewer adapter。
- 不做 multi-reviewer consensus。
- 不讓 `ait run` 預設等待 review。
- 不把 review failure 寫入 `verified_status`。

## Files To Change

預期變更：

- `src/ait/db/schema.py`
  - Add review tables/migrations.

- `src/ait/db/core_repositories.py` or new repository module
  - Add review CRUD APIs.

- `src/ait/db/records.py`
  - Add review/finding/override records.

- `src/ait/review.py`
  - Persist Phase 1 risk result.
  - Emit review artifact.
  - Compute freshness metadata.

- `src/ait/review_baseline.py`
  - Build trusted baseline snapshot artifact.

- `src/ait/review_policy.py`
  - Read review policy and gate decision helpers.

- `src/ait/policy.py`
  - Add review policy defaults.

- `src/ait/landing.py`
  - Check review gate only when policy requires it.

- `src/ait/cli/review.py`
  - Add commands to persist review result and override.

- `src/ait/run_report.py` and `src/ait/report/*`
  - Include review status summary.

- tests:
  - `tests/test_review_db.py`
  - `tests/test_review_baseline.py`
  - `tests/test_review_gate.py`
  - update CLI/report tests as needed

## Files Not To Change

Avoid modifying:

- LLM adapter resources
- `src/ait/runner.py` except if only needed for report refresh wiring and explicitly reviewed
- daemon code
- memory extraction logic outside policy-filtered read APIs

## Schema Contract

Add `attempt_reviews`:

- `id TEXT PRIMARY KEY`
- `target_attempt_id TEXT NOT NULL REFERENCES attempts(id)`
- `review_attempt_id TEXT NULL REFERENCES attempts(id)`
- `mode TEXT NOT NULL`
- `budget TEXT NOT NULL`
- `profiles_json TEXT NOT NULL`
- `reviewer_adapter TEXT NULL`
- `reviewer_agent_id TEXT NULL`
- `risk_level TEXT NOT NULL`
- `risk_score INTEGER NOT NULL`
- `risk_reasons_json TEXT NOT NULL`
- `status TEXT NOT NULL`
- `blocking INTEGER NOT NULL`
- `artifact_ref TEXT NULL`
- `baseline_ref TEXT NULL`
- `target_head_oid TEXT NULL`
- `base_ref_oid TEXT NULL`
- `policy_hash TEXT NOT NULL`
- `baseline_policy_hash TEXT NOT NULL`
- `reviewer_model TEXT NULL`
- `created_at TEXT NOT NULL`
- `completed_at TEXT NULL`
- `summary TEXT NOT NULL DEFAULT ''`

Add `attempt_review_findings`:

- `id TEXT PRIMARY KEY`
- `review_id TEXT NOT NULL REFERENCES attempt_reviews(id) ON DELETE CASCADE`
- `severity TEXT NOT NULL`
- `blocking INTEGER NOT NULL`
- `lifecycle_status TEXT NOT NULL`
- `path TEXT NOT NULL DEFAULT ''`
- `line INTEGER NULL`
- `hunk_ref TEXT NULL`
- `title TEXT NOT NULL`
- `body TEXT NOT NULL`
- `evidence_ref TEXT NULL`
- `suggested_test TEXT NULL`
- `confidence TEXT NOT NULL DEFAULT 'medium'`

Add `attempt_review_overrides`:

- `id TEXT PRIMARY KEY`
- `review_id TEXT NOT NULL REFERENCES attempt_reviews(id)`
- `reason TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `actor TEXT NULL`
- `audit_ref TEXT NULL`

Indexes:

- `idx_attempt_reviews_target`
- `idx_attempt_reviews_status`
- `idx_attempt_review_findings_review`
- `idx_attempt_review_findings_lifecycle`
- `idx_attempt_review_overrides_review`

## Review Artifact Contract

Persist artifacts under `.ait/reviews/` or another `.ait/` internal artifact path.

Review artifact v1 should include:

```json
{
  "schema_version": 1,
  "review_id": "review:ulid",
  "target_attempt_id": "repo:ulid",
  "mode": "light",
  "risk_level": "medium",
  "risk_score": 35,
  "risk_reasons": [],
  "baseline_ref": ".ait/review-baselines/review-id.json",
  "findings": []
}
```

Do not store unredacted secrets beyond existing AIT artifact policy.

## Baseline Snapshot Contract

Baseline snapshot v1 should include:

- `schema_version`
- `review_id`
- `target_attempt_id`
- `policy_hash`
- `baseline_policy_hash`
- `trusted_sources`
- `advisory_sources`
- `excluded_sources_summary`
- `selected_facts`
- `prior_failed_attempts`
- `prior_review_findings`
- `test_expectations`

Phase 2 can keep selected content small. It is more important to preserve source classification than to maximize recall.

## Review Policy Defaults

Default policy:

```json
{
  "review": {
    "default_mode": "never",
    "auto_apply_requires_review": false,
    "allow_override": true,
    "baseline": {
      "require_approved_facts": true,
      "allow_candidate_memory": false,
      "include_prior_failed_attempts": true,
      "include_prior_review_findings": true
    }
  }
}
```

Invalid values should fall back to safe defaults and emit warnings via effective policy reporting.

## Apply Gate Contract

Only enforce review gate when policy requires it.

Gate behavior:

- no policy requirement -> existing apply behavior
- missing required review -> hold
- queued/running required review -> hold
- failed required review -> hold
- blocked required review -> hold
- passed required review -> continue existing apply safety checks
- overridden review -> continue existing apply safety checks and report override

Hold message must mention review gate and recovery path.

## Required Tests

Migration tests:

- new tables exist after migration
- inserting review/finding/override works
- deleting review cascades findings if cascade is chosen
- old DBs migrate cleanly

Repository tests:

- create and fetch review
- list reviews for target attempt
- get latest review for target attempt
- create findings
- create override without mutating original review

Baseline tests:

- candidate memory excluded from trusted baseline
- policy-blocked facts excluded
- producer transcript marked advisory/evidence
- baseline artifact contains policy hash and source classification

Gate tests:

- apply unaffected when review policy disabled
- apply held when required review missing
- apply held when required review blocked
- apply proceeds when required review passed
- override permits proceed and is visible in result/report

Report tests:

- report includes review status
- report includes risk level
- report includes baseline ref
- report includes overridden status

Regression tests:

- verifier does not read review tables
- `verified_status` unchanged by blocked/failed review
- recover still works for held attempts

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest tests/test_review_db.py tests/test_review_baseline.py tests/test_review_gate.py -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest tests/test_db_migrations.py tests/test_landing.py tests/test_recover.py tests/test_verifier.py -q
```

Use existing test filenames if exact names differ.

## Implementation Review Checklist

- Review status is separate from attempt `verified_status`.
- Apply gate is policy-gated, not global.
- Override does not rewrite original review/finding.
- Baseline artifact distinguishes trusted and advisory sources.
- Schema has indexes for target/status lookups.
- Existing run/apply/recover behavior remains unchanged when review policy is disabled.
