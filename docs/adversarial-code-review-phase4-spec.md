# AIT Review Orchestration Phase 4 Implementation Spec

Status: Proposed implementation spec

Phase 4 wires the Phase 3 single LLM reviewer into risk-based async orchestration. This is the first phase where `ait run --review risk-based --apply auto` can use LLM review automatically.

## Objective

Support risk-based orchestration:

```bash
ait run --review risk-based --apply auto -- ...
```

Low risk should remain fast. High/critical risk should queue or run required review before auto apply is allowed.

## Non-Goals

Phase 4 不做：

- 不做 multi-reviewer consensus。
- 不新增 finding lifecycle commands beyond what Phase 2/3 already need。
- 不讓 all runs 預設 LLM review。
- 不讓 async review failure mutate target attempt。
- 不 bypass existing apply safety checks。

## Files To Change

預期變更：

- `src/ait/cli_parser.py`
  - Add `run --review {never,light,adversarial,risk-based}`.
  - Add `run --review-budget`.
  - Add `run --review-adapter` if not already wired.

- `src/ait/cli/run.py`
  - After `run_agent_command`, evaluate review policy.
  - Queue/run review depending on mode and apply policy.
  - Enforce gate before auto apply when required.

- `src/ait/review_policy.py`
  - Risk-based mode selection.
  - Required review decision.

- `src/ait/review_queue.py` or daemon-backed equivalent
  - Queue review jobs.
  - Track queued/running/completed/failed.

- `src/ait/cli/review.py`
  - `ait review status`.

- `src/ait/run_report.py` and report renderers
  - Include queued/running review state.

- tests:
  - `tests/test_review_queue.py`
  - `tests/test_cli_run_review.py`
  - `tests/test_review_status.py`

## Files Not To Change

Avoid modifying:

- verifier semantics
- memory candidate approval logic
- unrelated adapter setup
- cleanup semantics beyond preserving active review artifacts

## Run CLI Contract

Supported:

```bash
ait run --review never -- ...
ait run --review light -- ...
ait run --review adversarial -- ...
ait run --review risk-based -- ...
ait run --review risk-based --apply auto -- ...
```

Default:

- If `--review` omitted, use repo policy.
- If repo policy omitted, behave as `never`.
- `risk-based` performs deterministic risk scan first.

Behavior by apply policy:

- `--apply never`: do not block run; queue review if requested/required by policy.
- `--apply auto/current/branch`: if review gate is required, wait for sync review or hold until queued review completes.

Phase 4 can choose one of two implementation modes:

- Simple mode: required review runs synchronously before auto apply.
- Full mode: required review queues asynchronously and auto apply holds with clear message.

If choosing simple mode first, document that async queue is deferred within Phase 4.

## Review Queue Contract

Review job fields:

- review id
- target attempt id
- mode
- budget
- profiles
- adapter
- status
- created_at
- started_at
- completed_at
- failure reason

Queue invariants:

- duplicate required review jobs for the same target/mode/policy hash should be deduped.
- crashed jobs become failed or recoverable, not silently running forever.
- target attempt status is never changed by queue failure.

## Status CLI Contract

Command:

```bash
ait review status [--format text|json]
```

JSON output:

```json
{
  "schema_version": 1,
  "reviews": [
    {
      "review_id": "review:ulid",
      "target_attempt_id": "repo:ulid",
      "status": "queued",
      "mode": "adversarial",
      "risk_level": "high",
      "blocking": true
    }
  ]
}
```

Text output should show:

- target attempt
- status
- risk
- whether it blocks apply
- next command

## Apply Gate Contract

When auto apply is requested:

- review not required -> existing apply behavior
- required review missing -> hold
- required review queued/running -> hold with review status message
- required review failed -> hold
- required review blocked -> hold
- required review passed -> continue apply
- required review overridden -> continue apply and report override

No path should silently apply when required review is missing or incomplete.

## Required Tests

Run integration tests:

- `--review never` does not create review.
- `--review risk-based --apply never` completes run and records/queues review if high risk.
- low-risk risk-based run does not invoke fake LLM reviewer.
- high-risk risk-based run invokes or queues fake reviewer.
- `--apply auto` holds when required review is queued/running.
- `--apply auto` applies only after passed review and existing apply checks.

Queue tests:

- queue creates review job.
- duplicate queue request dedupes.
- job status transitions queued -> running -> passed.
- job failure transitions to failed and stores reason.
- status command lists queued/running/completed jobs.

Policy tests:

- default no review if policy missing.
- sensitive paths require adversarial review when policy says so.
- invalid policy values fallback safely.
- policy hash change makes old review stale.

Report tests:

- run report includes queued/running review.
- apply hold reason includes review gate.
- report includes next command.

Regression tests:

- existing `ait run --apply never` behavior unchanged when review omitted.
- existing `ait apply latest` behavior unchanged when review policy disabled.
- review queue does not interfere with cleanup of unrelated workspaces.

## Verification Commands

Targeted:

```bash
PYTHONPATH=src uv run pytest tests/test_review_queue.py tests/test_cli_run_review.py tests/test_review_status.py -q
```

Regression:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_landing.py tests/test_cleanup.py -q
```

## Implementation Review Checklist

- `ait run` does not wait for LLM unless mode/policy/apply requires it.
- Auto apply fails closed when required review incomplete.
- Queue jobs are deduped.
- Status output is actionable.
- Default behavior remains review disabled.
- No queue failure mutates target attempt.
