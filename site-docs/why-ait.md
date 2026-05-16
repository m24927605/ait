---
title: Why ait — problems it solves for AI coding agents
description: >-
  Deep dive on the ten problems ait solves for teams running Claude Code,
  Codex, Aider, Gemini CLI, and Cursor — blast radius, provenance, failed
  attempts, repeated investigation, parallel safety, apply ambiguity,
  agent-to-agent communication, local-first metadata, adversarial review, and
  prompt search.
---

# Why ait

AI coding agents are fast. Git history, review discipline, and shared context
across runs are not. `ait` closes that gap by making every agent run an
isolated, reviewable attempt before it reaches your working tree. It also gives
agents a repo-local way to communicate: prior attempts, accepted facts, notes,
review findings, and live memory files become the next agent's handoff context.

For runnable evidence, see [Pain-point demos](demos/pain-point-demos.md).

## 1. Blast radius is unbounded

**Pain.** A single prompt to Claude Code or Codex can rewrite 30 files,
delete entire directories, or overwrite content you were editing by hand.
Undo means `git stash` plus `git reset --hard` and praying you do not also
trash your own in-progress work.

**ait.** Each run lands in an isolated Git worktree. Your root checkout
is never touched. A bad attempt is `ait attempt discard <id>` — zero
collateral damage.

Runnable example: [`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius)

## 2. The diff has no useful provenance

**Pain.** Three days later you cannot answer: which prompt produced this
diff? what context files were used? did it exit 0 or 130? Shell history
is not enough.

**ait.** Each attempt links intent, prompt, exit status, edited files,
captured output, and resulting commits as one queryable record. `ait
attempt show <id>` returns the full picture.

Runnable example: [`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance)

## 3. Failed runs pollute the working copy

**Pain.** The agent times out halfway, leaves stray commits, partial
edits, untracked files. You clean up by hand and still miss things, which
contaminate the next run.

**ait.** Failed attempts are kept inside their own worktree for review
or `discard`. Main stays clean from end to end.

Runnable example: [`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation)

## 4. You pay for the same investigation twice

**Pain.** Last week Claude already traced why the auth retry fails. This
week Codex starts the investigation from scratch. Same tokens, twice.

**ait.** Repo-local memory combines previous attempts, commits, curated notes,
accepted facts, review findings, and live agent memory files (`CLAUDE.md`,
`AGENTS.md`, `.claude/memory.md`, `.codex/memory.md`, `.cursor/rules`) into a
compact context handoff (`AIT_CONTEXT_FILE`) for the next run.

Runnable example: [`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse)

## 5. Parallel agents stomp each other

**Pain.** You want Claude and Codex to try two approaches simultaneously,
then pick the better diff. Both fight over the working copy and corrupt
each other.

**ait.** Each attempt has its own worktree. Run N agents in parallel,
compare attempts side by side, and apply the one you trust.

Runnable example: [`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents)

## 6. Apply is ambiguous

**Pain.** The agent says "I have fixed it." Should you accept the diff
or not? Direct commits feel risky; reverting after the fact is friction.

**ait.** Apply is an explicit step: `ait apply latest` or `ait apply
<attempt-id> --mode current`. Until you call it, the agent's work is a
proposal, not a fact.

Runnable example: [`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion)

## 7. Agents cannot talk to each other

**Pain.** Claude ran three rounds, then Aider takes over and knows nothing
about the decisions, dead ends, or partial fixes from before. Codex repeats the
same investigation because the useful context lives in another chat window.

**ait.** The memory layer reads AIT-owned attempt history, accepted facts,
notes, review findings, `CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`,
`.codex/memory.md`, and Cursor rules live at handoff time. The next agent —
same or different — receives `AIT_CONTEXT_FILE` with the policy-allowed context
instead of starting from a blank private chat.

Runnable example: [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff)

## 8. Provenance tools want your code in their cloud

**Pain.** Most agent provenance / observability tools are SaaS. They
require uploading prompts, diffs, and source. Off the table for many
repos.

**ait.** Everything lives under `.ait/` next to `.git/`. The harness
daemon is local-only — Unix socket, no network. No telemetry, no SaaS,
no cross-machine sync. Suitable for security-sensitive repos.

Runnable example: [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance)

## 9. Plausible agent output still needs challenge

**Pain.** An agent can produce a convincing code change with weak evidence:
no tests, incomplete checks, or a confident explanation that hides a risky edge
case.

**ait.** AIT can preserve the original attempt and record a separate
adversarial review. The review target is an AIT attempt, not a loose diff, and
the result is queryable evidence. With review gating enabled, a blocked review
can hold `ait apply`.

```bash
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
ait apply <attempt-id> --mode current
```

Runnable examples: [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence), [`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer)

## 10. Finding old prompts means grepping shell history

**Pain.** "Where is that refactor prompt I wrote last month for the
query parser?" There is no good answer with raw shell history.

**ait.** Attempts, intents, and commits are queryable with a structured
DSL. Find by intent text, status, agent, time range, files touched, and
more.

Runnable example: [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search)

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
