# 06 - Explicit Promotion

## Pain

An agent saying "done" should not automatically mean its result is accepted
into `main`.

## Demo Project

This case owns its own project:

```text
06-explicit-promotion/workspace/
```

The demo creates Claude Code and Codex candidate attempts, then accepts only
the Claude Code result into the current branch.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `06-explicit-promotion/workspace/`.

```bash
ait query --on attempt 'title~"explicit promotion candidate"' --format table
ait attempt list --format table --limit 5
ait attempt show <promoted-attempt-id>
```

Use the output to explain:

- Multiple candidate attempts can exist at the same time.
- `verified_status` shows which attempt became the accepted result.
- `result_promotion_ref`, when present, is the recorded apply/promotion evidence.
- AIT separates "agent produced a result" from "human accepted the result".

## Demo Takeaway

AIT requires an explicit apply/accept step before an attempt becomes the
accepted result in `main`.
