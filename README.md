<div align="center">

# ait

### One agent writes. Another reviews. The repo remembers both.

**Every agent run is an attempt under `.ait/` — prompt, diff, review findings, prior decisions, queryable from the CLI.**

<sub>[English](README.md) · [繁體中文](README.zh-TW.md)</sub>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

---

<p align="center">
  <img src="docs/assets/hero-cross-agent-handoff.gif" alt="Claude writes a decision into AGENTS.md; Codex copies the exact proof string into handoff-proof.txt without re-reading AGENTS.md — proving the handoff went through AIT" width="800">
</p>
<p align="center"><sub>Hero demo: <a href="examples/pain-point-demos/07-cross-agent-handoff/"><code>07-cross-agent-handoff</code></a> — Claude finishes, Codex inherits the prior decisions.</sub></p>

`ait` wraps the agent CLI you already run. Every run becomes a reviewable attempt under `.ait/`. Three pillars: the next agent receives the prior agent's decisions, the implementer doesn't review its own work, and prior attempts stay queryable from the CLI.

```bash
pipx install ait-vcs      # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

Requires Python 3.14+.

The package is `ait-vcs` on PyPI and npm. The installed command is `ait`.

---

## Three pain points ait defuses

### 1. Every agent starts from zero on the same repo

**Scenario.** Yesterday Claude chased a billing-retry 429 bug. This morning Codex opens the same repo and re-investigates from scratch. Zero handoff.

**ait defuses it.** Every wrapped run lands as an attempt under `.ait/`. The next run — `ait run --adapter codex ...` (`src/ait/cli/run.py`) — receives the prior agent's decisions through a compact context file assembled from prior attempts, accepted facts, and notes (`src/ait/context_manifest.py`). Handoff is asynchronous and evidence-based: prompt, diff, findings, decisions. Trace handoffs with `ait query --on attempt 'agent.agent_id="codex:main"'`.

**Proof.** [`examples/pain-point-demos/07-cross-agent-handoff/`](examples/pain-point-demos/07-cross-agent-handoff/) — Codex inherits the prior decisions.

### 2. The agent that wrote the code is the only one who reviewed it

**Scenario.** Codex finishes, says "all tests pass." Implementer and reviewer are the same model, same chat, same prompt.

**ait defuses it.** `ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code` (`src/ait/cli/review.py`) runs a different agent against the attempt's diff. The reviewer is a different agent, with a different prompt. It can block apply. Findings are queryable rows: `ait query --on attempt 'review.status="blocked"'`. High-severity findings hold `ait apply`.

**Proof.** [`examples/pain-point-demos/09-1-codex-reviewer/`](examples/pain-point-demos/09-1-codex-reviewer/) — Codex reviews Claude's attempt and records a blocking finding before apply.

### 3. Last Tuesday's decision lives in a closed chat tab

**Scenario.** Three weeks ago you capped the retry budget at three. The chat tab is closed. The new agent proposes five.

**ait defuses it.** `.ait/` keeps every attempt — prompt, intent, output, files, commits, findings — alongside live `CLAUDE.md` / `AGENTS.md` / `.claude/memory.md` / `.codex/memory.md` / `.cursor/rules`. `ait memory recall "retry budget"` (`src/ait/memory/recall.py`) searches prior attempts, accepted facts, and notes — you decide what's relevant. Local, single-machine, shared across every wrapped agent.

**Proof.** [`examples/pain-point-demos/04-memory-reuse/`](examples/pain-point-demos/04-memory-reuse/) — a prior decision reaches the next agent via `ait memory recall`.

---

## What ait is, and is not

ait wraps the agent CLI you already use. It is not a Cursor competitor, not an Aider replacement, not an IDE plugin.

| Tool | What it does | What ait adds |
| --- | --- | --- |
| **Aider** | In-process edit + auto-commit loop, single model, one chat per run. | A separate reviewer agent against the same attempt (`ait review attempt --mode adversarial`, `src/ait/cli/review.py`). Aider commits land *inside* an ait attempt; apply is still explicit. Cross-agent handoff through the next run's context file (`src/ait/context_manifest.py`). |
| **Cursor** | IDE-integrated agent, in-editor diff review, agent-mode parallel tasks. | CLI-first attempt ledger across non-Cursor agents (`ait attempt list`, `src/ait/cli/attempt.py`). No SaaS round-trip; `.ait/` is local, daemon on Unix socket only (`src/ait/daemon_transport.py`). |
| **Cline** | VSCode extension wrapping Claude/OpenAI for in-editor agentic edits. | Wraps the agent CLI you already use, no editor required (`ait run --adapter claude-code`, `src/ait/cli/run.py`). Findings and prompts are queryable rows (`ait query`, `src/ait/query/`). |
| **Continue.dev** | IDE autocomplete and chat with model routing and rule files. | Reviewable attempts, not autocomplete (`ait apply` / `ait recover`). Review gate (`ait review finding list --severity high`). |

What ait does **not** do:

- No IDE plugin. CLI only.
- No autocomplete. Attempt-grained, not keystroke-grained.
- No cross-machine sync. `.ait/` is single-repo, single-machine.
- No published benchmark proving the reviewer catches bugs the implementer missed. A dogfood report exists ([`docs/aitbench-dogfood-report.md`](docs/aitbench-dogfood-report.md)); a quality claim does not.

---

## Daily commands

```bash
ait status                          # see what ran in this repo
ait status claude-code              # confirm this shell is wrapped, not bypassing
ait attempt list                    # list recent attempts
ait attempt show <attempt-id>       # prompt, diff, files, commits, review
ait apply latest                    # apply when you are ready
ait recover latest                  # keep failed work reachable
ait memory recall "retry budget"    # search prior attempts, facts, notes
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait query --on attempt 'review.status="blocked"'
```

Until `ait apply`, the root checkout never moves. Failed or risky attempts stay recoverable instead of becoming working-copy debris.

---

## How it works

```text
your prompt
    |
    v
