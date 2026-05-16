# Review Benchmark Dogfood Report

## Status

This is the initial dogfood report for AIT adversarial review quality. It is a
baseline report, not a published quality claim. CI numbers come from the
deterministic fake reviewer path in `src/ait/review_benchmark.py`, using the
fixture at `tests/fixtures/review_benchmark/cases.json`. Local real-reviewer
dogfood artifacts also exist for Claude Code and Codex. The current repaired
local runs complete successfully, but they remain machine/local-auth-dependent
dogfood evidence and must not be described as benchmark-proven quality.

The purpose is to make the review-gate quality work measurable before claiming
that adversarial review catches more real defects.

## Current Coverage

| Item | Current state |
| --- | --- |
| Benchmark runner | `src/ait/review_benchmark.py` |
| Unit tests | `tests/test_review_benchmark.py` |
| Fixture | `tests/fixtures/review_benchmark/cases.json` |
| Fixture expansion spec | `tests/fixtures/review_benchmark/README.md` |
| Current fixture cases | 10 |
| Deterministic CI reviewer | `fake:case`, `fake:warn`, `fake:pass` |
| Real Claude/Codex benchmark | Local dogfood artifacts recorded in `docs/review-benchmark-real-dogfood-claude-code.json` and `docs/review-benchmark-real-dogfood-codex.json` |
| Published quality claim | None |

## Current Fixture Cases

| Case | Risk area | Expected risk | Expected finding count | Purpose |
| --- | --- | --- | --- | --- |
| `auth-bypass` | authorization | high | 1 | Reviewer should catch a removed ownership check and treat misleading candidate memory as untrusted. |
| `billing-rounding-loss` | billing | high | 1 | Reviewer should catch money-impacting precision loss. |
| `dependency-typosquat` | dependency | high | 1 | Reviewer should flag suspicious dependency names. |
| `migration-data-loss` | migration | critical | 1 | Reviewer should block destructive migrations without rollback/evidence. |
| `ci-secret-leak` | CI/deployment | critical | 1 | Reviewer should catch secret exposure in workflow changes. |
| `missing-regression-test` | testing | medium | 1 | Reviewer should flag risky behavior changes without targeted tests. |
| `stale-memory-api` | memory contamination | high | 1 | Reviewer should ignore stale memory and use the trusted current baseline. |
| `prompt-injection-ignore-tests` | security | medium | 1 | Reviewer should ignore in-diff instructions aimed at the reviewer. |
| `benign-doc` | documentation | low | 0 | Reviewer should avoid inventing findings for a harmless README change. |
| `benign-refactor` | false-positive control | low | 0 | Reviewer should avoid inventing findings for a safe rename/refactor. |

## Baseline Metrics

Command used:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from ait.review_benchmark import load_benchmark_cases, run_review_benchmark

path = Path("tests/fixtures/review_benchmark/cases.json")
print("cases", len(load_benchmark_cases(path)))
for mode in ["fake:case", "fake:warn", "fake:pass"]:
    result = run_review_benchmark(path, fake_reviewer=mode)
    print(mode, result.to_dict())
PY
```

Results:

| Reviewer | case_count | finding_recall | false_positive_count | evidence_completeness | summary_fidelity | risk_scoring_calibration | baseline_usefulness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fake:case` | 10 | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 0.4 |
| `fake:warn` | 10 | 0.0 | 10 | 0.0 | 0.0 | 0.4 | 0.4 |
| `fake:pass` | 10 | 0.0 | 0 | 1.0 | 0.2 | 0.4 | 0.0 |

`latency_ms` is effectively zero for fake reviewers because no real model is
invoked. Token-cost fields are not available yet in the benchmark output.

## Real Local Dogfood Artifacts

Initial commands used on 2026-05-16:

```bash
uv run ait review benchmark run \
  --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter claude-code \
  --dogfood \
  --permission-profile read-only \
  --model claude-code-2.1.140-local-cli \
  --timeout-seconds 15 \
  --output docs/review-benchmark-real-dogfood-claude-code.json \
  --format json

uv run ait review benchmark run \
  --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter codex \
  --dogfood \
  --permission-profile read-only \
  --model codex-cli-0.130.0-local-cli \
  --timeout-seconds 15 \
  --output docs/review-benchmark-real-dogfood-codex.json \
  --format json
```

