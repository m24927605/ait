---
title: Getting started with ait — the 5-minute path
description: >-
  Install ait, initialize it in a Git repo, run one agent, inspect the
  attempt, and apply the result. End to end in under five minutes.
---

# Getting started

AIT is alpha. Single machine, `.ait/` stays local, expect rough edges.

One linear path. Five minutes to read and run. Install, init, run one agent,
inspect the attempt, apply.

## 1. Install (30 seconds)

```bash
pipx install ait-vcs
ait --version
```

Expected:

```text
ait 1.1.0
```

The package on PyPI and npm is `ait-vcs`. The installed command is `ait`.
Requires Python 3.14+ and Git. On older Python, use
`pipx install --python python3.14 ait-vcs`.

## 2. Initialize the repo (30 seconds)

```bash
cd your-repo
ait init
```

Expected (trimmed):

```text
AIT initialized
Agent wrappers: aider, claude, codex
Next:
- exec $SHELL  # picks up .ait/bin via the installed shell hook
- then run claude ...
Details:
Git baseline: created initial commit
Repo: /path/to/your-repo
State: /path/to/your-repo/.ait
Shell hook: already installed for zsh
Memory policy: created
```

`ait init` creates `.ait/` next to `.git/`. It installs wrappers for every
agent CLI it finds on PATH.

Reload your shell so the `ait` wrapper takes effect:

```bash
exec $SHELL
```

## 3. Run one agent (2 minutes)

Use Claude Code. AIT detects it and records an attempt:

```bash
claude -p --permission-mode bypassPermissions "Add a TODO comment to README.md saying we tried ait"
```

Nothing in this command is AIT-specific. The wrapper routes through `ait run
--adapter claude-code` (`src/ait/cli/run.py`). Your root checkout does not
move while the agent works — edits land in an isolated Git worktree.

## 4. Inspect what happened (1 minute)

```bash
ait status
```

Expected (trimmed):

```text
AIT install:
- version: 1.1.0
Daemon: stopped              # or: running (socket_connectable=True, pid_matches=True)
AIT health: pass
Memory initialized: True
Latest result: <attempt-id>  ok
```

The `Latest result` line shows the attempt id. To list and inspect the full
attempt — prompt, output, changed files, commits — pass it explicitly:

```bash
ait attempt list
ait attempt show <attempt-id>
```

## 5. Apply (or recover) (30 seconds)

If the diff is good:

```bash
ait apply latest
```

If not, recover the working state instead:

```bash
ait recover latest
```

Both `ait apply` and `ait recover` special-case the literal `latest`. Other
attempt subcommands take a full or partial attempt id.

Until you call `ait apply`, the agent's work is a proposal, not a fact. Your
root checkout never moves on its own.

That is the five-minute path. You wrapped one agent, recorded one attempt,
applied one diff.

---

## Next steps

### Hand work to a second agent

Run Claude, then Codex, on the same repo. Codex receives Claude's
decisions through the handoff file. See
[`examples/pain-point-demos/07-cross-agent-handoff/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff).

### Run a separate reviewer agent

Run a different agent against the attempt's diff before apply:

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high
```

High-severity findings hold `ait apply`. See
[Adversarial code review](reference/adversarial-code-review.md).

### Search prior decisions

```bash
ait memory recall "retry budget"
```

`ait memory recall <query>` searches prior attempts, accepted facts, and
notes. It is a zero-touch read — it does not mutate `.ait/` or your source.

### Use other agent CLIs

- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [Any shell agent](integrations/shell.md)

### Other install paths

```bash
# virtualenv
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs

# npm wrapper
npm install -g ait-vcs

# pinned GitHub tag
pipx install "git+https://github.com/m24927605/ait.git@v1.1.0"
```

### Check that the wrapper is on PATH

```bash
ait status claude-code
```

`Bypass detection: wrapped` means the agent will go through AIT.
`Bypass detection: bypass_risk` means PATH still resolves to the real
binary; run `eval "$(ait init --shell)"` or `direnv allow`, then check
again.
