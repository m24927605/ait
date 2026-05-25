---
title: Getting started with ait
description: >-
  Install ait, try the demo, initialize a repo, run one agent, inspect the
  attempt, and apply or recover the result.
---

# Getting started

`ait` is alpha, local-first software. Metadata stays in `.ait/` on your machine.

This page gives you one simple path: try the demo, initialize a repo, run one
agent, inspect the attempt, then apply or recover.

## 1. Try the demo

No API keys. No existing repo. No real agent required.

```bash
pipx install ait-vcs
ait demo
```

The demo creates a temporary repo, records a few attempts, and shows a review
gate blocking a risky change. Everything is local.

Clean up demo directories:

```bash
ait demo --clean
```

## 2. Install for daily use

Recommended:

```bash
pipx install ait-vcs
ait --version
```

The package is `ait-vcs`. The command is `ait`. Requirements: Python 3.14+ and
Git.

If your default Python is older:

```bash
pipx install --python python3.14 ait-vcs
```

Other install paths:

```bash
# virtualenv
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs

# npm wrapper
npm install -g ait-vcs

# pinned GitHub tag
pipx install "git+https://github.com/m24927605/ait.git@v1.1.0"
```

## 3. Initialize a repo

Run this inside a project:

```bash
cd your-repo
ait init
```

`ait init` creates `.ait/` next to `.git/` and installs repo-local wrappers for
supported agent CLIs it can find.

If prompted, allow the shell integration:

```bash
direnv allow
```

Check that your agent command will go through `ait`:

```bash
ait status claude-code
ait status codex
ait status --all
```

`wrapped` means the command resolves to the repo-local `ait` wrapper.
`bypass_risk` means your shell still resolves to the real agent binary, so `ait`
will not capture that run. Run `direnv allow`, reload your shell, or use
`ait repair`, then check again.

## 4. Run one agent

Use the agent normally:

```bash
claude -p "Add a short note to README.md saying we tried ait"
```

The wrapped run is recorded as an isolated attempt. The root checkout should not
change until you apply the result.

## 5. Inspect the attempt

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

`ait attempt show` gives you the prompt, changed files, output, commits, and
review state for that attempt.

## 6. Apply or recover

If the result is good:

```bash
ait apply latest
```

If the run failed, was interrupted, or needs manual inspection:

```bash
ait recover latest
ait resume latest
```

Until `ait apply`, the agent's work is a proposal, not a fact.

## Next workflows

Run a separate reviewer agent:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high
```

Search prior decisions:

```bash
ait memory recall "retry budget"
```

Use another agent:

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [Any shell agent](integrations/shell.md)
