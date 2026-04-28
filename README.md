# ait

`ait` gives AI coding agents a safer Git workflow: isolated worktrees,
agent-linked commits, and provenance for what changed. It is designed so
you can keep invoking tools such as Claude Code while `ait` captures the
work in an attempt branch that can be reviewed and promoted later.

## 30 Second Quickstart

Install the PyPI package, enter a Git repository, let `ait` install
repo-local wrappers for the agent CLIs it can find, then keep using
`claude`, `codex`, or `aider`:

```bash
pipx install ait-vcs
cd your-repo
eval "$(ait init --shell)"
claude ...
```

`ait init --shell` initializes `.ait/`, installs repo-local wrappers for
detected agent CLIs, and prints a shell export for the current terminal.
After that, detected agent commands resolve to `.ait/bin/*` inside that
repository. The wrappers run agents through `ait run`, so the agent edits
an isolated attempt worktree and `ait` records the result as an
attempt-linked commit. Existing agent memory files such as `CLAUDE.md`
and `AGENTS.md` are imported automatically during regular `ait init` and
again on first wrapped agent run when needed. After each wrapped run,
`ait` also writes a compact attempt memory note with status, changed
files, commits, and confidence so future agents can reuse what happened.
When a new wrapped run starts, `ait` retrieves the most relevant
agent/attempt memory into a compact `AIT Relevant Memory` context
section. Use `ait memory recall <query>` or `ait memory recall --auto`
to inspect what memory would be selected before a run. Use
`ait memory lint` to audit memory quality and `ait memory lint --fix` for
conservative duplicate, secret, and overlong-note repairs.

If you do not use `pipx`, install in a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
eval "$(.venv/bin/ait init --shell)"
```

See [docs/getting-started.md](docs/getting-started.md) for activation,
verification, and rollback.

## What ait Tracks

- structured user intents
- isolated agent attempts in Git worktrees
- agent command output and lifecycle status
- long-term repo memory rebuilt from prior attempts and commits
- optional daemon-ingested tool events from harnesses
- queryable evidence, file access, and commit linkage
- promote, discard, rebase, and verification flows

## Status

This repository is at `0.31.0` alpha quality for local dogfood use. It is
local-only: metadata lives in `.ait/` inside one Git repository and is
intentionally not synchronized across machines.

## Requirements

- Python 3.14+
- Git
- SQLite from the Python standard library

## Install For Development

From the repository root:

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

## Install From GitHub

Install the tagged release with `pipx`:

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.31.0"
```

Or install into a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install "git+https://github.com/m24927605/ait.git@v0.31.0"
.venv/bin/ait --help
```

## Install From PyPI

The PyPI distribution name is `ait-vcs` because the shorter `ait` name
is already owned by another project. The installed command is still
`ait`.

```bash
pip install ait-vcs
ait --version
ait --help
```

Or inside a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --version
.venv/bin/ait --help
```

## Manual Intent/Attempt Flow

Initialize ait metadata in a Git repository:

```bash
ait init
```

Create an intent and attempt:

```bash
ait intent new "Fix auth expiry" --kind bugfix
ait attempt new <intent-id> --agent-id cli:human
```

The attempt command prints:

- `attempt_id`
- `workspace_ref`
- `base_ref_oid`
- `ownership_token`

Make changes in the attempt worktree, then commit through ait:

```bash
cd <workspace_ref>
# edit files
git add <files>
cd <repo-root>
ait attempt commit <attempt-id> -m "fix auth expiry"
```

Promote the attempt:

```bash
ait attempt promote <attempt-id> --to main
```

If `main` advanced while the attempt was running:

```bash
ait attempt rebase <attempt-id> --onto main
ait attempt promote <attempt-id> --to main
```

Inspect state:

```bash
ait attempt show <attempt-id>
ait intent show <intent-id>
ait context <intent-id>
ait attempt list --verified-status succeeded
ait query --on attempt 'observed.tool_calls>0'
ait blame path/to/file.py
ait memory
ait memory --path src/
ait memory --promoted-only
ait memory search "auth adapter"
ait memory graph show
ait memory graph query "release process"
ait memory graph brief "release process"
ait memory graph brief "release process" --auto --agent codex:main --command-text "codex implement release"
```

## Daemon And Harness

Start the daemon:

```bash
ait daemon start
ait daemon status
```

The harness API streams lifecycle and tool events to the daemon:

```bash
python examples/harness_demo.py <attempt-id> <ownership-token> .ait/daemon.sock
```

After the demo:

```bash
ait attempt show <attempt-id>
```

Expected counters include tool calls, reads, writes, commands, and file
evidence under `files.read` and `files.touched`.

## Universal Agent Runner

