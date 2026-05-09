# AIT Review Orchestration Phase 6 Implementation Spec

Status: Proposed implementation spec

Phase 6 is productization hardening for the Phase 1-5 review orchestration work. The goal is to move the current V0 implementation toward a reliable, maintainable, and auditable product surface before adding broader integrations.

Phase 6 should not expand the feature surface blindly. It should first stabilize the existing implementation, then harden queue execution, freshness, adapter configuration, apply gates, query integration, and evaluation.

## Objective

Make AIT Risk-Based Pre-Apply Review Orchestration production-ready enough for regular dogfooding:

- review behavior remains disabled by default unless CLI or repo policy opts in
- queued reviews can be processed by a local worker/daemon path
- stale reviews cannot silently satisfy apply gates
- reviewer adapter execution is configurable and constrained
- apply gate failures are explicit, actionable, and fail closed
- `ait query` can inspect review/finding state
- benchmark cases can measure quality, latency, and review fatigue

## Current V0 Boundaries

Phase 1-5 introduced the core foundation:

- `ait review attempt <selector>`
- deterministic risk scan
- review tables and repository APIs
- baseline snapshot artifacts
- structured reviewer output parser
- fake reviewer
- command-based reviewer adapter
- review queue V0 using `attempt_reviews`
- `ait run --review`
- profile policy
- fake multi-reviewer consensus
- finding lifecycle commands
- review status/finding list/report refinement

Phase 6 assumes those exist, but treats them as V0. The implementation should be reviewed and hardened before deeper automation is added.

## Non-Goals

Phase 6 does not do:

- GitHub PR inline review integration
- automatic fixing of review findings
- cloud service orchestration
- all-runs default adversarial review
- direct network access in AIT core
- treating AI reviewer output as an absolute correctness oracle
- replacing `verified_status` with review status
- letting stale, malformed, or missing review evidence pass an apply gate

## Files To Change

Expected areas:

- `src/ait/review.py`
  - cleanup/refactor review orchestration boundaries
  - freshness metadata helpers
  - profile/multi-review artifact consistency

- `src/ait/review_queue.py`
  - queue worker execution
  - stale/retry handling
  - idempotent job processing

- `src/ait/review_policy.py`
  - freshness and gate policy helpers
  - adapter/profile policy validation
  - required review decisions

- `src/ait/review_adapter.py`
  - adapter command config
  - timeout/cwd/env controls
  - output capture rules

- `src/ait/landing.py`
  - stronger apply gate checks
  - stale/missing/malformed review failure paths

- `src/ait/policy.py`
  - effective review adapter policy
  - invalid policy fallback warnings

- `src/ait/cli/review.py`
  - queue worker/status commands
  - clearer review diagnostics

- `src/ait/query/*`
  - review/finding query fields

- `src/ait/report/*`
  - freshness/gate/profile/lifecycle reporting

- tests:
  - `tests/test_review_hardening.py`
  - `tests/test_review_queue_worker.py`
  - `tests/test_review_freshness.py`
  - `tests/test_review_adapter_config.py`
  - `tests/test_review_gate_hardening.py`
  - `tests/test_review_query_dsl.py`
  - `tests/test_review_benchmark.py`

## Files Not To Change

Avoid modifying:

- verifier semantics
- low-level Git workspace semantics unless needed to read immutable refs
- memory candidate acceptance logic
- unrelated adapter setup flows
- daemon lifecycle outside the minimal worker integration needed for review queue processing

## Stabilization Contract

Phase 6A must audit the current implementation before adding behavior:

- remove obvious duplicated logic
- ensure helper boundaries are coherent
- confirm DB migrations are safe for old databases
- confirm `ait run`, `ait apply`, `ait recover`, and `ait status` defaults are unchanged when review is not enabled
- confirm `verified_status` is never changed by review failure
- decide whether generated lockfile changes such as `uv.lock` are intentional

No large refactor should happen without tests preserving current behavior.

## Queue Worker Contract

Review queue V0 uses `attempt_reviews` rows with `status` values such as `queued`, `running`, `passed`, `blocked`, and `failed`.

Phase 6B should add a worker path that can process queued jobs:

```bash
ait review worker --once
ait review worker --max-jobs 5
```

Worker behavior:

- select queued jobs in FIFO order
- transition `queued -> running`
- run the configured reviewer adapter or fake adapter
- persist raw stdout/stderr and artifacts
- transition to `passed`, `warning`, `blocked`, or `failed`
- never mutate the target attempt status
- stale `running` jobs become `failed` or recoverable, not permanently running
- duplicate jobs are deduped by target/mode/profile/policy/freshness key

## Review Freshness Contract

A review is stale if any of these changed since review creation:

- target attempt head oid
- base ref oid
- repo review policy hash
- baseline policy hash
- review mode
- review budget
- required profiles
- reviewer adapter or model identity
- relevant approved facts or durable decisions
- sensitive path/profile policy
- target findings were marked fixed/superseded without a new review

Freshness metadata should be stored or derivable from:

- `target_head_oid`
- `base_ref_oid`
- `policy_hash`
- `baseline_policy_hash`
- `baseline_ref`
- `mode`
- `budget`
- `profiles`
- `reviewer_adapter`
- `reviewer_model`

Apply gate must not accept stale review as passing. It should hold with an actionable reason:

```text
review gate: required review is stale; run ait review attempt <attempt-id>
```