agent CLI wrapped by ait
    |
    v
isolated Git worktree
    |
    v
attempt: prompt, diff, files, commits, findings
    |
    v
review, apply, recover, or query
```

The wrapped process inherits `AIT_INTENT_ID`, `AIT_ATTEMPT_ID`, `AIT_WORKSPACE_REF`, and a compact context file pointing at prior attempts, accepted facts, notes, commits, and live `CLAUDE.md` / `AGENTS.md` / `.claude/memory.md` / `.codex/memory.md` / `.cursor/rules`. The context manifest (`src/ait/context_manifest.py`) separates trusted baseline, advisory, and excluded memory.

---

## Status

**Alpha.**

ait is alpha quality, dogfooded daily on real repos, single-machine metadata. No cross-machine sync. No SaaS dashboard. No telemetry. The daily console is read-only; mutation still goes through the CLI. Metadata export/import is dry-run planning only.

`.ait/policy.json` is validated on every apply, review, console action preflight, and context trust filter pass.

Intended for local power users and infra-minded engineers comfortable with Git workflows.

---

## Install

```bash
pipx install ait-vcs            # recommended
npm install -g ait-vcs          # alternative
python3.14 -m venv .venv && .venv/bin/pip install ait-vcs   # venv
pipx install "git+https://github.com/m24927605/ait.git@v1.0.4"   # pinned release
```

Upgrade:

```bash
ait upgrade
ait upgrade --dry-run
```

Requirements: Python 3.14+, Git, SQLite (stdlib), Node.js 18+ only for the npm wrapper.

---

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install pytest
.venv/bin/pytest -q
```

Before a release, the version in `pyproject.toml`, the Git tag, and this README should match.

---

## Links

- [Documentation site](https://m24927605.github.io/ait/) — English and 繁體中文
- [Getting started](https://m24927605.github.io/ait/getting-started/)
- [Command reference](https://m24927605.github.io/ait/reference/commands/)
- [Adversarial code review](https://m24927605.github.io/ait/reference/adversarial-code-review/)
- [CHANGELOG](CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
- [PyPI](https://pypi.org/project/ait-vcs/) · [npm](https://www.npmjs.com/package/ait-vcs)

MIT. No telemetry. Nothing leaves your machine.
