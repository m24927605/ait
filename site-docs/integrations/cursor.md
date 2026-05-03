---
title: Run Cursor agents with reviewable Git provenance via ait
description: >-
  Wrap Cursor CLI agents with ait so each agent run edits an isolated Git
  worktree and produces an attempt log of files, status, and commits ready
  for review.
---

# Cursor

Run [Cursor](https://cursor.sh/) CLI agents inside an isolated Git worktree
managed by `ait`, with each agent run captured as a reviewable attempt.

## Why wrap Cursor agents with ait

- Cursor edits stay confined to an attempt worktree.
- Each run produces an attempt log: prompt, edited files, exit status, and
  commits.
- Promotion is explicit — your root checkout is never modified silently.

## Setup

```bash
ait init
ait adapter setup cursor
ait adapter doctor cursor
```

## Run Cursor under ait

```bash
ait run --adapter cursor --intent "Migrate to new SDK" -- cursor
```

Or call the wrapped `cursor` command directly after setup.

## Review and promote

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

## See also

- [Getting started](../getting-started.md)
- [Claude Code integration](claude-code.md)
- [Gemini CLI integration](gemini.md)