| Adapter | Local CLI | run_status | Result |
| --- | --- | --- | --- |
| `claude-code` | Claude Code 2.1.140, `claude -p` | `unavailable` | First real invocation timed out after 15 seconds; remaining cases were marked unavailable with the same local failure reason. |
| `codex` | Codex CLI 0.130.0, `codex exec --sandbox read-only -` | `completed_with_failures` | First case returned output that failed the structured finding schema; second real invocation timed out after 15 seconds, so remaining cases were marked unavailable. |

### Failure Root Cause

The initial failed artifacts were caused by AIT benchmark defects, not by a
single external Claude Code or Codex outage.

1. The benchmark prompt asked for JSON with only `summary` and `findings`, while
   `parse_review_output` required richer finding fields such as `path`, `title`,
   `body`, `evidence_ref`, and `suggested_test`. Real reviewers returned useful
   fields with common names such as `file`, `issue`, `details`,
   `recommendation`, or `recommended_fix`, and AIT rejected them.
2. The 15-second per-case timeout was too short for real local reviewer CLIs.
   Single successful invocations took roughly 15 to 25 seconds on this machine.
3. `finding_recall` used exact expected-title matching. Real reviewers often
   found the right defect with different wording, so the metric could report
   zero recall for a useful review.
4. The first artifacts did not include redacted stdout/stderr excerpts, making
   failure diagnosis too opaque.

### Repaired Real Dogfood Commands

Commands used after the repair on 2026-05-16:

```bash
uv run ait review benchmark run \
  --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter claude-code \
  --dogfood \
  --permission-profile read-only \
  --model claude-code-2.1.140-local-cli \
  --timeout-seconds 120 \
  --output docs/review-benchmark-real-dogfood-claude-code.json \
  --format json

uv run ait review benchmark run \
  --fixture tests/fixtures/review_benchmark/cases.json \
  --reviewer-adapter codex \
  --dogfood \
  --permission-profile read-only \
  --model codex-cli-0.130.0-local-cli \
  --timeout-seconds 120 \
  --output docs/review-benchmark-real-dogfood-codex.json \
  --format json
```

| Adapter | run_status | case_count | finding_recall | false_positive_count | summary_fidelity | risk_scoring_calibration | baseline_usefulness | latency_ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `claude-code` | `completed` | 10 | 1.0 | 11 | 0.6 | 0.8 | 0.4 | 265609 |
| `codex` | `completed` | 10 | 1.0 | 1 | 0.5 | 0.9 | 0.4 | 166956 |

These artifacts are valuable because they prove the benchmark path invokes real
local CLIs and records stdout/stderr excerpts, parse status, return code, and
latency honestly. They are still not evidence that reviewer quality is proven:
Claude produced many false positives in this run, token/cost metadata is still
missing, and repeated runs are needed before making stronger public claims.

## Metrics Definition

| Metric | Definition | Review-gate reason |
| --- | --- | --- |
| `finding_recall` | Expected findings matched divided by expected findings. | Measures whether the reviewer catches known defects. |
| `false_positive_count` | Findings not expected by the fixture. | Measures review fatigue and actionability risk. |
| `evidence_completeness` | Findings with path, title, and body. | Blocks vague findings from looking useful. |
| `summary_fidelity` | Summary includes expected fixture signal. | Checks whether the reviewer summary preserves the key issue. |
| `risk_scoring_calibration` | High/critical fixture cases produce high/critical findings; low cases do not. | Tests whether risk classification matches review-gate decisions. |
| `baseline_usefulness` | Cases where baseline context was required and findings were produced. | Measures whether repo memory contributes signal. |
| `trusted_baseline_contamination_rate` | Cases where blocked/stale memory entered trusted baseline. | Protects evidence-backed memory boundaries. |
| `non_actionable_warning_count` | Low/info findings with weak actionability. | Tracks noisy review output. |
| `latency_ms` | Elapsed benchmark runtime. | Needed to decide when LLM review is worth the delay. |
| `token_cost` | Input/output/cached tokens when a real adapter exposes them. | Needed to compare deterministic review with LLM-backed review. |

## Acceptance Targets Before Public Claims

AIT should not publicly claim benchmark-proven adversarial review quality until
all of these are true:

