---
title: Run Aider in an isolated Git worktree with ait
description: >-
  Use ait to wrap Aider so each session edits an isolated Git worktree.
  Aider's commits land inside the attempt with full prompt and file
  provenance, ready for review and promotion.
---

# Aider

Run [Aider](https://aider.chat/) inside an isolated Git worktree managed by
`ait`, with each session recorded as a reviewable attempt.

## Why wrap Aider with ait

- Aider commits to an isolated worktree — your main branch stays clean
  until you promote.
- Each session becomes one attempt with prompt, edited files, and the
  commits Aider produced.
- Repo-local memory keeps prior Aider sessions queryable.

## Setup

```bash
ait init
ait adapter setup aider
ait adapter doctor aider
```

## Run Aider under ait

```bash
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
```

Or after setup, just call `aider` directly inside the repository.

## Review and promote

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

## See also

- [Getting started](../getting-started.md)
- [Claude Code integration](claude-code.md)
- [Codex CLI integration](codex.md)
