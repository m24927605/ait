---
title: Adversarial code review
description: >-
  How to run adversarial code review on an ait attempt with Claude Code or a
  custom reviewer adapter, inspect findings, and use review evidence before
  applying AI-generated changes.
---

# Adversarial code review

Adversarial review is the workflow that makes AIT feel less like "safer agent
runs" and more like an AI engineering control plane.

One agent implements. A different reviewer agent challenges the result. AIT
records the decision and can stop a blocked attempt from being applied.

The reviewer does not edit the target attempt worktree. AIT gives it a
structured brief, captures its output, parses findings, and stores the review
evidence under `.ait/`.

This is different from asking another agent to "look at the diff" manually:

- the review target is an AIT attempt, not a loose working tree
- the reviewer receives the same structured baseline, risk reasons, diff
  evidence, transcript evidence, and required JSON schema
- findings are persisted and queryable
- high and critical findings can become blocking review evidence
- review-gated apply can hold blocked attempts before they touch your checkout

## Why it raises review quality

Adversarial review improves AI code review because it changes both the role and
the information flow.

- **Role separation:** the implementing agent is no longer grading its own
  answer. A separate reviewer agent is asked to challenge the attempt.
- **Sharper prompt contract:** the reviewer is not asked for generic advice; it
  is asked to find reasons the attempt should not be accepted.
- **Better context:** the reviewer sees attempt metadata, changed files, diff
  evidence, test evidence, transcript references, risk reasons, and local
  baseline context.
- **Structured output:** findings become records with severity, path, body,
  confidence, and `blocking`.
- **Operational consequence:** when review gating is enabled, a blocked review
  can hold `ait apply`.

That is why the review is more than another chat response. It becomes
queryable, reportable, and enforceable workflow evidence.

## Quick start

Run a deterministic risk scan first:

```bash
ait review attempt latest-reviewable --mode light
```

Run Claude Code as the adversarial reviewer:

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code \
  --review-budget standard
```

Inspect findings and produce a portable report:

```bash
ait review finding list --status open
ait review report --attempt latest --format markdown --output docs/reviews/latest.md
```

Enable review-gated apply in `.ait/policy.json` when you want CLI apply to
require a clear latest review:

```json
{
  "schema": "ait.team_policy",
  "schema_version": 1,
  "apply": {
    "require_review_clearance": true
  }
}
```

Then try to apply a blocked attempt:

```bash
ait apply <attempt-id> --mode current
```

Expected result:

```text
AIT held the result because this repo requires review before apply.
Status: held
Reason: review gate: required review is blocked
```

When a finding is intentionally accepted or judged false positive, record the
reason:

```bash
ait review finding update <finding-id> --status false_positive --reason "not reachable"
ait review finding update <finding-id> --status accepted_risk --reason "accepted for demo"
```

## When to use it

Use adversarial review when the cost of a bad AI change is higher than the
cost of another reviewer pass:

- auth, billing, payments, security, deployment, CI, migration, or dependency
  changes
- large diffs or changes across multiple subsystems
- attempts with missing or weak test evidence
- before applying or promoting an important AI-generated result
- when comparing independent Claude Code and Codex attempts on the same task

For low-risk edits, `light` mode is usually enough because it is local,
deterministic, and fast.

## What the reviewer sees

AIT builds a reviewer brief from the attempt record and repo-local context.
The brief can include:

- target attempt metadata, changed files, and diff excerpts
- prompt and transcript references captured during the run
- structured test, build, and lint evidence when available
- deterministic risk reasons from `light` mode
- trusted repo-local memory facts allowed by policy
- prior failed attempts and prior review findings that are relevant to the
  same area
- the exact JSON schema the reviewer must return

Candidate, stale, superseded, or policy-blocked memory is advisory or excluded
instead of being treated as trusted baseline.

## Claude Code reviewer path

The built-in `claude-code` review adapter invokes the local CLI:

```bash
claude -p
```

AIT sends the brief on stdin, runs the reviewer outside the target attempt
worktree, and passes a minimal allowlisted environment to the child process.
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, and generic
`*TOKEN*`, `*SECRET*`, `*PASSWORD*`, or `*KEY*` names are not inherited by
default. This prevents a silent fallback to provider API credits. If local
Claude Code is not installed or not logged in, the review fails closed.

Check the local auth path:

```bash
ait adapter doctor claude-code --json
```

Expected local CLI mode reports `will_use_api_key: false` and
`will_fallback_to_credits: false`.

## Custom reviewer adapters

For local experiments, `--review-adapter` may be a command-style adapter:

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter 'command:python scripts/review_attempt.py'
```

The command receives the reviewer brief on stdin and must print the expected
structured JSON. Named review adapters can also be configured by repository
policy. Reviewer commands do not inherit the full process environment; add
specific non-secret variables only when needed:

```json
{
  "review": {
    "adapters": {
      "codex": {
        "env_allowlist": ["PATH", "HOME", "TMPDIR", "CODEX_HOME"]
      }
    }
  }
}
```

## Risk-based run policy

`risk-based` is a run policy. It lets AIT choose whether a run needs no review,
`light` review, or `adversarial` review from the risk assessment:

```bash
ait run \
  --review risk-based \
  --review-adapter claude-code \
  --adapter claude-code -- claude
```

Current policy:

- `low`: no review
- `medium`: `light`
- `high` or `critical`: `adversarial`

Queued reviews can be inspected and processed with:

```bash
ait review status
ait review worker --once
```

## Measuring review quality

AIT should not claim that adversarial review is automatically better without
evidence. The implemented workflow gives you the substrate to measure it:

- deterministic `light` review for cheap risk classification
- separate LLM-backed reviewer adapters for high-risk attempts
- structured findings with severity, confidence, path, status, and blocking
  state
- queryable review status and finding history
- review-gated apply when policy requires review

The still-missing evidence is repeated successful real-reviewer data: how many
bugs a reviewer found that the implementer missed, false positive rate,
latency, token cost, which risk patterns benefit most, and when deterministic
review is enough versus when an LLM reviewer pays off. Until that data is
published, treat adversarial review as an explicit extra safety pass, not proof
of correctness.

The current baseline report is tracked in the repository at
[`docs/review-benchmark-dogfood-report.md`](https://github.com/m24927605/ait/blob/main/docs/review-benchmark-dogfood-report.md).
It records deterministic fake-reviewer metrics, local Claude Code/Codex
dogfood artifacts, and the acceptance targets that must be met before stronger
public quality claims are made. The current repaired real dogfood artifacts
complete successfully; they prove honest local invocation, parsing, and
reporting, but they are still local dogfood evidence rather than review quality
proof.

## Demo flow

A compact demo for an audience already familiar with Claude Code and Codex:

1. Run Claude Code as the implementer.
2. Run Codex as the adversarial reviewer with `ait review attempt --mode
   adversarial --review-adapter codex`.
3. Show `ait query --on attempt 'review.status="blocked"' --format table`.
4. Show `ait review finding list --severity high --format text`.
5. Show `ait review report --attempt <attempt-id> --format json`.
6. Run `ait apply <attempt-id> --mode current` and show that the review gate
   holds the blocked attempt.

The key point is that AIT is not "another prompt wrapper". It turns agent work
and reviewer work into durable, reviewable records tied to Git attempts, then
lets that evidence affect whether code can land.

## Boundaries

Adversarial review is still LLM-assisted review. It does not replace tests,
human judgment, or domain-specific verification. AIT gives the reviewer better
context and records the result, but a clean review is not formal proof that the
change is correct.

AIT itself does not upload code to a SaaS. The reviewer adapter you choose
controls where the reviewer model runs.
