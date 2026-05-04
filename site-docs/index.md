---
title: ait — Git workflow layer for AI coding agents
description: >-
  ait wraps Claude Code, Codex, Aider, Gemini CLI, and Cursor with Git
  worktree isolation, attempt provenance, cross-session repo-local memory
  with summaries, cross-agent context handoff, and reviewable promotion.
  Open-source, dependency-free, runs on top of Git.
---

# ait

**The Git workflow layer for AI coding agents — worktree isolation,
attempt provenance, cross-session memory, reviewable promotion.**

`ait` wraps the agent CLIs you already use — Claude Code, Codex, Aider,
Gemini CLI, Cursor — and turns each run into a **reviewable attempt**.
The agent edits an isolated Git worktree, `ait` records what happened,
and your main checkout stays untouched until you promote the result.

```bash
pipx install ait-vcs    # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

The package is named `ait-vcs` on PyPI and npm. The installed command is `ait`.

## Problems ait solves

| Problem with agent coding today | What ait adds |
| --- | --- |
| A bad prompt rewrites half your repo before you notice | Each run lands in an isolated Git worktree — your root checkout never moves |
| The diff has no useful provenance — which prompt produced it? | Attempts link intent, command output, files, and commits in one record |
| Failed or partial runs leave your working copy half-broken | Bad attempts stay isolated; `ait attempt discard` removes them in one command |
| The next agent repeats investigation you already paid tokens for | Repo-local memory feeds prior attempts and commits to the next run |
| Two agents on the same task stomp each other | Each attempt has its own worktree — run N agents in parallel |
| Did the agent really fix it, or just claim it did? | Explicit `ait attempt promote` keeps speculative changes out of main until you decide |
| Cross-agent hand-offs lose every previous decision | Memory layer auto-imports `CLAUDE.md`, `AGENTS.md`, and prior attempts |
| Provenance tooling wants to ship your code to a SaaS | Metadata stays in `.ait/` next to `.git/` — harness daemon is local-only (Unix socket, no network), no telemetry |
| "Where's that prompt I wrote last month?" → grep shell history | Query attempts, intents, and commits with a structured DSL |

See the full deep-dive on each problem in [Why ait](why-ait.md).

`ait` is **not** another agent. It is the Git layer around the agents you
already trust.

## Supported agents

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [Any other shell agent](integrations/shell.md)

## Status

`ait` is alpha quality. It is intended for local dogfooding and early users
who are comfortable with Git workflows. Metadata is local to one repository
under `.ait/`; it is not synchronized across machines.

## Project links

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI package](https://pypi.org/project/ait-vcs/)
- [npm package](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
