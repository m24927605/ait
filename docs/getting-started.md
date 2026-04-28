# Getting Started

This guide gets an external user from installation to a Claude Code run
that is routed through `ait`.

## Install

Use `pipx` for a global command with an isolated Python environment:

```bash
pipx install ait-vcs
ait --version
```

The PyPI package name is `ait-vcs`; the installed command is `ait`.

If you prefer a project virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --version
```

## Activate In A Repository

Run this from inside a Git repository:

```bash
ait init
direnv allow   # only if prompted
```

`ait init` initializes `.ait/`, installs repo-local wrappers for
supported agent CLIs found on `PATH`, writes `.envrc`, imports detected
agent memory, and creates the default memory policy guardrail. `direnv
allow` is only needed when prompted. Detected wrappers include:

```text
.ait/bin/claude
.ait/bin/codex
.ait/bin/aider
.ait/bin/gemini
.ait/bin/cursor
```

After that, detected agent commands in this repository run through `ait`.

Use the agent CLI normally:

```bash
claude ...
```

Check whether the current shell is ready:

```bash
ait status
```

For virtualenv installs, use the local executable:

```bash
.venv/bin/ait init
direnv allow   # only if prompted
```

Advanced troubleshooting commands are available when shell activation or
wrapper setup needs inspection:

```bash
eval "$(ait init --shell)"
ait doctor --fix --format json
```

That path performs the same repo setup work as `ait init`, repairs
detected agent wrappers, imports existing agent memory files, creates the
default memory policy, and reports whether the current shell is ready for
direct `claude`, `codex`, or `aider` use.

For persistent zsh/bash activation in new terminal sessions, install
the opt-in shell integration after reviewing it:

```bash
ait shell show --shell zsh
ait shell install --shell zsh
```

This writes a marked block to your shell rc file. Remove it with:

```bash
ait shell uninstall --shell zsh
```

## Verify

Check that the wrapper is active:

```bash
ait status
ait status --all
```

The important fields are:

```text
Wrapper installed: True
PATH uses wrapper: True
Real Claude binary: True
```

You can also run:

```bash
ait doctor
```

## Use Claude Code

Run Claude normally:

```bash
claude ...
```

The repo-local wrapper executes Claude Code through `ait run`, so the
agent edits an isolated attempt worktree. The root checkout stays
unchanged until you promote the attempt. Successful runs with changes
are committed automatically in the attempt worktree; if the agent already
creates a git commit, ait records that existing commit instead of making
a duplicate.

Optionally control the generated intent and commit message with
environment variables:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p 'Append one line to README.md'
```

Inspect and promote the result:

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

## Roll Back

To stop using the wrapper in the current shell, remove `.ait/bin` from
`PATH` or open a fresh terminal.

To remove the repo-local wrapper files:

```bash
rm -f .ait/bin/claude
```

If `.envrc` was written by `ait init`, remove or edit the
`PATH_add .ait/bin` line, then reload the shell.

The `.ait/` directory contains local metadata for this repository. Do
not delete it if you want to keep recorded intents, attempts, evidence,
and worktrees.
