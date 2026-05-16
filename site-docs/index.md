---
title: ait — Local control plane for AI coding agents
description: >-
  ait is a local control plane and Git-native attempt ledger for Claude Code,
  Codex, Aider, Gemini CLI, and Cursor: repo-local memory, cross-agent handoff,
  adversarial review, and explicit apply/recover. Open-source,
  dependency-free, no SaaS, no telemetry.
---

# ait

**Local control plane for AI coding agents. Git-native attempt ledger,
repo-local memory, cross-agent handoff, and review gate.**

`ait` wraps the agent CLIs you already use — Claude Code, Codex, Aider,
Gemini CLI, Cursor — and turns each run into a **reviewable attempt**.
It gives agents a shared repo-local memory, long-term attempt history, an
inspectable handoff channel, and adversarial review before code lands. The
agent still edits an isolated Git worktree, `ait` records what happened, and
your main checkout stays untouched until you apply the result.

Put it in this category: **local control plane for AI coding agents**. AIT is
not only a worktree manager, not a generic memory layer, not a review bot, and
not a SaaS provenance dashboard. Those surfaces are pieces of one local
attempt ledger: agents work in attempts, memory is derived from evidence, review
findings can gate apply, and Git remains the source of truth.
See the category boundary page for a direct comparison with
[GUI-first agent managers, worktree managers, memory layers, review bots, and
provenance tools](compare/agent-managers-memory-review-vs-ait.md).

```text
Claude investigates -> AIT records attempt + accepted context
Codex implements with AIT_CONTEXT_FILE
Reviewer agent challenges the result
You run ait apply only when the evidence is good
```

The four features to notice first:

- **Shared repo memory.** Claude Code, Codex, Aider, Gemini, Cursor, and shell
  agents can read the same policy-allowed project context.
- **Long-term memory.** Useful attempts, commits, notes, accepted facts, and
  findings survive across terminals, sessions, and weeks.
- **Agent-to-agent communication.** One agent's investigation, decision, failed
  path, or review finding can reach the next agent through `AIT_CONTEXT_FILE`.
- **Adversarial review.** A separate reviewer agent can challenge an attempt and
  leave evidence before you decide whether to apply.

```bash
pipx install ait-vcs    # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

The package is named `ait-vcs` on PyPI and npm. The installed command is `ait`.

![AIT Work Graph showing attempts, evidence, memory, hot files, and query filters](assets/ait-work-graph.png)

_Static HTML from `ait graph --html`: attempts, evidence, memory, hot files, and query filters in one local report._

## Key capabilities

| Capability | What it means |
| --- | --- |
| Git-native attempt ledger | Each agent run becomes a queryable attempt linked to intent, prompt, context, output, files, commits, memory, and review evidence. |
| Live federated memory | Claude Code, Codex, Aider, Gemini, Cursor, and shell agents can reuse the same live repo memory: AIT-owned history plus current `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, and Cursor rules. |
| Long-term repo memory | Attempts, commits, notes, accepted facts, prior findings, and explicit adopted memory can survive across sessions. |
| Agent-to-agent communication | One agent can record an investigation, decision, failed path, or review finding, and another agent can receive it later through `AIT_CONTEXT_FILE`. |
| Adversarial review | A separate reviewer agent can challenge an attempt, record findings, and hold apply on high-risk results. |
| Attempt-first workflow | Wrap the agent CLIs you already use and turn each run into an isolated attempt before anything touches the root checkout. |
| Attempt provenance | Prompt, intent, adapter, output, changed files, commits, trace references, status, and outcome stay linked. |
| Worktree isolation | Every run gets an internal isolated Git worktree, so failed or risky attempts do not pollute your workspace. |
| Parallel agent attempts | Multiple agents can try different approaches at the same time without racing inside the same checkout. |
| Explicit apply/recover flow | Agent output stays a proposal until apply; held or failed work remains recoverable. |
| Wrapper bypass detection | `ait status <adapter>` shows whether this shell will enter AIT or silently call the real agent binary. |
| Local-first metadata | Metadata lives under `.ait/`; no SaaS dashboard, no telemetry, no required code upload. |
| Queryable history | Attempts, intents, files, agents, statuses, review results, and old prompts can be found with AIT commands. |

## Problems ait solves

