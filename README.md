# ait

**ait is a local attempt ledger for AI coding agents.**

It records every AI coding run so another agent can review, continue, or
recover it later.

<p>
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

You keep using Claude Code, Codex, Aider, Gemini CLI, Cursor CLI, or another
agent the way you normally do. `ait` wraps that run, stores the prompt, diff,
review, and decisions as a repo-local attempt under `.ait/`, then gives the
next agent a usable handoff. You can ask a different agent to review the
attempt before you apply it. Until you explicitly run `ait apply`, a wrapped
agent's result stays out of the root checkout.

Package name: `ait-vcs`. Installed command: `ait`.

## Why this exists

AI coding agents are good at making changes, but the surrounding workflow is
still fragile:

- The next agent often starts from zero because the last agent's context lived
  in a closed chat.
- The agent that wrote the code is often the only one that "reviewed" it.
- Failed or interrupted runs can leave confusing working-copy debris.
- Useful decisions are hard to find after the run that produced them.

`ait` treats each run as an attempt: a proposal with provenance, review state,
memory, and an explicit apply step.

## Who needs it

`ait` is for engineers who already use AI coding agents on real repositories
and want a local record of what happened. It is especially useful when you:

- Switch between Claude Code, Codex, Aider, Gemini CLI, Cursor CLI, or other
  agent CLIs.
- Want a second agent to review a risky change before it lands.
- Need to recover useful work from failed or interrupted runs.
- Want old prompts, decisions, and findings to be searchable from the repo.

## 30-second quickstart

Try the workflow without real API keys or an existing repo:

```bash
pipx install ait-vcs
ait demo
```

`ait demo` creates a temporary repo, runs a scripted multi-agent walkthrough,
records attempts in a real local SQLite ledger, and shows a review gate blocking
a risky change. Clean it up with:

```bash
ait demo --clean
```

Use it in a real repo:

```bash
cd your-repo
ait init
ait status --all # optional: confirm agent commands resolve through ait
claude ...        # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

Requires Python 3.14+ and Git. If your default Python is older:

```bash
pipx install --python python3.14 ait-vcs
```

## How it feels to use

1. Initialize a repo once with `ait init`.
2. Confirm the wrapper when you care: `ait status claude-code` or
   `ait status --all`.
3. Run your agent normally: `claude ...`, `codex ...`, `aider ...`, and so on.
4. `ait` records the run as an isolated attempt under `.ait/`.
5. Inspect it with `ait status` or `ait attempt show <attempt-id>`.
6. Optionally run a separate reviewer agent.
7. Apply, recover, resume, or discard the attempt.

The important behavior: the root checkout should not be changed by a wrapped
run before `ait apply`. The agent's work is a proposal until you promote it.

## Core concepts

**Attempt**

One agent run captured by `ait`: prompt, intent, exit status, changed files,
diff, commits, traces, and review state.

```bash
ait attempt list
ait attempt show <attempt-id>
```

**Repo-local ledger**

`.ait/` lives next to `.git/`. It is local metadata for this repository: no
SaaS, no telemetry, no automatic sync. Nothing in `.ait/` leaves your machine
unless you copy, commit, export, or upload it yourself. The agent CLI you run
still follows its own provider and network behavior.

**Explicit apply**

Wrapped agent runs land in an isolated workspace. `ait apply latest` is the
moment you decide the attempt should affect the root checkout.

```bash
ait apply latest
ait recover latest
ait resume latest
```

**Cross-agent handoff**

The next wrapped agent can receive prior attempts, accepted facts, notes, and
live repo memory files such as `CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`,
`.codex/memory.md`, and `.cursor/rules`.

**Adversarial review**

Use one agent to implement and another to challenge the result before apply.
This does not prove the code is correct; it gives you a separate review pass
with recorded findings.

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code
```

**Memory recall**

Search prior attempts and repo memory when a decision matters again:

```bash
ait memory recall "retry budget"
```

## Common workflows

**Record a normal agent run**

```bash
ait init
claude -p "Refactor the auth retry logic"
ait status
ait attempt list
ait attempt show <attempt-id>
```

**Review with a different agent**

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter codex

ait review finding list --severity high
```

**Continue after an interrupted or held run**

```bash
ait recover latest
ait resume latest
```

**Find an old decision**

```bash
ait memory recall "why retry budget is three"
ait query --on attempt 'title~"retry"'
```

**Compare multiple attempts**

```bash
ait attempt list
ait attempt show <attempt-id>
ait graph --html
```

## How this differs from Cursor, Aider, Claude Code, Codex, and Cline

`ait` is not another coding agent. It is the local workflow layer around the
agents you already use.

| Tool | Main job | What `ait` adds |
| --- | --- | --- |
| Cursor / Cline | IDE-native agent experience. | A CLI-first attempt ledger that also works outside the editor and across multiple agent CLIs. |
| Claude Code / Codex / Gemini CLI | A coding agent that reads, edits, and runs commands. | Isolation, provenance, cross-agent handoff, review records, memory recall, and explicit apply/recover. |
| Aider | Pair-programming loop with model-driven edits and commits. | A repo-local attempt boundary around those edits, plus optional review by a different agent before apply. |
| Git worktrees alone | Isolated directories for parallel work. | Prompt and trace capture, attempt metadata, review findings, memory handoff, and daily commands for apply/recover. |

The short version: your agent writes code; `ait` remembers what happened and
keeps the result reviewable before it lands.

## When not to use ait

Do not use `ait` if you need:

- An IDE plugin or autocomplete engine.
- A hosted dashboard, team sync service, or cross-machine ledger.
- A production-hardened system with a stable long-term storage contract.
- Proof that an AI reviewer will find all defects.
- A tool that replaces Claude Code, Codex, Aider, Cursor, Cline, or Git.

`ait` is most useful for engineers who already use agent CLIs and want local
provenance, safer apply, cross-agent handoff, and a second-agent review pass.

## Install

Recommended:

```bash
pipx install ait-vcs
ait --version
```

npm wrapper:

```bash
npm install -g ait-vcs
ait --version
```

Project virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --version
```

Pinned GitHub release:

```bash
pipx install "git+https://github.com/m24927605/ait.git@v1.4.3"
```

Upgrade:

```bash
ait upgrade
ait upgrade --dry-run
```

Requirements: Python 3.14+, Git, SQLite from the Python standard library.
The npm package requires Node.js 18+ and installs the Python package behind the
`ait` command.

## Current status and limitations

`ait` is alpha software.

- Local-first: metadata lives under `.ait/` in one repository on one machine.
- No telemetry, no SaaS dashboard, no automatic push, no automatic merge.
- Browser/HTML reporting is local; mutation still goes through CLI commands.
- Metadata export/import is currently a dry-run planning path, not sync.
- Adversarial review is an extra safety pass, not proof of correctness.
- Memory recall is useful, but you still decide which recalled context matters.

## Docs and examples

- [Documentation site](https://m24927605.github.io/ait/)
- [Getting started](https://m24927605.github.io/ait/getting-started/)
- [Command reference](https://m24927605.github.io/ait/reference/commands/)
- [Adversarial code review](https://m24927605.github.io/ait/reference/adversarial-code-review/)
- [Pain-point demos](https://m24927605.github.io/ait/demos/pain-point-demos/)
- [Review benchmark dogfood report](docs/review-benchmark-dogfood-report.md)
- [Examples](examples/)
- [CHANGELOG](CHANGELOG.md)
- [PyPI](https://pypi.org/project/ait-vcs/) · [npm](https://www.npmjs.com/package/ait-vcs)

MIT licensed.
