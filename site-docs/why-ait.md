---
title: Why ait — problems it solves for AI coding agents
description: >-
  Deep dive on the ten problems ait solves for teams running Claude Code,
  Codex, Aider, Gemini CLI, and Cursor — blast radius, provenance, failed
  attempts, repeated investigation, parallel safety, promotion ambiguity,
  cross-agent hand-off, local-first metadata, verification, and prompt
  search.
---

# Why ait

AI coding agents are fast. Git history, review discipline, and handoff
context across runs are not. `ait` closes that gap with a thin Git-native
layer. Here is the long form of every problem it solves and how.

## 1. Blast radius is unbounded

**Pain.** A single prompt to Claude Code or Codex can rewrite 30 files,
delete entire directories, or overwrite content you were editing by hand.
Undo means `git stash` plus `git reset --hard` and praying you do not also
trash your own in-progress work.

**ait.** Each run lands in an isolated Git worktree. Your root checkout
is never touched. A bad attempt is `ait attempt discard <id>` — zero
collateral damage.

## 2. The diff has no useful provenance

**Pain.** Three days later you cannot answer: which prompt produced this
diff? what context files were used? did it exit 0 or 130? Shell history
is not enough.

**ait.** Each attempt links intent, prompt, exit status, edited files,
captured output, and resulting commits as one queryable record. `ait
attempt show <id>` returns the full picture.

## 3. Failed runs pollute the working copy

**Pain.** The agent times out halfway, leaves stray commits, partial
edits, untracked files. You clean up by hand and still miss things, which
contaminate the next run.

**ait.** Failed attempts are kept inside their own worktree for review
or `discard`. Main stays clean from end to end.

## 4. You pay for the same investigation twice

**Pain.** Last week Claude already traced why the auth retry fails. This
week Codex starts the investigation from scratch. Same tokens, twice.

**ait.** Repo-local memory summarizes previous attempts, commits, agent
memory files (`CLAUDE.md`, `AGENTS.md`), and curated notes into a compact
context handoff (`AIT_CONTEXT_FILE`) for the next run.

## 5. Parallel agents stomp each other

**Pain.** You want Claude and Codex to try two approaches simultaneously,
then pick the better diff. Both fight over the working copy and corrupt
each other.

**ait.** Each attempt has its own worktree. Run N agents in parallel,
compare attempts side by side, promote the one you trust.

## 6. Promotion is ambiguous

**Pain.** The agent says "I have fixed it." Should you accept the diff
or not? Direct commits feel risky; reverting after the fact is friction.

**ait.** Promotion is an explicit verb: `ait attempt promote <id> --to
main`. Until you call it, the agent's work is a proposal, not a fact.

## 7. Cross-agent hand-off loses context

**Pain.** Claude ran three rounds, then Aider takes over and knows
nothing about the decisions, dead ends, or partial fixes from before.

**ait.** The memory layer auto-imports `CLAUDE.md`, `AGENTS.md`, and
prior attempts so the next agent — same or different — picks up with the
shared history.

## 8. Provenance tools want your code in their cloud

**Pain.** Most agent provenance / observability tools are SaaS. They
require uploading prompts, diffs, and source. Off the table for many
repos.

**ait.** Everything lives under `.ait/` next to `.git/`. The harness
daemon is local-only — Unix socket, no network. No telemetry, no SaaS,
no cross-machine sync. Suitable for security-sensitive repos.

## 9. Self-reported success is unverifiable

**Pain.** The agent claims "all tests pass." Sometimes it ran them.
Sometimes it cherry-picked one suite. Sometimes it never ran anything.

**ait.** The verifier decides `succeeded`, `promoted`, or `failed` based
on actual exit status, file changes, and commit results — not on what the
agent says about itself.

## 10. Finding old prompts means grepping shell history

**Pain.** "Where is that refactor prompt I wrote last month for the
query parser?" There is no good answer with raw shell history.

**ait.** Attempts, intents, and commits are queryable with a structured
DSL. Find by intent text, status, agent, time range, files touched, and
more.

## So what

If any of those ten problems hurt enough that you would tolerate one
extra command (`ait init`) before each repo, the rest of `ait` is just
your normal agent workflow with safety rails.

```bash
pipx install ait-vcs    # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...              # codex / aider / gemini / cursor — same idea
```

Then read [Getting started](getting-started.md) and pick your
[integration](integrations/claude-code.md).