`ait run` wraps any CLI-based agent or command in an ait intent and
attempt. It creates an isolated attempt worktree, starts the daemon,
runs the command in that worktree, records the command event, and marks
the attempt finished with the command exit code.

```bash
ait run --agent shell:local --intent "Try a generated change" -- \
  python -c "from pathlib import Path; Path('agent.txt').write_text('ok\n')"
```

By default, `ait run` prints parseable JSON. Command stdout and stderr
are captured as `command_stdout` and `command_stderr` fields:

```bash
attempt_id="$(ait run --format json --intent "Try change" -- \
  python -c "print('agent output')" | python -c 'import json,sys; print(json.load(sys.stdin)["attempt_id"])')"
```

Use `--format text` to stream command stdout and stderr directly to the
terminal while still printing the final ait result afterward.

The wrapped process receives:

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
```

Examples:

```bash
ait run --agent aider:main --intent "Fix auth expiry" -- aider src/auth.py
ait run --agent claude-code:manual --intent "Refactor query parser" -- claude
```

This is the shallow universal integration layer. Deeper adapters can add
native file-read/write events through hooks, but `ait run` already gives
session lifecycle, worktree isolation, exit-code verification, and
command provenance for any shell-launchable agent.

Use `--adapter` to select agent-specific defaults:

```bash
ait run --adapter shell --intent "Run local command" -- python script.py
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter codex --intent "Implement parser" -- codex
```

Adapters define the default `agent_id`, whether context is enabled by
default, and adapter-specific environment variables. `--agent` remains
available as an override.

Inspect adapter capabilities:

```bash
ait adapter list
ait adapter list --format json
ait adapter show claude-code
ait adapter show claude-code --format json
ait adapter doctor claude-code
ait adapter doctor claude-code --format json
ait adapter setup claude-code --print
```

The Claude Code doctor checks that the packaged hook script and settings
sample are available after installation, so native hook setup can be
generated without relying on a source checkout.

Add `--with-context` to write a compact agent-readable context file into
the attempt worktree and expose it as `AIT_CONTEXT_FILE`:

```bash
ait run --with-context --agent shell:local --intent "Continue previous work" -- \
  python -c "import os; print(open(os.environ['AIT_CONTEXT_FILE']).read())"
```

The context file includes long-term repo memory rebuilt from previous
ait attempts and commits.

## Long-Term Memory

`ait memory` renders a compact project memory summary from local durable
state:

```bash
ait memory
ait memory --format json
ait memory --path src/
ait memory --topic architecture
ait memory --promoted-only
ait memory --budget-chars 4000
ait memory search "auth adapter"
ait memory search "auth adapter" --format json
ait memory search "auth adapter" --ranker lexical
ait memory graph build
ait memory graph show
ait memory graph show --format json
ait memory graph query "release process"
ait memory graph query "release process" --format json
ait memory graph brief "release process"
ait memory graph brief "release process" --format json
ait memory graph brief "release process" --auto --explain
ait memory policy init
ait memory policy show
ait memory note add --topic architecture "Keep adapter layers thin."
ait memory note list
ait memory note remove <note-id>
```

For Claude Code, the repo-local wrapper injects this memory
automatically through `AIT_CONTEXT_FILE`. This does not give the model
permanent internal memory; it gives each run a fresh, repo-local memory
handoff that the agent can read before editing.

Memory can be filtered by path or note topic, restricted to promoted
attempts, and compacted to a character budget before rendering. Curated
notes are stored in the local `.ait/state.sqlite3` database and remain
repo-local unless the user chooses to move that state elsewhere.

`ait memory search <query>` searches repo-local memory evidence without
using a remote service. The default ranker uses local TF-IDF vectors
across curated notes, intent text, attempt metadata, changed files,
attempt commits, and captured Aider/Codex transcripts. Use
`--ranker lexical` for the older deterministic term matching fallback.
Common secret patterns are redacted before transcript evidence enters
`.ait/traces/`; rendered memory and search results mark redacted
evidence in metadata.

Use `ait memory policy init` to create `.ait/memory-policy.json`.
The policy excludes sensitive changed paths such as `.env`, `*.pem`,
and `secrets/` from memory summaries/search metadata, and excludes
transcripts matching private-key markers from durable transcript
contents before they can become searchable memory.

`ait memory graph build` materializes a derived repo brain under
`.ait/brain/graph.json` and `.ait/brain/REPORT.md`. The graph connects
repo docs, curated notes, intents, attempts, agents, changed files, and
attempt commits. It is a rebuildable local index, not the source of
truth. Wrapped Claude Code, Codex, and Aider runs refresh the graph
automatically before writing `AIT_CONTEXT_FILE`. The injected context
uses a compact `AIT Repo Brain Briefing` selected from the graph for the
current intent. AIT automatically builds the briefing query from intent
text, command args, agent identity, recent failed attempts, hot files,
and memory note topics, so normal agent invocation can receive relevant
repo memory without a manual workflow command or full graph dump.

See `docs/long-term-memory-design.md` and
`docs/long-term-memory-acceptance.md` for long-term memory design and
acceptance criteria. See `docs/repo-brain-design.md` and
`docs/repo-brain-acceptance.md` for the graph-backed repo brain slice.

## Integration Guide

Most AI agent workflows should start with `ait run`. It works with any
CLI that can be launched from a shell, and it gives the agent an
isolated Git worktree plus these environment variables:

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
```

