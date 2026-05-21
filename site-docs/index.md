---
title: ait — One agent writes. Another reviews. The repo remembers both.
description: >-
  ait wraps Claude Code, Codex, Aider, Gemini CLI, and Cursor so one agent
  hands work to the next, a different agent reviews the diff, and prior
  attempts stay queryable from the CLI.
---

# One agent writes. Another reviews. The repo remembers both.

Every agent run is an attempt under `.ait/` — prompt, diff, review findings,
prior decisions, queryable from the CLI.

`ait` wraps the agent CLIs you already use. The next agent receives the prior
agent's decisions through a handoff file. A separate reviewer agent runs
against the attempt's diff before you apply. Memory is `.ait/` plus live
`CLAUDE.md` / `AGENTS.md` files, searchable from one CLI.

```bash
pipx install ait-vcs      # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

Requires Python 3.14+. On older Python, use
`pipx install --python python3.14 ait-vcs`.

The package is `ait-vcs` on PyPI and npm. The command is `ait`.

## What AIT adds, vs. the tools you already use

| Tool | What it does | What AIT adds |
| --- | --- | --- |
| **Aider** | In-process edit + auto-commit loop, single model, one chat per run. | A different reviewer agent against the same attempt (`ait review attempt --mode adversarial`, `src/ait/cli/review.py`). Aider commits land inside an attempt; apply is still explicit. The next agent receives the prior agent's decisions via the handoff file (`src/ait/context_manifest.py`). |
| **Cursor** | IDE-integrated agent, in-editor diff review, agent-mode parallel tasks. | CLI-first attempt ledger across non-Cursor agents (`ait attempt list`, `src/ait/cli/attempt.py`). Nothing leaves your machine; the daemon is a local Unix socket (`src/ait/daemon_transport.py`). |
| **Cline** | VSCode extension wrapping Claude/OpenAI for in-editor agentic edits. | Wraps the agent CLI you already use, no editor required (`ait run --adapter claude-code`, `src/ait/cli/run.py`). Prompts and findings are queryable rows (`ait query`, `src/ait/query/`). |
| **Continue.dev** | IDE autocomplete and chat with model routing and rule files. | Reviewable attempts, not autocomplete. Apply is explicit (`ait apply` / `ait recover`). A review gate can block apply (`ait review finding list --severity high`). |
| **When NOT to use AIT** | You want an IDE plugin, autocomplete, cross-machine sync, or a hardened production tool. | AIT is CLI-only, attempt-grained, single-machine, and alpha. The console is read-only; `.ait/` does not sync across machines. |

## The three pillars

### One agent hands work to the next

Yesterday Claude chased a billing-retry 429 bug. Today Codex opens the same
repo. Without AIT, Codex starts from zero. With AIT, the next run — Claude,
Codex, Aider, Gemini, Cursor, anything wrapped by `ait run --adapter <name>`
(`src/ait/cli/run.py`) — receives a handoff file assembled from prior
attempts and notes. Handoff is asynchronous, one direction, evidence-based:
prompt, diff, findings, decisions.

Proof: [`examples/pain-point-demos/07-cross-agent-handoff/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff)

### A different agent reviews the diff

Codex finishes and says "all tests pass." The implementer and the reviewer
are the same model in the same chat. AIT runs the reviewer as a separate
agent with a different prompt:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

The reviewer cannot see the implementer's chat. Findings are queryable rows
(`ait query --on attempt 'review.status="blocked"'`). High-severity findings
hold `ait apply`.

Proof: [`examples/pain-point-demos/09-1-codex-reviewer/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer)

### The repo remembers prior decisions

Three weeks ago you capped the retry budget at three. The chat tab is closed.
A new agent proposes five. `.ait/` keeps every attempt — prompt, intent,
output, files, commits, findings — alongside live `CLAUDE.md`, `AGENTS.md`,
`.claude/memory.md`, `.codex/memory.md`, and `.cursor/rules`. Recall is a CLI
query:

```bash
ait memory recall "retry budget"
```

`src/ait/memory/recall.py` searches prior attempts, accepted facts, and notes
— you decide what's relevant.

Proof: [`examples/pain-point-demos/04-memory-reuse/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse)

## After a week of use

![AIT Work Graph showing attempts, evidence, memory, hot files, and query filters](assets/ait-work-graph.png)

_Static HTML from `ait graph --html`: attempts, evidence, memory, hot files,
and query filters in one local report._

## Status

Alpha. Dogfooded daily on real repos. Metadata is single-machine, under
`.ait/`. No cross-machine sync, no SaaS, no telemetry. See
[Why ait](why-ait.md) for the "When NOT to use AIT" boundary.

## Project links

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI package](https://pypi.org/project/ait-vcs/)
- [npm package](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
