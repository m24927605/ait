---
title: Getting started with ait
description: >-
  Install ait, initialize it inside an existing Git repository, and run your
  first AI coding agent inside an isolated worktree with full attempt
  provenance.
---

# Getting started

## Requirements

- Python 3.14 or newer
- Git
- SQLite (ships with the Python standard library)
- Node.js 18+ only when installing through npm

## Install

Recommended (pipx):

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

Pinned GitHub tag:

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.36"
```

## Initialize a repository

Inside any Git repository:

```bash
cd your-repo
ait init
direnv allow   # only if prompted
```

`ait init` creates a `.ait/` directory next to `.git/`. All AI metadata stays
inside this directory and is not synced across machines.

## First wrapped run

Use any supported agent CLI. `ait` will detect it and record an attempt:

```bash
claude -p --permission-mode bypassPermissions "Refactor the auth module"
```

Inspect what happened:

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

Promote when ready:

```bash
ait attempt promote <attempt-id> --to main
```

Until promotion, your root checkout stays unchanged.

## Next steps

- [Run Claude Code in a worktree](integrations/claude-code.md)
- [Run Codex CLI safely](integrations/codex.md)
- [Run Aider with provenance](integrations/aider.md)
- [Command reference](reference/commands.md)
