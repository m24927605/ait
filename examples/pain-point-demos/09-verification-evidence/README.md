# 09 - Adversarial Review

## Pain

An agent can produce a plausible code change that still needs to be challenged:
no tests, incomplete evidence, or risk hidden behind a confident answer.

## Demo Project

This case owns its own project:

```text
09-verification-evidence/workspace/
```

Claude Code creates `src/multiply.js` without adding or running tests. The demo
then runs an AIT adversarial review against that attempt. For repeatable live
demos, `run.sh` uses AIT's deterministic reviewer adapter to produce a stable
blocking finding.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `09-verification-evidence/workspace/`.

```bash
ait query --on attempt 'title~"risky multiply change"' --format table
ait attempt show <attempt-id>
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
```

Use the output to explain:

- `ait attempt show` shows the original agent attempt and its evidence.
- `evidence_summary.observed_tests_run` shows whether tests were observed.
- `review.mode="adversarial"` shows the attempt was challenged by adversarial review.
- `review.status="blocked"` shows the review did not accept the attempt as-is.
- `ait review finding list` shows the blocking finding that must be addressed.

## Demo Takeaway

AIT can preserve the agent's work and separately record an adversarial review
that challenges whether the result is safe to accept.
