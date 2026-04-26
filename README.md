# ait

`ait` is an AI-agent-native version control layer on top of Git.

The MVP tracks:

- structured intents
- isolated attempts in Git worktrees
- daemon-ingested tool events from agent harnesses
- queryable evidence, file access, and commit linkage
- verification, promote, discard, and rebase flows

## Status

This repository is at `0.1.0` release-candidate quality for local
dogfood use. It is local-only: metadata lives in `.ait/` inside one Git
repository and is intentionally not synchronized across machines.

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

## Claude Code Hook Example

`examples/claude_code_hook.py` is a conservative Claude Code hook bridge.
It creates one ait intent and attempt per Claude session, streams
`PostToolUse` / `PostToolUseFailure` events through `AitHarness`, sends
a heartbeat on `Stop`, and finishes the attempt on `SessionEnd`.

Example settings are in:

```text
examples/claude-code-settings.json
```

To try it, copy the relevant hook entries into your Claude Code
`settings.json` for this project. The hook expects `ait` to be importable
by the Python interpreter used in the command, so run it from an
installed development environment.

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

The release candidate for `0.1.0` should have:

- clean working tree
- passing tests
- dogfood notes updated
- changelog updated
- version in `pyproject.toml` matching the tag
