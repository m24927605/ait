# 07 - Cross-Agent Handoff

## Pain

Claude Code can make a decision, then Codex takes over without seeing that
context.

## Demo Project

This case owns its own project:

```text
07-cross-agent-handoff/workspace/
```

Claude Code writes and accepts an `AGENTS.md` decision. AIT imports that
decision as memory. Codex then receives it through AIT context.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `07-cross-agent-handoff/workspace/`.

```bash
ait query --on attempt 'title~"record calculator module decision"' --format table
ait query --on attempt 'title~"read calculator module handoff"' --format table
ait memory list --format table
ait attempt show <decision-attempt-id>
ait attempt show <codex-attempt-id>
```

Use the output to explain:

- The Claude Code decision attempt became the accepted result.
- `ait memory list` shows repo-local memory created from the decision.
- Codex is a separate later attempt.
- Codex receives the decision through AIT context instead of hidden chat state.

## Demo Takeaway

AIT makes cross-agent handoff explicit, inspectable, and local to the repo.
