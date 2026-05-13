---
title: Adversarial code review
description: >-
  How to run adversarial code review on an ait attempt with Claude Code or a
  custom reviewer adapter, inspect findings, and use review evidence before
  applying AI-generated changes.
---

# Adversarial code review

Adversarial review is a second-pass reviewer agent for a finished AIT
attempt. The reviewer does not edit the target attempt worktree. AIT gives it
a structured brief, captures its output, parses findings, and stores the
review evidence under `.ait/`.

This is different from asking another agent to "look at the diff" manually:

- the review target is an AIT attempt, not a loose working tree
- the reviewer receives the same structured baseline, risk reasons, diff
  evidence, transcript evidence, and required JSON schema
- findings are persisted and queryable
- high and critical findings can become blocking review evidence

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
worktree, and removes `ANTHROPIC_API_KEY` from the child environment. This
prevents a silent fallback to provider API credits. If local Claude Code is
not installed or not logged in, the review fails closed.

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
policy.

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

## Demo flow

A compact demo for an audience already familiar with Claude Code and Codex:

1. Run one task with Claude Code and another with Codex, each as its own AIT
   attempt.
2. Show `ait attempt list` to compare the attempts without long IDs.
3. Run `ait review attempt latest-reviewable --mode light` to show deterministic
   risk reasons.
4. Run `ait review attempt latest-reviewable --mode adversarial
   --review-adapter claude-code` to show a real reviewer adapter.
5. Show `ait review finding list --status open` and `ait review report`.
6. Apply or promote only after the review evidence is acceptable.

The key point is that AIT is not "another prompt wrapper". It turns agent work
and reviewer work into durable, reviewable records tied to Git attempts.

## Boundaries

Adversarial review is still LLM-assisted review. It does not replace tests,
human judgment, or domain-specific verification. AIT gives the reviewer better
context and records the result, but a clean review is not a formal proof that
the change is correct.

AIT itself does not upload code to a SaaS. The reviewer adapter you choose
controls where the reviewer model runs.
