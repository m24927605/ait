---
title: Naked git-worktree vs ait — when to upgrade
description: >-
  You can already run parallel AI coding agents with raw git-worktree.
  Here is what stays manual — attempt provenance, prompt search, cross-agent
  memory, promote/discard — and when ait is worth adding on top of Git.
---

# Naked `git-worktree` vs ait

ait is a Git-native version control layer for AI coding agents (Claude
Code, Codex CLI, Aider, Gemini CLI, Cursor) — adding worktree
isolation, attempt provenance, cross-agent memory, and reviewable
promotion on top of Git. Open source (MIT), Python 3.14+,
dependency-free, no SaaS, no telemetry.

If you already use `git worktree add` to run parallel AI agents, this
page is for you. It compares the raw worktree workflow with the same
workflow under ait, line for line, so you can decide whether the
upgrade is worth one extra command (`ait init`).

## Both target the same problem — kind of

Raw `git-worktree` and ait both solve **isolation**: keep one agent's
edits out of another agent's working directory, and out of your root
checkout, until you decide otherwise.

That is where the overlap ends.

`git-worktree` is a Git primitive. It gives you a separate directory,
a separate branch, a shared object store. Nothing more. It does not
know what an "AI attempt" is. It does not record which prompt
produced which diff. It does not summarize what previous agents
already tried. It does not have a `discard` verb that cleans up the
working tree, the branch, the prompt log, and the captured output in
one shot.

ait treats each agent run as a structured **attempt**: a record that
links intent text, command, exit status, edited files, captured
output, and the resulting commits. The worktree is one detail among
many — and it is the easy detail.

For a wider walk through the design, see [Why ait](../why-ait.md).

## 7 things you do manually with naked `git-worktree`

| | Naked `git-worktree` | With ait |
| --- | --- | --- |
| **Create** | `git worktree add ../repo-claude-auth -b claude/auth` | `claude ...` — wrapper provisions worktree |
| **Name** | You invent a scheme: agent + branch + date | Auto: stable attempt ID + agent + intent slug |
| **Cleanup** | `git worktree remove`, then `git branch -D`, then prune stash files | `ait attempt discard <id>` — one verb |
| **Find a prompt** | `grep` shell history, hope you saved it | `ait attempt list --intent "auth retry"` |
| **Cross-worktree memory** | None — each Claude/Codex/Aider session starts blank | `AIT_CONTEXT_FILE` summarizes prior attempts + `CLAUDE.md` / `AGENTS.md` |
| **Promote to main** | Cherry-pick or merge the branch by hand, resolve drift | `ait attempt promote <id> --to main` |
| **Discard a bad run** | Manual: remove worktree + delete branch + clear partial commits + delete stash | `ait attempt discard <id>` removes all of it |

The point is not that any single column is impossible — it is that
the right column collapses 7 manual steps into one verb each, and
records the result for next week's you.

### A concrete example

The raw flow for one Claude Code run, three agents in parallel:

```bash
# Three worktrees, three branches, three terminals.
git worktree add ../repo-auth   -b claude/auth
git worktree add ../repo-fixes  -b codex/fixes
git worktree add ../repo-tests  -b aider/tests

# In each terminal, remember to:
cd ../repo-auth && claude -p "Refactor the auth module"   # prompt: lost
cd ../repo-fixes && codex                                 # prompt: lost
cd ../repo-tests && aider --message "Add edge case tests" # prompt: in chat history only

# Three days later, you want to discard the auth attempt:
cd ~/code/myrepo
git worktree remove ../repo-auth
git branch -D claude/auth
# Was there a stash? An untracked file? You don't remember.
```

Same outcome under ait, after `ait init`:

```bash
# Three agents, three terminals, three attempt worktrees provisioned
# automatically. Prompts and outputs captured.
claude -p "Refactor the auth module"
codex
aider --message "Add edge case tests"

# Three days later:
ait attempt list --intent "auth"
ait attempt show 01HXY...        # full record: prompt, files, exit, commits
ait attempt discard 01HXY...     # cleans worktree, branch, metadata
```

The first script is something you write once, lose, and rewrite. The
second script is the actual UX every day after `ait init`.

## When you don't need ait

Be honest about the cases ait does not earn its slot:

- **One agent, one branch, ad-hoc.** You spin up a single Claude
  Code session in a worktree once a week, throw away the branch
  after merge, and never go back to read what you did. Raw
  `git-worktree` is fine. The overhead of `ait init` is not paying
  for anything.
- **You don't run agents in parallel.** If your workflow is strictly
  sequential — one agent at a time, in your root checkout — even
  raw worktrees are overkill. ait does not change that.
- **You never want to look up old prompts or runs.** ait's biggest
  earned value is the queryable attempt history. If you treat AI
  coding as fully ephemeral and never audit it, that value
  evaporates.
- **Your repo is so small that cleanup is trivial.** A 200-file repo
  with five contributors does not generate enough attempt churn for
  the bookkeeping to matter.

If three of those four describe you, stop reading and stay on raw
`git-worktree`.

## When ait pays off

Conversely, ait earns its keep when:

- You run **two or more agents in parallel**, especially across
  Claude Code + Codex / Aider / Gemini / Cursor. The cross-agent
  memory layer alone repays the install.
- You have **stricter review discipline**: you want to look at a
  diff with full provenance (prompt, exit status, files) before it
  ever touches main. `ait attempt promote` is the explicit verb that
  forces that habit.
- You need **audit trail** for compliance, security review, or just
  a teammate asking "what prompt produced this diff three weeks
  ago?". The structured DSL beats `grep` over shell history every
  time.
- You want **local-only** provenance — `.ait/` lives next to
  `.git/`, the harness daemon is a Unix socket, no network, no
  telemetry, no SaaS sign-up.
- You hand off between agents and don't want each new run to pay
  for the same investigation in tokens.

## Migration: from naked worktree to ait

You don't need to give up the worktrees you already have. ait
co-exists.

```bash
# In your existing repo (with or without active worktrees):
pipx install ait-vcs
cd your-repo
ait init
direnv allow   # only if prompted

# Verify wrappers and hooks were installed for whichever agents are on $PATH.
ait adapter list
ait doctor

# From this point, just use your agents as usual. ait detects and wraps them.
claude ...
codex ...
aider ...
```

Existing manual worktrees keep working — ait does not touch them.
New runs through the wrapped agent CLIs become attempts. When you
are comfortable, you can stop creating worktrees by hand and let ait
provision them.

If anything looks wrong:

```bash
ait doctor --fix
ait repair
```

For the full setup walkthrough, see [Getting started](../getting-started.md).
For the verb cheatsheet, see the [command reference](../reference/commands.md).

## Next step

If raw `git-worktree` is already covering your one-agent, one-branch
weekly run — keep it. If you have ever lost a prompt, cleaned up
five worktrees by hand, or wanted a structured "show me every
Claude run that touched `auth.py` last month" query, run
`ait init` once and see what changes.

→ [Get started in 2 minutes](../getting-started.md)