When context is enabled, `ait run` also writes `.ait-context.md` into the
attempt worktree and exposes its path as `AIT_CONTEXT_FILE`.

Use the generic shell adapter for scripts, one-off commands, and custom
automation:

```bash
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

Use the Claude Code adapter when launching Claude from a repository. It
enables context by default, so Claude can read `AIT_CONTEXT_FILE` before
editing:

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
```

For lower user friction, install repo-local wrappers for every supported
agent binary found on `PATH`:

```bash
eval "$(ait init --shell)"
```

This initializes `.ait/`, installs wrappers for detected agent CLIs, and
activates `.ait/bin` in the current shell. The lower-level commands are
still available:

```bash
eval "$(ait doctor --fix)"
eval "$(ait enable --shell)"
```

After that, invoking `claude ...`, `codex ...`, or `aider ...` from the
repository will hit `.ait/bin/*`, which runs the agent through `ait run`
in an isolated attempt worktree. The wrapper passes through all agent
arguments. It uses `AIT_INTENT` and `AIT_COMMIT_MESSAGE` when set,
otherwise it falls back to conservative defaults:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  'Append one line to README.md'
```

If a repo-local wrapper cannot find the real agent binary, it prints a
diagnostic with the adapter, repo, wrapper path, real binary path, and a
next step such as `ait status codex`.

If a wrapper or `.envrc` is damaged after setup, repair the repo-local
automation without learning the lower-level setup commands:

```bash
ait repair
ait repair codex
ait repair --format json
```

If the project already has agent memory files from earlier AI work, import
them into ait long-term memory:

```bash
ait memory import
ait memory import --source claude
ait memory import --path .cursor/rules
ait memory import --format json
```

To set up direnv instead of changing the current shell directly:

```bash
ait bootstrap
direnv allow
```

To make new zsh/bash sessions auto-activate `.ait/bin` whenever you
enter an AIT-enabled repository, install the opt-in shell integration:

```bash
ait shell install --shell zsh
```

Inspect it before installing:

```bash
ait shell show --shell zsh
```

Remove it later with:

```bash
ait shell uninstall --shell zsh
```

Check whether the automation path is ready:

```bash
ait status
ait status --all
ait doctor
ait bootstrap --check
```

Text `ait status` may print a one-time automation hint to stderr when
the repo-local wrapper is not active. Use `--no-hints` for scripted
checks:

```bash
ait --no-hints status --format json
```

To make Claude edit an isolated attempt worktree and commit the result:

```bash
ait run --adapter claude-code \
  --format json \
  --intent "Update README" \
  --commit-message "update README with Claude" \
  -- claude -p --permission-mode bypassPermissions \
    'Append exactly this line to README.md: ait run worktree smoke ok'
```

The root checkout is unchanged until the attempt is promoted. Promote
the resulting attempt after reviewing it:

```bash
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

See `docs/claude-code-run-worktree.md` for the live smoke workflow.

For deeper Claude Code event capture, install the native hook example
after checking readiness:

```bash
ait adapter doctor claude-code
ait adapter setup claude-code
```

The hook bridge records Claude Code tool events such as file reads,
edits, and shell commands. It is optional: `ait run --adapter
claude-code` is the simpler first integration, while hooks add richer
provenance for teams that want tool-level evidence.

Use the Codex and Aider adapters the same way:

```bash
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
```

These adapters provide worktree isolation, context handoff, command
provenance, and exit-code verification. They can also install
repo-local wrappers just like Claude Code:

```bash
eval "$(ait bootstrap codex --shell)"
eval "$(ait bootstrap aider --shell)"
ait status codex
ait status aider
```

After bootstrap, invoking `codex ...` or `aider ...` from that
repository routes through `ait run --adapter codex` or
`ait run --adapter aider`, so `AIT_CONTEXT_FILE` carries the same
long-term memory handoff. Their stdout/stderr transcripts are captured
under `.ait/traces/` and become searchable memory evidence. Common
secrets are redacted before transcripts are written. Native tool-level
hooks for Codex and Aider are not implemented yet.

