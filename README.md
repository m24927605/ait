<div align="center">

# ait

### Git-native safety rails for AI coding agents

Run Claude Code, Codex, Aider, Gemini, and Cursor in isolated Git
worktrees with traceable commits, reviewable attempts, and repo-local
memory.

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#status)

**[README](README.md) · [繁體中文](README.zh-TW.md) · [MIT License](LICENSE)**

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

## Why Developers Use ait

| Problem with agent coding | What ait adds |
| --- | --- |
| A prompt edits many files at once | Each run happens in an isolated Git worktree |
| The diff has no useful provenance | Attempts link intent, command output, files, and commits |
| Agents leave partial or failed work behind | You can inspect, discard, rebase, or promote attempts |
| The next agent repeats old investigation | Repo-local memory summarizes prior attempts and commits |
| Tooling should stay local | Metadata lives in `.ait/` inside your repository |

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
pipx install "git+https://github.com/m24927605/ait.git@v0.55.27"
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

`ait` is currently `0.55.27` and alpha quality. It is intended for local
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
