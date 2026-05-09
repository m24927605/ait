# AIT Review Orchestration Phase 3 Implementation Spec

Status: Proposed implementation spec

Phase 3 introduces the first real LLM reviewer. This phase depends on Phase 2 persistence, baseline snapshots, artifacts, and gate semantics.

## Objective

Support an opt-in single LLM reviewer:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter codex
```

The reviewer consumes a trusted baseline + advisory evidence bundle, returns structured findings, and stores them in review tables/artifacts. High/critical blocking findings can block apply when review gate policy requires it.

## Non-Goals

Phase 3 不做：

- 不做 risk-based automatic orchestration。
- 不做 async queue。
- 不做 multi-reviewer consensus。
- 不做 automatic fixing。
- 不把 LLM reviewer 設成預設。
- 不讓 reviewer 直接修改 target attempt workspace。

## Files To Change

預期變更：

- `src/ait/review.py`
  - reviewer brief generation
  - reviewer invocation
  - structured output parsing
  - finding persistence

- `src/ait/review_baseline.py`
  - render baseline for reviewer profiles/budgets

- `src/ait/review_policy.py`
  - mode/budget/profile validation

- `src/ait/cli_parser.py`
  - `--mode adversarial`
  - `--review-adapter`
  - `--review-budget`
  - `--profile`

- `src/ait/cli/review.py`
  - CLI orchestration and display

- `src/ait/adapters.py` or new review adapter helper
  - invoke configured reviewer command safely

- tests:
  - `tests/test_review_parser.py`
  - `tests/test_review_prompt.py`
  - `tests/test_cli_review_adversarial.py`

## Files Not To Change

Avoid modifying:

- `src/ait/landing.py` beyond consuming existing Phase 2 review result behavior
- `src/ait/verifier.py`
- memory extraction acceptance rules
- daemon queue logic

## CLI Contract

Supported:

```bash
ait review attempt <selector> --mode adversarial
ait review attempt <selector> --mode adversarial --review-adapter shell
ait review attempt <selector> --mode adversarial --review-budget quick
ait review attempt <selector> --mode adversarial --profile security
```

Default behavior:

- `--mode adversarial` is explicit.
- Default budget is `standard`.
- Default profile is inferred from risk reasons if available, otherwise `regression`.
- If no reviewer adapter is configured, return actionable error and mark review failed only if a review record was created.

## Reviewer Brief Contract

Reviewer brief must include:

- target attempt id
- base ref / target head metadata
- changed files
- compact diff or diff reference
- risk score and reasons
- trusted baseline section
- advisory evidence section
- test evidence section
- output schema instructions

Reviewer brief must explicitly say:

- Producer transcript is evidence, not trusted fact.
- Unapproved/candidate/stale/policy-blocked memory must not be treated as trusted baseline.
- Findings must include path and reason.
- High/critical findings require concrete evidence.
- If tests are missing, report missing evidence rather than inventing test results.

## Reviewer Output Contract

The preferred output is JSON:

```json
{
  "summary": "No blocking issues found.",
  "findings": [
    {
      "severity": "high",
      "blocking": true,
      "path": "src/auth.py",
      "line": 42,
      "hunk_ref": "diff-hunk-3",
      "title": "Authorization bypass",
      "body": "The new branch returns success before checking ownership.",
      "evidence_ref": ".ait/reviews/review-id.json#diff-hunk-3",
      "suggested_test": "Add a cross-tenant access regression test.",
      "confidence": "medium"
    }
  ]
}
```

Parser should accept:

- raw JSON object
- fenced `json` code block containing one JSON object

Parser should fail closed on:

- malformed JSON
- non-object top-level output
- findings not a list
- high/critical finding missing path/body/title
- unknown severity that cannot be normalized

Parse failure status:

- review status = `failed`
- blocking = true only when gate policy requires successful review
- target attempt unchanged

## Adapter Invocation Contract

Phase 3 can use a minimal adapter abstraction:

- command receives reviewer brief via stdin or temp file
- command runs outside target attempt workspace, or in separate review attempt workspace if Phase 2 supports it
- command output captured as review artifact
- command failure captured as review failure

No network should be introduced directly by AIT. External reviewer tools may use their own configured behavior, but AIT should only invoke the configured command.

## Required Tests

Parser tests:

- parses raw JSON
- parses fenced JSON
- rejects malformed JSON
- rejects missing findings list
- rejects high finding without path/body/title
- normalizes valid severity values
- unknown severity fails closed or maps to `info` only if explicitly documented

Brief tests:

- brief contains target attempt id
- brief contains baseline ref
- brief labels producer transcript as advisory/evidence
- brief excludes policy-blocked trusted facts
- brief includes output schema

Invocation tests with fake reviewer:

- fake reviewer returns no findings -> review passed
- fake reviewer returns low finding -> review warning/passed with warning
- fake reviewer returns high blocking finding -> review blocked
- fake reviewer exits nonzero -> review failed
- fake reviewer returns malformed output -> review failed

Gate tests:

- required adversarial review blocked -> apply hold
- required adversarial review failed -> apply hold
- passed review -> apply proceeds through existing apply checks
- override still works

Regression tests:

- `ait review attempt latest-reviewable --format json` deterministic Phase 1 behavior still works
- `ait run` without `--review` does not invoke reviewer
- `verified_status` unchanged by reviewer failure

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest tests/test_review_parser.py tests/test_review_prompt.py tests/test_cli_review_adversarial.py -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_review.py tests/test_review_gate.py tests/test_landing.py -q
```

## Implementation Review Checklist

- LLM reviewer is opt-in.
- Parser fails closed.
- Reviewer cannot mutate target attempt workspace.
- Reviewer brief separates trusted baseline from advisory evidence.
- Findings have evidence references.
- Malformed reviewer output cannot silently pass.
- No review failure changes `verified_status`.