For a custom workflow, either wrap the command with `ait run` or call
the Python harness API directly from your agent runner:

```python
from ait.harness import AitHarness

with AitHarness.open(
    attempt_id=attempt_id,
    ownership_token=ownership_token,
    socket_path=".ait/daemon.sock",
    agent={
        "agent_id": "my-agent:worker",
        "harness": "my-agent",
        "harness_version": "0.1",
    },
) as harness:
    harness.record_tool(
        tool_name="Edit",
        category="write",
        duration_ms=120,
        success=True,
        files=[{"path": "src/app.py", "access": "write"}],
    )
    harness.finish(exit_code=0)
```

Choose the integration depth by how much evidence you need:

- `ait run`: lifecycle, isolated worktree, command event, exit code
- `ait run --with-context`: adds compact handoff context
- native hooks: adds per-tool read/write/command evidence
- harness API: full custom event capture from an agent runner

## Agent Context

`ait context <intent-id>` summarizes the intent, prior attempts, files,
commits, observed tool counters, and simple recommendations:

```bash
ait context <intent-id>
ait context <intent-id> --format json
```

This gives the next agent a short handoff instead of requiring a full
chat transcript or repeated repository exploration.

## Claude Code Hook Example

`ait adapter setup claude-code` installs a conservative Claude Code hook
bridge into the current repository at:

```text
.ait/adapters/claude-code/claude_code_hook.py
```

It also merges the hook configuration into:

```text
.claude/settings.json
```

Use `--print` to inspect the generated settings without writing files,
or `--target` to write a different settings path:

```bash
ait adapter setup claude-code --print
ait adapter setup claude-code --target .claude/settings.json
ait adapter setup claude-code --install-wrapper
ait adapter setup claude-code --install-wrapper --install-direnv
ait init
ait init --shell
ait init --adapter codex --format json
ait repair
ait repair codex
ait repair --format json
ait memory import
ait memory import --source claude
ait memory import --path .cursor/rules
ait enable
ait enable --shell
ait shell show --shell zsh
ait shell install --shell zsh
ait shell uninstall --shell zsh
ait bootstrap
ait bootstrap claude-code
ait bootstrap claude-code --shell
ait bootstrap claude-code --check
ait doctor --fix
ait status
ait status --all
ait doctor
```

The installed hook creates one ait intent and attempt per Claude
session, streams `PostToolUse` / `PostToolUseFailure` events through
`AitHarness`, sends a heartbeat on `Stop`, and finishes the attempt on
`SessionEnd`.

`examples/claude_code_hook.py` is the source version of the same hook.
Example settings are in:

```text
examples/claude-code-settings.json
```

The hook expects `ait` to be importable by the Python interpreter used in
the command, so run it from an installed development environment.

The packaged hook path installed by `ait adapter setup claude-code` is
covered by an end-to-end regression test that simulates Claude Code
`SessionStart`, `PostToolUse`, and `SessionEnd` payloads and verifies
that ait records the attempt and tool evidence. A live Claude Code smoke
test with Claude Code `2.1.119` also verified real hook payloads record
ait attempts and tool evidence; see `docs/claude-code-live-smoke.md`.

Current limitation: the hook records provenance, but it does not force
Claude Code to edit inside the ait attempt worktree. The SessionStart
hook returns the attempt workspace path as additional context. A deeper
integration can use Claude Code's worktree hook path or a wrapper command
to make the ait worktree the actual execution directory.

## Release Checks

Before cutting a release:

```bash
git status --short
.venv/bin/pytest -q
```

Clean clone smoke test:

```bash
tmpdir="$(mktemp -d)"
git clone https://github.com/m24927605/ait.git "$tmpdir/ait"
cd "$tmpdir/ait"
git checkout v0.31.0
python3.14 -m venv .venv
.venv/bin/pip install -e . pytest
.venv/bin/pytest -q
.venv/bin/ait --version
.venv/bin/ait --help
```

The release candidate should have:

- clean working tree
- passing tests
- dogfood notes updated
- changelog updated
- version in `pyproject.toml` matching the tag

PyPI publishing uses Trusted Publishing from GitHub Actions. Configure
the PyPI `ait-vcs` project with these publisher values before relying on
automatic release uploads:

- owner: `m24927605`
- repository: `ait`
- workflow: `publish.yml`
- environment: `pypi`

Manual upload remains available from the repository root:

```bash
.venv/bin/python -m build
.venv/bin/python -m twine upload dist/*
```

The publish workflow uses `skip-existing: true` so a manual fallback
upload does not make a later release workflow fail only because the same
distribution files already exist on PyPI.
