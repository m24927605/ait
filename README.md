# ait

Use AI coding agents without letting them blur your Git history.

`ait` wraps tools such as Claude Code, Codex, Aider, Gemini, and Cursor
in a repo-local safety layer. Each agent run gets its own isolated
worktree, its changes are linked back to the run that produced them, and
future agents can reuse a compact memory of what happened before.

With `ait`, agent work becomes easier to:

- review before it touches your main branch
- promote, discard, or rebase like normal Git work
- trace back to the intent, command, files, and commits that produced it
- hand off to the next agent without rebuilding context from scratch

## Why ait

AI agents are fast, but their changes can be hard to supervise. A single
prompt may edit many files, run commands, create commits, or leave
partial work behind. Without structure, the only record is usually a chat
transcript and a messy diff.

`ait` turns each run into an attempt:

1. create an isolated Git worktree
2. run the agent or command there
3. record command output, changed files, status, and commits
4. keep the root checkout unchanged until you promote the result

The goal is not to replace your agent. It is to make agent output feel
like reviewable engineering work.

## Quickstart

Install, initialize a repo, then keep using your agent CLI:

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

The package name is `ait-vcs`, but the installed command is `ait`.

`ait init` initializes the current Git repository, creates `.ait/`,
installs repo-local wrappers for detected agent CLIs, imports existing
agent memory files such as `CLAUDE.md` and `AGENTS.md`, and creates the
default memory policy. After your shell loads `.ait/bin`, commands such
as `claude`, `codex`, `aider`, `gemini`, and `cursor` run through
`ait`.

## What You Get

- isolated worktrees for agent edits
- attempt-linked commits instead of mystery changes
- local provenance for commands, files, status, and output
- repo memory rebuilt from prior attempts and commits
- simple promotion back to your main branch
- no remote service requirement

## Status

This repository is at `0.55.26` alpha quality for local dogfood use.
Metadata lives in `.ait/` inside one Git repository and is not
synchronized across machines.

## Requirements

- Python 3.14+
- Git
- SQLite from the Python standard library
- Node.js 18+ only when installing through npm

## Install

From PyPI:

```bash
pipx install ait-vcs
ait --version
```

Inside a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --help
```

From npm:

```bash
npm install -g ait-vcs
ait --version
```

From a tagged GitHub release:

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.26"
```

Upgrade an existing install:

```bash
ait upgrade
ait --version
```

Preview the upgrade command:

```bash
ait upgrade --dry-run
```

## Daily Workflow

Initialize once:

```bash
ait init
direnv allow   # only if prompted
```

Then use the tools you already use:

```bash
claude ...
codex ...
aider ...
```

Wrapped agent commands run inside isolated attempt worktrees. If the
agent changes files successfully, `ait` records the result as an
attempt-linked commit. If the agent already made a commit, `ait` records
that commit instead of creating a duplicate.

Set explicit intent and commit text when useful:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "Shorten the README"
```

Inspect and promote an attempt:

```bash
ait status
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

Until promotion, the root checkout stays unchanged.

Repair repo-local wrappers or memory policy if setup drifts:

```bash
ait repair
ait repair codex
```

## Running Commands Explicitly

Use `ait run` when you want to wrap a command without relying on
repo-local shell wrappers:

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

The wrapped process receives:

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
AIT_CONTEXT_FILE   # when context is enabled
```

Use `--commit-message` for a specific attempt commit message, or
`--no-auto-commit` for diagnostic runs that should leave worktree
changes uncommitted.

## Memory

`ait` keeps repo-local memory in `.ait/` and injects relevant context
into wrapped agent runs. This is not remote model memory; each run gets
a fresh local handoff selected from prior attempts, commits, notes, and
imported agent memory files.

That means a later agent can learn from previous attempts without you
pasting old transcripts back into the prompt.

Common commands:

```bash
ait memory
ait memory --path src/
ait memory search "auth adapter"
ait memory recall "billing retry"
ait memory lint
ait memory lint --fix
ait memory policy show
ait memory import
```

The default memory policy excludes common sensitive paths and redacts
common secret patterns before transcript evidence becomes searchable.

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
ait graph
ait graph --html
```

For shell auto-activation:

```bash
ait shell show --shell zsh
ait shell install --shell zsh
ait shell uninstall --shell zsh
```

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

## More Documentation

- [Getting started](docs/getting-started.md)
- [Claude Code run worktree workflow](docs/claude-code-run-worktree.md)
- [Claude Code hook smoke test](docs/claude-code-live-smoke.md)
- [Long-term memory design](docs/long-term-memory-design.md)
- [Long-term memory acceptance](docs/long-term-memory-acceptance.md)
- [Repo brain design](docs/repo-brain-design.md)
- [Repo brain acceptance](docs/repo-brain-acceptance.md)
- [Release checklist](docs/release-checklist.md)
