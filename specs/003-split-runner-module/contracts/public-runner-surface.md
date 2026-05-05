# Contract: Public Runner Surface

The refactor must preserve these imports:

```python
from ait.runner import (
    AIT_CONTEXT_BUDGET_CHARS,
    _finish_attempt_locally,
    _fit_transcript_field_budget,
    _run_command_with_pty_transcript,
    _stage_all_changes,
    _strip_terminal_control,
    _write_command_transcript,
    run_agent_command,
)
```

## Patch Points

The following patch points must still affect `run_agent_command()`:

- `ait.runner.start_daemon`
- `ait.runner.AitHarness.finish`
- `ait.runner._write_command_transcript`
- `ait.runner.utc_now`
- `ait.runner.add_attempt_memory_note`
- `ait.runner._stage_all_changes`

## Behavior

- `run_agent_command()` keeps the same arguments, return fields, warnings, and
  exception behavior.
- Helper extraction must not change command cwd, environment variables,
  transcript refs, memory note behavior, report refresh behavior, or commit
  creation policy.
