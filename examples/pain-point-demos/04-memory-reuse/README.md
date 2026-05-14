# 04 - Memory Reuse

## Pain

Claude investigates a problem, then Codex starts from scratch and repeats the
same work.

## Demo Project

This case owns its own project:

```text
04-memory-reuse/workspace/
```

Claude Code records an auth retry finding. AIT stores it as repo-local memory.
Codex then receives it through `AIT_CONTEXT_FILE`.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `04-memory-reuse/workspace/`.

```bash
ait query --on attempt 'title~"Claude: investigate auth retry"' --format table
ait query --on attempt 'title~"Codex: reuse auth retry investigation"' --format table
ait memory list --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
```

Use the output to explain:

- Claude Code and Codex are separate attempts.
- `ait memory list` shows the repo-local memory entry.
- Claude Code changed `notes/auth-retry.md`.
- Codex changed `context-proof.txt`.
- Codex's trace shows it received context through AIT instead of starting from
  nothing.

## Demo Takeaway

AIT lets useful findings survive across agent sessions and across different
agents without relying on chat scrollback.