## Adapter Configuration Contract

AIT core should not add direct network access. It may invoke configured local commands.

Repo policy can define:

```json
{
  "review": {
    "adapters": {
      "default": {
        "command": "codex review --json",
        "timeout_seconds": 300,
        "env_allowlist": ["PATH", "HOME"],
        "cwd": ".ait/reviewer-runs"
      },
      "security": {
        "command": "codex review --profile security --json",
        "timeout_seconds": 600
      }
    }
  }
}
```

Adapter rules:

- command receives reviewer brief via stdin or a temp artifact
- command runs outside the target attempt workspace
- timeout is enforced
- stdout/stderr are captured
- nonzero exit is review `failed`
- malformed output is review `failed`
- missing adapter for required review is fail-closed
- secrets and raw transcript exposure follow memory/baseline policy

## Stronger Apply Gate Contract

Auto apply can proceed only when:

- attempt `verified_status == succeeded`
- attempt has committed changes
- workspace/ref is readable
- no conflict markers are found
- required review exists
- required review is fresh
- required review is passed or explicitly overridden
- no open high/critical blocking finding remains
- all required profiles are present
- structured findings contain auditable path/title/body/evidence where required
- baseline did not include candidate/stale/policy-blocked facts as trusted

Auto apply must hold when:

- review is missing
- review is queued/running
- review failed
- review blocked
- review is stale
- required profile is missing
- reviewer output could not be parsed
- adapter failed or timed out
- baseline policy violation is detected
- test evidence is missing on sensitive paths and policy requires evidence

Manual apply may allow explicit override only when policy permits it, and the override must be auditable.

## Query DSL Contract

Phase 6F should expose review/finding state through `ait query`, not only through review-specific commands.

Target fields:

- `review.id`
- `review.status`
- `review.mode`
- `review.risk_level`
- `review.risk_score`
- `review.blocking`
- `review.override`
- `review.profile`
- `review.fresh`
- `finding.id`
- `finding.severity`
- `finding.blocking`
- `finding.lifecycle_status`
- `finding.path`

Example queries:

```bash
ait query 'review.status="blocked"'
ait query 'review.override=true'
ait query 'finding.severity="high" and finding.lifecycle_status="open"'
ait query 'review.profile="security"'
ait query 'review.fresh=false'
```

## Evaluation Benchmark Contract

Phase 6G should add a local benchmark suite that does not require real external services in CI.

Benchmark cases should include:

- vulnerable diff
- expected finding
- malicious prompt/comment injection
- misleading memory
- stale approved fact
- missing test evidence
- sensitive path change
- benign change for false-positive measurement

Metrics:

- finding recall
- false positive rate
- evidence completeness
- malformed output fail-closed rate
- memory contamination rate
- blocked memory source recall count, ideal value `0`
- trusted baseline contamination rate, ideal value `0`
- review latency
- user waiting time
- review fatigue, measured by non-actionable warning count
- Staff human reviewer agreement

## Required Tests

Stabilization tests:

- full review-related test suite passes
- `ait run` default unchanged without review
- `ait apply` default unchanged when review policy disabled
- `ait recover` unaffected by review tables
- `verified_status` unchanged by blocked/failed review

Queue worker tests:

- queued job processes to passed
- high finding processes to blocked
- malformed output processes to failed
- adapter timeout processes to failed
- stale running job is recovered
- duplicate queued jobs dedupe

Freshness tests:

- target head change makes review stale
- base ref movement makes review stale
- policy hash change makes review stale
- baseline hash change makes review stale
- required profile change makes review stale
- stale review blocks auto apply

Adapter config tests:

- command adapter receives brief
- timeout is enforced
- nonzero exit fails review
- stdout/stderr artifact is preserved
- adapter cwd is outside target workspace
- env allowlist is respected where supported

Gate hardening tests:

- missing review holds
- queued/running review holds
- stale review holds
- missing required profile holds
- malformed output holds
- override is auditable and not treated as passed

Query tests:

- query blocked reviews
- query overridden reviews
- query open high findings
- query profile results
- query stale reviews

Benchmark tests:

- benchmark runner loads cases
- expected finding is detected for fake reviewer case
- malicious memory is excluded from trusted baseline
- benchmark emits machine-readable metrics

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest \
  tests/test_review_hardening.py \
  tests/test_review_queue_worker.py \
  tests/test_review_freshness.py \
  tests/test_review_adapter_config.py \
  tests/test_review_gate_hardening.py \
  tests/test_review_query_dsl.py \
  tests/test_review_benchmark.py \
  -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest \
  tests/test_cli_review.py \
  tests/test_cli_review_adversarial.py \
  tests/test_cli_run_review.py \
  tests/test_review_gate.py \
  tests/test_landing.py \
  tests/test_recover.py \
  tests/test_runner.py \
  -q
```

## Implementation Review Checklist

- Review remains disabled by default.
- Queue worker failure never mutates target attempt.
- Freshness is enforced before auto apply.
- Stale reviews are visible in status/report/query.
- Adapter execution is bounded and auditable.
- No direct network access is added to AIT core.
- `verified_status` remains Git/provenance integrity only.
- Override is first-class and auditable, not a fake pass.
- Reports distinguish passed, blocked, overridden, accepted risk, stale, and queued states.
- Benchmark metrics can be compared across implementation changes.
