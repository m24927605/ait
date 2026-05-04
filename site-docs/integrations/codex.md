---
title: Run Codex CLI safely with Git worktree isolation
description: >-
  Use ait to wrap OpenAI Codex CLI so every session edits an isolated Git
  worktree, with prompt, output, and commits recorded as a reviewable attempt.
---

# Codex CLI

Wrap [Codex CLI](https://github.com/openai/codex) with `ait` so each session
runs in an isolated Git worktree with full provenance.

## Why wrap Codex with ait

- Codex changes are confined to an attempt worktree — your root checkout is
  untouched until you promote.
- Failed sessions remain available for inspection, not silently dropped.
- Successive Codex runs feed `ait`'s repo-local memory, so the next session
  can recall what was already tried.

## Setup

```bash
ait init                  # detects `codex` on PATH, auto-installs hook + wrapper
ait adapter doctor codex  # optional sanity check
```

`ait init` writes `.codex/hooks.json` and the bridge under
`.ait/adapters/codex/` automatically when `codex` is on `$PATH`. Use
`ait adapter setup codex` to re-run the install explicitly.

## Run Codex under ait

Direct invocation works after setup:

```bash
codex
```

Or wrap explicitly with intent:

```bash
ait run --adapter codex --intent "Implement parser edge cases" -- codex
```

## Repair and refresh

If the wrapper drifts (e.g. after upgrading Codex):

```bash
ait repair codex
```

## Review attempts

```bash
ait attempt list
ait attempt show <attempt-id>
ait memory recall "parser edge cases"
```

## See also

- [Getting started](../getting-started.md)
- [Claude Code integration](claude-code.md)
- [Aider integration](aider.md)
