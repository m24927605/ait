---
title: Wrap any shell agent with Git worktree isolation
description: >-
  Use ait's generic shell adapter to give Git worktree isolation and attempt
  provenance to any custom AI agent, automation script, or CLI tool.
---

# Shell agents

The `shell` adapter wraps **any** command — custom agents, automation
scripts, or one-off tools — so the work happens inside an attempt worktree
with full provenance.

## When to use the shell adapter

- You have a custom AI agent that is not (yet) a first-class adapter.
- You want to record a fixture-regeneration script or a one-off automation
  as an attempt.
- You want the same review-and-promote workflow for arbitrary commands.

## Run any command under ait

```bash
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

Anything after `--` is the command to run. `ait` records the prompt
(intent), exit status, edited files, and any commits the command produces.

## Review attempts

```bash
ait attempt list
ait attempt show <attempt-id>
```

## See also

- [Getting started](../getting-started.md)
- [Claude Code integration](claude-code.md)
