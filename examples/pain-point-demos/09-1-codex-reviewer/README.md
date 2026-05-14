# 09-1 - Claude Implementation, Codex Review

## Pain

Using one agent to implement and another agent to review is useful only if the
handoff is explicit and the review result is recorded as evidence.

## Demo Project

This demo project is created at:

```text
09-1-codex-reviewer/workspace/
```

Claude Code implements `divide(a, b)` without zero-division handling. AIT then
runs an adversarial review with Codex as the reviewer.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `09-1-codex-reviewer/workspace/`.

```bash
ait query --on attempt 'title~"unsafe divide implementation"' --format table
ait attempt show <attempt-id>
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review status --format text
ait review report --attempt <attempt-id> --format json
ait review finding list --severity high --format text
ait config show --format json
ait apply <attempt-id> --mode current
```

Use the output to explain:

- Claude Code produced the implementation attempt.
- Codex ran later as the adversarial reviewer through AIT.
- `review.mode="adversarial"` records the review mode.
- `review.status="blocked"` records that the implementation was not accepted as-is.
- `ait review report` shows the reviewer adapter and review summary for the attempt.
- `ait review finding list` shows the concrete blocking finding.
- `ait config show --format json` confirms this demo workspace requires the review gate before apply.
- `ait apply <attempt-id> --mode current` should be held instead of applying the blocked attempt.

## Demo Takeaway

AIT makes cross-agent review auditable: Claude Code can implement, Codex can
challenge, and the review decision remains queryable in the repo. When the
review gate is enabled, the blocked review also prevents the attempt from being
applied.
