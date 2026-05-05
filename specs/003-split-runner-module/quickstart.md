# Quickstart: Split Runner Module

## Baseline

```bash
uv run pytest tests/test_runner.py
```

## Refactor Verification

```bash
uv run pytest tests/test_runner.py
uv run pytest tests/test_cli_run.py tests/test_cursor_capture.py tests/test_aider_capture.py tests/test_memory_security.py tests/test_brain.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

## Architecture Checks

```bash
wc -l src/ait/runner.py src/ait/runner_*.py | sort -nr
```

Expected:

- `src/ait/runner.py` is below 600 lines.
- No `src/ait/runner_*.py` helper exceeds 400 lines.

```bash
PYTHONPATH=src python3 - <<'PY'
from ait.runner import (
    AIT_CONTEXT_BUDGET_CHARS, _finish_attempt_locally,
    _fit_transcript_field_budget, _run_command_with_pty_transcript,
    _stage_all_changes, _strip_terminal_control, _write_command_transcript,
    run_agent_command,
)
print("ait.runner public imports ok")
PY
```