| Problem with agent coding today | What ait adds | Runnable example |
| --- | --- | --- |
| A bad prompt rewrites half your repo before you notice | Each run lands in an isolated Git worktree — your root checkout never moves | [`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius) |
| The diff has no useful provenance — which prompt produced it? | Attempts link intent, command output, files, and commits in one record | [`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance) |
| Failed or partial runs leave your working copy half-broken | Bad attempts stay recoverable; `ait recover latest` shows what AIT kept | [`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation) |
| The next agent repeats investigation you already paid tokens for | Shared repo-local memory feeds prior attempts, commits, notes, and accepted facts to the next run | [`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse) |
| Two agents on the same task stomp each other | Each attempt has its own worktree — run N agents in parallel | [`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents) |
| Did the agent really fix it, or just claim it did? | Explicit `ait apply latest` keeps speculative changes out of main until you decide | [`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion) |
| Cross-agent hand-offs lose every previous decision | Live repo memory combines current agent memory files with prior attempts, notes, and accepted decisions | [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) |
| Provenance tooling wants to ship your code to a SaaS | Metadata stays in `.ait/` next to `.git/` — harness daemon is local-only (Unix socket, no network), no telemetry | [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance) |
| The implementing agent rubber-stamps its own answer | Adversarial review lets a separate reviewer agent challenge the attempt; high-risk findings can block apply | [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence), [`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) |
| "Where's that prompt I wrote last month?" → grep shell history | Query attempts, intents, and commits with a structured DSL | [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search) |

See the full deep-dive on each problem in [Why ait](why-ait.md).
For runnable evidence for each point, use the
[Pain-point demos](demos/pain-point-demos.md).

`ait` is **not** another agent. It is the local attempt workflow and control
plane around the agents you already trust.

## How agents communicate

AIT communication is asynchronous and inspectable. Every wrapped run creates an
attempt with prompt, output, changed files, commits, status, and memory
candidates. Later runs receive `AIT_CONTEXT_FILE`, a compact handoff assembled
from policy-allowed attempts, accepted facts, notes, commits, review findings,
and live memory files such as `CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`,
`.codex/memory.md`, and `.cursor/rules`.

The result is not a hidden chat transcript, an external vector database, or a
`CLAUDE.md` generator. It is attempt-derived, evidence-backed repo memory you
can inspect, search, review, and keep or discard with Git-aware context.

## Supported agents

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [Any other shell agent](integrations/shell.md)

## Review and memory boundaries

`ait review attempt --mode light` is a deterministic risk scan. It checks
changed-file count, sensitive paths, dependency or lockfile changes, generated
or binary files, and missing test evidence. It does not call an LLM and does
not produce line-by-line findings.

Use `adversarial` mode when you want a real reviewer adapter and structured
findings:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

The built-in `claude-code` reviewer invokes the local `claude -p` CLI and
removes `ANTHROPIC_API_KEY` from that child process environment. AIT does not
silently fall back to provider API credits; Claude Code must be installed and
locally authenticated on your machine.

Repo-local memory is a live federated view inside one repository. AIT records
attempts, commits, notes, accepted memory facts, prior findings, and review
findings under `.ait/`, then reads current repo-local agent memory files such
as `CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`, `.codex/memory.md`, and
`.cursor/rules` live at recall/run/review time. This is inspectable project
memory, not hidden chat-window memory.

When you introduce AIT to an existing repository, start with
`ait memory sources` or `ait memory recall`. Both are zero-touch reads by
default: no `.ait/` creation and no source mutation. `ait memory backfill
--dry-run` remains a zero-write preview. Use `backfill --import` only when you
explicitly want AIT to add advisory memory under `.ait/`.

See [Adversarial code review](reference/adversarial-code-review.md) for details
on reviewer adapters, findings, reports, and review-gated apply.

## Status

`ait` is alpha quality. It is intended for local dogfooding and early users
who are comfortable with Git workflows, especially power users and
infra-minded engineers. Metadata is local to one repository under `.ait/`; it
is not synchronized across machines.

The visual model is becoming usable: `ait graph --html` remains a static local
report, and `ait console --read-only` writes or serves a loopback-only daily
console over the same attempt graph, evidence, memory, hot files, and review
results. The console is read-only today; apply/recover/discard still go through
the existing CLI/domain paths. A CLI action dry-run layer now records
apply/recover/discard preflight and append-only journal entries, but browser
mutation UI and execution are not enabled.

Team-readiness hardening is local-only: `.ait/policy.json` validation is
fail-closed and is now consumed by apply, review, console action preflight, and
context trust filtering. Metadata export/import currently emits dry-run plans.
There is still no cross-machine sync, SaaS dashboard, telemetry, automatic
push, or automatic merge.

## Product direction

| Current constraint | Solution path |
| --- | --- |
| Category can sound like several tools at once | Anchor ait as a local control plane and Git-native attempt ledger; memory, review, provenance, and apply/recover are parts of that ledger. |
| CLI-first experience loses some users to visual agent managers | Keep the console read-only while hardening apply/recover/discard dry-run preflight and journaling before browser mutation UI. |
| Alpha quality limits broad team adoption | Focus first on local power users and infra-minded engineers; expose dry-run metadata export/import and fail-closed policy validation before any broader sync story. |
| "Memory" can be mistaken for prompt stuffing | Keep memory attempt-derived, evidence-backed, inspectable, and tied to Git state. |
| Review gate impact needs proof | The 10-case benchmark fixture and repaired Claude/Codex dogfood artifacts now exist. Keep publishing honest repeated runs until recall, false positives, latency, token cost, and the deterministic-vs-LLM tradeoff are stable enough for a quality claim. |

## Project links

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI package](https://pypi.org/project/ait-vcs/)
- [npm package](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
