# Data Model: Split Runner Module

## RunResult

Public result returned by `run_agent_command()`.

Fields:

- `intent_id`
- `attempt_id`
- `workspace_ref`
- `exit_code`
- `command_stdout`
- `command_stderr`
- `attempt`

## PTY Completed Process

Internal result for terminal-backed command capture.

Fields:

- `args`
- `returncode`
- `stdout`
- `stderr`

## Context File

Generated `.ait-context.md` written into the attempt worktree when context is
enabled.

Validation:

- Total text must fit the context character budget.
- Truncation marker must fit inside the requested budget.

## Command Transcript

Raw command transcript stored under `.ait/traces`.

State:

- Excluded by memory policy
- Redacted and stored
- Normalized sidecar written when transcript content can be normalized

## Semantic Exit Decision

Derived result used after command execution.

Inputs:

- subprocess exit code
- captured transcript text
- workspace status
- optional generated context file

Rules:

- Non-zero subprocess exits remain unchanged.
- Successful commands that do not look like refusal remain unchanged.
- Refusal-like successful commands with no workspace changes become exit code
  `3`.
