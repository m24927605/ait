# 05 - Parallel Agents

## Pain

Running Claude Code and Codex in the same checkout can cause them to overwrite
each other's files.

## Demo Project

This case owns its own project:

```text
05-parallel-agents/workspace/
```

Claude Code and Codex both create `approach.txt`, but AIT gives each agent a
different attempt worktree.

## Run

```bash
./run.sh
```

## AIT Verification Flow

Run these from `05-parallel-agents/workspace/`.

```bash
ait query --on attempt 'title~"parallel approach"' --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
ait attempt list --format table --limit 5
```

Use the output to explain:

- Both attempts start from the same base revision.
- Each attempt has its own `workspace_ref`.
- Both attempts changed `approach.txt`.
- Parallel work stays isolated until a human chooses what to apply.

## Demo Takeaway

AIT makes parallel agent work comparable instead of letting agents race inside
the same checkout.
