<div align="center">

# ait

### Git-native safety rails for AI coding agents

Run Claude Code, Codex, Aider, Gemini, and Cursor in isolated Git
worktrees with traceable commits, reviewable attempts, and repo-local
memory.

<sub>[English](README.md) · [繁體中文](README.zh-TW.md)</sub>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#status)

</div>

---

AI agents are fast. Git history, review discipline, and handoff context
often are not.

`ait` wraps the agent CLIs you already use and turns each run into a
reviewable attempt. The agent edits an isolated worktree, `ait` records
what happened, and your main checkout stays untouched until you promote
the result.

```bash
pipx install ait-vcs
cd your-repo
ait init
direnv allow   # only if prompted

claude ...
```

Prefer npm?

```bash
npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

The package is named `ait-vcs` on PyPI and npm. The installed command is
`ait`.

## Problems ait Solves

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

`ait` is not another agent. It is the Git layer around the agents you
already trust.

## What It Feels Like

Initialize once:

```bash
ait init
direnv allow   # only if prompted
```

Then keep using your agent:

```bash
claude ...
codex ...
aider ...
gemini ...
cursor ...
```

After a successful wrapped run, inspect the attempt:

```bash
ait status
ait attempt show <attempt-id>
```

Promote only when you are ready:

```bash
ait attempt promote <attempt-id> --to main
```

Until promotion, your root checkout stays unchanged.

## Core Features

| Feature | Description |
| --- | --- |
| Worktree isolation | Agent edits happen away from your root checkout |
| Attempt provenance | Commands, status, output, changed files, and commits stay linked |
| Agent wrappers | Repo-local `claude`, `codex`, `aider`, `gemini`, and `cursor` wrappers |
| Auto commit capture | Successful changes become attempt-linked commits, without duplicating existing commits |
| Local memory | Prior attempts, commits, notes, and imported agent memory feed future runs |
| Review flow | Promote, discard, rebase, inspect, and query attempts using normal Git concepts |

## Quick Examples

Set explicit intent and commit text:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "Shorten the README and improve the quickstart"
```

Wrap a command directly:

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

Use repo-local memory:

```bash
ait memory
ait memory search "auth adapter"
ait memory recall "billing retry"
```

Repair local setup if wrappers drift:

```bash
ait repair
ait repair codex
```

## Integrations

`ait` ships first-class adapters for the agents most teams already run.
Each adapter wraps the upstream CLI, isolates its work in a Git worktree,
and records the attempt locally in `.ait/`.

`ait init` detects every supported agent CLI on `$PATH` and wires it up
automatically — wrappers under `.ait/bin/`, hooks merged into the
relevant `.claude/`, `.codex/`, `.gemini/` config. The per-adapter
sections below assume you already ran `ait init`. To re-run setup
explicitly (e.g. after upgrading an agent), use `ait adapter setup
<name>`.

### Run Claude Code in a Git worktree

```bash
claude -p --permission-mode bypassPermissions "Refactor the auth module"
```

`ait` captures the prompt, edited files, status, and resulting commits as
one attempt. Promote it with `ait attempt promote <id> --to main` once you
are happy with the diff.

### Run Codex CLI safely on a real repository

```bash
ait run --adapter codex --intent "Implement parser edge cases" -- codex
```

Each Codex session edits an isolated worktree. Failed attempts are kept
for inspection; only promoted attempts touch your root checkout.

### Run Aider in an isolated worktree

```bash
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
```

Aider's commits land inside the attempt worktree, with full provenance
linking the prompt, edited files, and commits.

### Run Gemini CLI with attempt history

```bash
ait run --adapter gemini --intent "Add config validation" -- gemini
```

Gemini sessions are recorded as attempts the same way as Claude Code and
Codex. `ait memory recall` later surfaces what each agent tried.

### Run Cursor agents with reviewable provenance

```bash
ait run --adapter cursor --intent "Migrate to new SDK" -- cursor
```

Cursor edits are confined to an attempt worktree. The attempt log keeps
the changed files, exit status, and commits available for review and
promotion.

### Wrap any other shell agent

```bash
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

Use the generic `shell` adapter to give attempt provenance to any custom
agent or script.

## How It Works

```text
your prompt
    |
    v
agent CLI wrapped by ait
    |
    v
isolated attempt worktree
    |
    v
attempt metadata + commits + memory
    |
    v
review, promote, discard, or rebase
```

The wrapped process receives:

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
AIT_CONTEXT_FILE   # when context is enabled
```

`AIT_CONTEXT_FILE` contains a compact repo-local handoff selected from
previous attempts, commits, curated notes, and imported agent memory
files such as `CLAUDE.md` and `AGENTS.md`.

## Install

Recommended:

```bash
pipx install ait-vcs
ait --version
```

Virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --help
```

npm wrapper:

```bash
npm install -g ait-vcs
ait --version
```

Tagged GitHub release:

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.38"
```

Upgrade:

```bash
ait upgrade
ait --version
```

Preview an upgrade:

```bash
ait upgrade --dry-run
```

## Useful Commands

```bash
ait status
ait status --all
ait doctor
ait doctor --fix

ait adapter list
ait adapter doctor claude-code
ait adapter setup claude-code

ait attempt list
ait attempt show <attempt-id>
ait intent show <intent-id>
ait context <intent-id>

ait memory
ait memory search "auth adapter"
ait memory lint
ait memory lint --fix

ait graph
ait graph --html
```

Shell auto-activation:

```bash
ait shell show --shell zsh
ait shell install --shell zsh
ait shell uninstall --shell zsh
```

## Requirements

- Python 3.14+
- Git
- SQLite from the Python standard library
- Node.js 18+ only when installing through npm

## Status

`ait` is currently `0.55.38` and alpha quality. It is intended for local
dogfooding and early users who are comfortable with Git workflows.

Metadata is local to one repository under `.ait/`. It is not
synchronized across machines.

## Development

Set up the repository:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install pytest
```

Verify:

```bash
.venv/bin/pytest -q
.venv/bin/ait --version
.venv/bin/ait --help
```

Before a release:

```bash
git status --short
.venv/bin/pytest -q
```

The release version in `pyproject.toml`, the Git tag, and this README
should match.

## Documentation

- [Getting started](docs/getting-started.md)
- [Claude Code run worktree workflow](docs/claude-code-run-worktree.md)
- [Claude Code hook smoke test](docs/claude-code-live-smoke.md)
- [Long-term memory design](docs/long-term-memory-design.md)
- [Long-term memory acceptance](docs/long-term-memory-acceptance.md)
- [Repo brain design](docs/repo-brain-design.md)
- [Repo brain acceptance](docs/repo-brain-acceptance.md)
- [Release checklist](docs/release-checklist.md)
