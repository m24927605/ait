---
title: Run Gemini CLI with attempt history using ait
description: >-
  Wrap Gemini CLI with ait so every session edits an isolated Git worktree
  and is captured as a reviewable attempt, with repo-local memory across
  runs.
---

# Gemini CLI

Run [Gemini CLI](https://github.com/google-gemini/gemini-cli) inside an
isolated Git worktree managed by `ait`, with each session recorded as a
reviewable attempt.

## Why wrap Gemini CLI with ait

- Each Gemini session edits an attempt worktree, not your root checkout.
- Sessions are queryable later via `ait memory recall`.
- You promote only the attempts you want.

## Setup

```bash
ait init
ait adapter setup gemini
ait adapter doctor gemini
```

## Run Gemini under ait

```bash
ait run --adapter gemini --intent "Add config validation" -- gemini
```

Or call `gemini` directly inside the repository after setup.

## Review attempts

```bash
ait attempt list
ait attempt show <attempt-id>
```

## See also

- [Getting started](../getting-started.md)
- [Claude Code integration](claude-code.md)
- [Cursor integration](cursor.md)
