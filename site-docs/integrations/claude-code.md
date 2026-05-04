---
title: Run Claude Code in a Git worktree with ait
description: >-
  Use ait to wrap Claude Code so each session edits an isolated Git worktree
  with full attempt provenance — prompt, files, status, and commits — and your
  main checkout stays untouched until you promote.
---

# Claude Code

Run [Claude Code](https://docs.claude.com/en/docs/claude-code) inside an
isolated Git worktree, with every session captured as a reviewable attempt.

## Why wrap Claude Code with ait

Claude Code is fast and capable, but a single prompt can edit many files
across your repository. `ait` keeps that work contained:

- The agent edits an **isolated worktree** instead of your root checkout.
- Every Claude Code run becomes one **attempt** — prompt, files, status,
  output, and commits stay linked.
- You can **inspect, discard, rebase, or promote** an attempt with normal
  Git concepts.
- A repo-local memory layer surfaces what previous Claude runs already
  tried.

## Setup

```bash
ait init                       # detects `claude` on PATH, auto-installs the wrapper + hook
ait adapter doctor claude-code # optional sanity check
```

`ait init` detects every supported agent CLI on `$PATH` and wires it up
in one shot — for Claude Code that means installing a repo-local
`claude` wrapper plus merging the Claude Code hook config into
`.claude/settings.json`. To re-run setup explicitly (e.g. after
upgrading Claude Code), use `ait adapter setup claude-code`.

## Run Claude Code under ait

Use Claude Code exactly as you normally would:

```bash
claude -p --permission-mode bypassPermissions \
  "Shorten the README and improve the quickstart"
```

Or wrap the call explicitly:

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
```

Set explicit intent and commit text via environment variables:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "Shorten the README and improve the quickstart"
```

## Review and promote

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

Promote when the diff is good:

```bash
ait attempt promote <attempt-id> --to main
```

Discard when it is not:

```bash
ait attempt discard <attempt-id>
```

## See also

- [Getting started](../getting-started.md)
- [Codex CLI integration](codex.md)
- [Aider integration](aider.md)
