# ait

`ait` is an AI-agent-native version control layer on top of Git.

The MVP tracks:

- structured intents
- isolated attempts in Git worktrees
- daemon-ingested tool events from agent harnesses
- queryable evidence, file access, and commit linkage
- verification, promote, discard, and rebase flows

## Status

This repository is at `0.6.5` alpha quality for local dogfood use. It is
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
pipx install "git+https://github.com/m24927605/ait.git@v0.6.5"
```

Or install into a virtual environment:

```bash
python3.14 -m venv .venv
.venv/bin/pip install "git+https://github.com/m24927605/ait.git@v0.6.5"
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

## Quickstart

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

For lower user friction, install the repo-local Claude wrapper once:

```bash
eval "$(ait doctor --fix)"
```

After that, invoking `claude ...` from the repository will hit
`.ait/bin/claude`, which runs Claude Code through `ait run --adapter
claude-code` in an isolated attempt worktree. The wrapper passes through
all Claude arguments. It uses `AIT_INTENT` and `AIT_COMMIT_MESSAGE` when
set, otherwise it falls back to conservative defaults:

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  'Append one line to README.md'
```

To set up direnv instead of changing the current shell directly:

```bash
ait bootstrap
direnv allow
```

Check whether the automation path is ready:

```bash
ait status
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

These adapters currently provide worktree isolation, context handoff,
command provenance, and exit-code verification. Native tool-level hooks
for Codex and Aider are not implemented yet.

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
ait bootstrap
ait bootstrap claude-code
ait bootstrap claude-code --shell
ait bootstrap claude-code --check
ait doctor --fix
ait status
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
git checkout v0.6.5
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