- At least 10 benchmark cases across auth, security, billing, dependency,
  migration, CI/deployment, and missing-test-evidence risk areas. This fixture
  count is now present; the remaining gate is real reviewer dogfood plus report
  quality.
- Deterministic fake reviewer path remains available for CI without API keys,
  local login, network, or paid credits.
- At least one real local reviewer run is recorded for Claude Code or Codex,
  clearly marked as machine/local-auth dependent. This is now true for both
  Claude Code and Codex, but one repaired local run per adapter is still not a
  quality claim.
- Reports include false positives, latency, and token/cost metadata when
  available, not only recall.
- Docs clearly separate `light` deterministic review from LLM-backed
  `adversarial` review.
- No report claims formal verification or guaranteed correctness.

## Implementation Plan

Ticket-level work orders for this plan live in
[`docs/ait-product-maturity-hardening-work-orders-zh.md`](ait-product-maturity-hardening-work-orders-zh.md),
Milestone B.

1. Continue expanding `tests/fixtures/review_benchmark/cases.json` beyond the
   initial 10 cases, following the backlog in
   `tests/fixtures/review_benchmark/README.md`.
2. Keep the benchmark CLI surface covered:

   ```bash
   ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json --fake-reviewer fake:case --format json
   ait review benchmark report --input .ait/review-benchmark/latest.json --format markdown
   ```

3. Improve real adapter dogfood reliability:
   - keep the 120-second default timeout unless repeated local data supports a
     lower adapter-specific profile
   - capture token/cost metadata when adapters expose it
   - preserve schema-specific reviewer prompts and parser alias coverage
   - rerun artifacts after local auth, permission profiles, or CLI versions
     change
4. Keep adversarial review docs linked to these artifacts only as dogfood
   evidence, not as proof of review quality.

## Test Plan

| Test | Coverage |
| --- | --- |
| `tests/test_review_benchmark.py::test_load_benchmark_cases_validates_fixture` | Fixture schema validation. |
| `tests/test_review_benchmark.py::test_fake_case_reviewer_reports_metrics_without_network` | Deterministic happy path, recall, false positives, evidence completeness. |
| `tests/test_review_benchmark.py::test_fake_warning_reviewer_counts_non_actionable_warnings` | Review fatigue/noise metric. |
| `tests/test_review_benchmark.py::test_real_reviewer_case_brief_spells_parser_schema_fields` | Real reviewer prompt must state the parser-required schema fields. |
| `tests/test_review_benchmark.py::test_real_reviewer_metrics_match_expected_findings_without_exact_title_match` | Real reviewer recall cannot depend on exact title wording. |
| `tests/test_review_benchmark.py::test_review_benchmark_run_and_report_cli` | JSON run output plus Markdown report limitation section. |
| `tests/test_review_benchmark.py::test_real_reviewer_dogfood_records_unavailable_once_without_repeating_timeout` | Real adapter timeout becomes truthful unavailable artifact without repeating the same stuck invocation 10 times. |
| `tests/test_review_parser.py::test_parses_common_reviewer_field_aliases` | Common real reviewer field names remain parseable without weakening high-risk evidence requirements. |
| Future CLI test: invalid fixture | Benchmark command must fail with a clear message. |

## Code Review Gate

Any PR changing review benchmark behavior must satisfy:

- CI path must not require a real LLM, network, login state, API key, or paid
  credits.
- Benchmark output must report false positives and latency, not only recall.
- Real reviewer results must be labeled with adapter, command, local auth mode,
  and environment assumptions.
- `light` review and `adversarial` review metrics must not be collapsed into
  one score.
- Blocked, stale, or candidate memory must not be counted as trusted baseline
  evidence.
- No docs may claim benchmark-proven quality until the acceptance targets above
  are met.

## Current Conclusion

AIT has the substrate for review-gate measurement: a 10-case fixture, a
deterministic runner, structured metrics, JSON/Markdown report CLI, tests, and
truthful real local dogfood artifacts for Claude Code and Codex. The current
repaired real artifacts complete successfully, so they support a stronger
substrate claim: AIT can invoke local reviewer CLIs, parse useful structured
findings, and record the result honestly. Public docs should still frame
adversarial review as an explicit extra safety pass until repeated real reviewer
runs show stable recall, acceptable false positives, latency, and cost.
