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
ait status
eval "$(ait enable --shell)"
```

`ait enable --shell` installs repo-local wrappers for supported agent
CLIs found on `PATH`, such as:

```text
.ait/bin/claude
.ait/bin/codex
.ait/bin/aider
```

It prints a shell export that puts `.ait/bin` first on `PATH` for the
current terminal session. After that, detected agent commands in this
repository run through `ait`.

For virtualenv installs, use the local executable:

```bash
.venv/bin/ait status
eval "$(.venv/bin/ait enable --shell)"
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
unchanged until you promote the attempt.

Control the generated intent and commit message with environment
variables:

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

If you enabled direnv instead of using `doctor --fix`, remove or edit
the `PATH_add .ait/bin` line in `.envrc`, then reload the shell.

The `.ait/` directory contains local metadata for this repository. Do
not delete it if you want to keep recorded intents, attempts, evidence,
and worktrees.
