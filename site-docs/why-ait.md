---
title: Why ait — three power-user pains, and what ait does not do
description: >-
  Three pains AIT defuses for engineers running Claude Code, Codex, Aider,
  Gemini CLI, and Cursor — and four things AIT explicitly does not promise.
---

# Why ait

Three pains hit every engineer running multiple agent CLIs against the same
repo. AIT defuses them with attempts, a separate reviewer, and queryable
repo memory. Each pain below has a scenario, the AIT move, and a runnable
demo.

For the full runnable evidence catalog, see
[Pain-point demos](demos/pain-point-demos.md).

## 1. Every agent starts from zero on the same repo

**Scenario.** Yesterday Claude chased a billing-retry 429 bug across three
files. This morning Codex opens the same repo and re-investigates from
scratch. Zero handoff. You pay the same tokens twice and lose the dead-end
notes from yesterday.

**What AIT does.** Every wrapped run lands as an attempt under `.ait/`. The
next run — Codex, Aider, Gemini, Cursor, anything wrapped by `ait run
--adapter <name>` (`src/ait/cli/run.py`) — receives a handoff file assembled
from prior attempts and notes (`src/ait/context_manifest.py`). The handoff is
asynchronous and one-direction: prompt, diff, findings, decisions. Trace
handoffs with:

```bash
ait query --on attempt 'agent.agent_id="codex:main"'
```

**Proof.** [`examples/pain-point-demos/07-cross-agent-handoff/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) — Codex receives the prior agent's decisions through the handoff file.

## 2. The agent that wrote the code is the only one who reviewed it

**Scenario.** Codex finishes, says "all tests pass," shows a green diff. The
implementer and the reviewer are the same model, same chat, same prompt.
Anything the model missed at write-time, it misses at read-time.

**What AIT does.** AIT runs a separate reviewer agent with a different
prompt against the attempt's diff. The reviewer cannot see the
implementer's chat. The implementer doesn't review its own work.

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

Findings are queryable rows (`ait query --on attempt 'review.status="blocked"'`).
High-severity findings hold `ait apply` (`src/ait/cli/review.py`).

**Proof.** [`examples/pain-point-demos/09-1-codex-reviewer/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) — a separate reviewer agent records a blocking finding before apply.

## 3. Last Tuesday's decision lives in a closed chat tab

**Scenario.** Three weeks ago you capped the retry budget at three after a
long debate with Claude. The chat tab is closed. This morning a new agent
opens the same file and proposes five.

**What AIT does.** `.ait/` keeps every attempt — prompt, intent, output,
files, commits, findings — alongside live `CLAUDE.md`, `AGENTS.md`,
`.claude/memory.md`, `.codex/memory.md`, and `.cursor/rules`. Recall is a CLI
query (`src/ait/memory/recall.py`):

```bash
ait memory recall "retry budget"
```

`ait memory recall <query>` searches prior attempts, accepted facts, and
notes — you decide what's relevant. Local, single-machine, shared across
every wrapped agent.

**Proof.** [`examples/pain-point-demos/04-memory-reuse/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse) — the prior decision reaches the next agent via `ait memory recall`.

## When NOT to use AIT

These are honest boundaries, not warnings buried in a footer.

- **AIT does not promise the reviewer catches every bug.** It promises the
  reviewer is a different agent with a different prompt. There is no
  published recall, precision, false-positive, or latency benchmark against
  a real-world bug corpus. The dogfood report
  ([`docs/aitbench-dogfood-report.md`](https://github.com/m24927605/ait/blob/main/docs/aitbench-dogfood-report.md))
  is observational evidence, not a universal quality proof.

- **AIT is not a multi-agent team.** Handoff is asynchronous and
  one-direction. The next agent receives the prior agent's decisions
  through a handoff file. There is no live coordination, no shared chat,
  no agents working at the same time inside one task.

- **AIT is alpha, not production-ready.** `.ait/` lives on one machine. No
  cross-machine sync, no SaaS dashboard, no telemetry. Metadata
  export/import emits dry-run plans only. The console is read-only;
  mutation goes through CLI.

- **Memory recall does not surface the right context every time.**
  `src/ait/memory/recall.py` uses BM25-style ranking over prior attempts,
  accepted facts, and notes. There is no published precision/recall
  benchmark. You decide what's relevant.

If those bound the value to zero for your situation, AIT is not the right
tool. If you can live with them, the three pains above are real and
recurring.

## Differentiation, vs. tools you already use

| Tool | What it does | What AIT adds |
| --- | --- | --- |
| **Aider** | In-process edit + auto-commit loop, single model, one chat per run. | A different reviewer agent against the same attempt (`ait review attempt --mode adversarial`, `src/ait/cli/review.py`). Aider commits land inside an attempt; apply is still explicit. The next agent receives the prior agent's decisions via the handoff file (`src/ait/context_manifest.py`). |
| **Cursor** | IDE-integrated agent, in-editor diff review, agent-mode parallel tasks. | CLI-first attempt ledger across non-Cursor agents (`ait attempt list`, `src/ait/cli/attempt.py`). Nothing leaves your machine; the daemon is a local Unix socket (`src/ait/daemon_transport.py`). |
| **Cline** | VSCode extension wrapping Claude/OpenAI for in-editor agentic edits. | Wraps the agent CLI you already use, no editor required (`ait run --adapter claude-code`, `src/ait/cli/run.py`). Prompts and findings are queryable rows (`ait query`, `src/ait/query/`). |
| **Continue.dev** | IDE autocomplete and chat with model routing and rule files. | Reviewable attempts, not autocomplete. Apply is explicit (`ait apply` / `ait recover`). A review gate can block apply (`ait review finding list --severity high`). |

Ready to try it? Read [Getting started](getting-started.md).
