# Review Benchmark Fixture Spec

This directory contains local, deterministic fixtures for AIT review benchmark
dogfooding. Fixtures are test data, not public proof that adversarial review
catches defects in general.

## Current File

`cases.json` is the active fixture consumed by `src/ait/review_benchmark.py`
and `tests/test_review_benchmark.py`.

Each case must include:

| Field | Purpose |
| --- | --- |
| `id` | Stable case id for reports and golden expectations. |
| `vulnerable_diff` | Minimal diff-like text the reviewer evaluates. |
| `malicious_prompt` | Optional prompt injection or bad instruction to ignore. |
| `misleading_memory` | Optional candidate/stale memory that must not become trusted baseline. |
| `expected_findings` | Expected actionable findings with severity, path, title, body, evidence, test, and confidence. |
| `expected_blocked_memory_sources` | Candidate or blocked memory sources that must not be trusted. |
| `trusted_baseline_sources` | Sources the reviewer may treat as accepted baseline. |
| `expected_summary_contains` | Signal expected in the benchmark summary. |
| `expected_risk_level` | Expected risk calibration for the case. |
| `baseline_required_to_find` | Whether the case requires trusted baseline context to find the issue. |

## Current Cases

| Case | Purpose |
| --- | --- |
| `auth-bypass` | High-risk authorization regression with misleading candidate memory. |
| `billing-rounding-loss` | Money-impacting precision regression. |
| `dependency-typosquat` | Suspicious dependency addition. |
| `migration-data-loss` | Destructive database migration. |
| `ci-secret-leak` | CI secret exposure. |
| `missing-regression-test` | Risky behavior change without targeted tests. |
| `stale-memory-api` | Stale memory contamination case. |
| `prompt-injection-ignore-tests` | In-diff prompt-injection instruction. |
| `benign-doc` | Low-risk documentation change used to measure false positives. |
| `benign-refactor` | Safe refactor used to measure false positives. |

## Next Fixture Backlog

The active fixture now has 10 cases. The next backlog expands depth within each
risk area:

| Proposed id | Risk area | Expected signal |
| --- | --- | --- |
| `auth-cross-tenant-cache` | auth | Reviewer catches cache-key auth boundary loss. |
| `billing-refund-sign` | billing | Reviewer catches negative/positive refund sign reversal. |
| `dependency-lockfile-drift` | dependency | Reviewer flags dependency manifest/lockfile mismatch. |
| `migration-backfill-timeout` | migration | Reviewer catches unsafe backfill behavior. |
| `ci-permission-widening` | CI/deployment | Reviewer flags broadened workflow permissions. |
| `stale-memory-config` | memory trust | Reviewer ignores stale config memory. |
| `benign-test-only` | false positive control | Reviewer avoids findings for test-only coverage. |

## Acceptance Criteria

- The deterministic fake reviewer path must run without network, login state,
  API keys, or paid credits.
- Reports must include recall, false positives, evidence completeness,
  summary fidelity, risk calibration, baseline usefulness, latency, and token
  cost when available.
- Candidate, stale, superseded, or policy-blocked memory must not count as
  trusted baseline evidence.
- At least one real local reviewer dogfood run must be recorded separately and
  labeled with adapter, command, auth mode, elapsed time, and environment
  assumptions before public quality claims are made.

## Code Review Standard

Fixture changes should be reviewed for behavioral coverage, not just JSON
syntax. A reviewer should check that each expected finding is actionable, has a
path and evidence reference, includes a suggested regression test when
appropriate, and that every no-finding case protects against false positives.
