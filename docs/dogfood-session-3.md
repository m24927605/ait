# Dogfood Session 3

Date: 2026-04-26

Goal: prove the Claude Code hook bridge path before writing release
docs. Session 2 proved a manual harness client; this session simulates
Claude Code hook events against `examples/claude_code_hook.py`.

## What Ran

The session fed these hook payloads to the bridge:

- `SessionStart`
- `PostToolUse` for `Read`
- `PostToolUse` for `Edit`
- `PostToolUseFailure` for `Bash`
- `Stop`
- `SessionEnd`

The hook was executed through:

```text
.venv/bin/python examples/claude_code_hook.py
```

## What Worked

- `SessionStart` started the daemon when needed.
- The hook created a new intent and attempt with:
  - `agent_id = claude-code:default`
  - `agent_harness = claude-code`
  - `agent_model = claude-sonnet-4-6`
- Session state was persisted under `.ait/claude-code-hooks/`.
- The hook streamed tool events through `AitHarness`.
- `Stop` sent a heartbeat.
- `SessionEnd` sent `attempt_finished`.
- The final attempt was `reported_status=finished` and
  `verified_status=succeeded`.

Observed counters matched the simulated hook events:

```text
observed_tool_calls   = 3
observed_file_reads   = 1
observed_file_writes  = 1
observed_commands_run = 1
observed_duration_ms  = 44
```

Evidence files were indexed correctly:

```text
files.read    = src/ait/harness.py
files.touched = examples/claude_code_hook.py
```

## Limitations Found

The hook bridge records provenance for a Claude Code session, but it
does not force Claude Code's working directory into the ait attempt
worktree. The `SessionStart` hook returns the attempt workspace path as
additional context, but the user or harness still controls where the
agent actually edits.

This is acceptable for the release candidate because it proves automatic
event capture without blocking the agent. A deeper integration can use
Claude Code's `WorktreeCreate` hook or a wrapper command to make the ait
worktree the actual execution directory.

## Evidence Artifact

Test attempt:

```text
03d50b6c6207c384c78fc8ebf93a2c6502df4417:aa06b59d398d0921136739f60652097f:01KQ40WXT1MM7K63MCKT13546V
```

The attempt remains in local `.ait/` state as a dogfood artifact.

## Next Targets

For release readiness, the next targets are documentation and packaging:

1. README install and quickstart.
2. Minimal CI.
3. Changelog and release checklist for `0.1.0`.
