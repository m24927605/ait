# Implementation Plan: Split Runner Module

**Branch**: `003-split-runner-module` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/003-split-runner-module/spec.md`

## Summary

Reduce coupling in `src/ait/runner.py` by extracting PTY handling, context
generation, transcript persistence, and semantic exit-code helpers into focused
modules. Keep `ait.runner` as the public orchestration and monkey-patch surface
so existing tests and external integrations continue to work.

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: Python standard library only; no new runtime dependencies
**Storage**: Existing `.ait/state.sqlite3`, worktree files, transcripts, and reports
**Testing**: `pytest` and `unittest` over existing tests
**Target Platform**: Local POSIX CLI environments with Git
**Project Type**: Python CLI/library package
**Performance Goals**: Preserve current subprocess behavior and avoid additional runner startup work
**Constraints**: Preserve `ait.runner` imports and patch points; no CLI, SQLite, daemon, worktree, or memory policy behavior changes
**Scale/Scope**: Runner helper extraction only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Kit Traceability**: PASS. Active feature is recorded in
  `.specify/feature.json` and artifacts live under `specs/003-split-runner-module/`.
- **Low Coupling, High Cohesion**: PASS. PTY, context, transcript, and semantic
  helpers have explicit modules; `runner.py` keeps orchestration.
- **Stable Public Behavior**: PASS. The plan preserves `run_agent_command`,
  `RunResult`, imported helper symbols, and existing patch points.
- **Local Safety And Data Integrity**: PASS. No new path deletion, Git ref
  mutation, daemon protocol, or SQLite schema behavior is introduced.
- **Verification Before Completion**: PASS. Targeted runner tests, consumer
  tests, full suites, line-count checks, and patch-surface imports are required.

## Project Structure

### Documentation (this feature)

```text
specs/003-split-runner-module/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── public-runner-surface.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/ait/
├── runner.py              # public orchestration and patch surface
├── runner_context.py      # context rendering and budget fitting
├── runner_pty.py          # PTY subprocess capture
├── runner_semantics.py    # refusal detection and semantic exit code
└── runner_transcript.py   # transcript persistence and normalization

tests/
└── test_runner.py
```

**Structure Decision**: Keep `src/ait/runner.py` as a module, not a package, to
preserve `unittest.mock.patch("ait.runner.<name>")` behavior. Extract only
helpers whose moved implementation does not need to be directly patched.

### Dependency Direction

Allowed direction:

```text
runner.py -> runner_context.py
runner.py -> runner_pty.py
runner.py -> runner_semantics.py
runner.py -> runner_transcript.py
```

Helper modules must not import `ait.runner`. `runner.py` may import helper
functions as module-level names so existing patches against `ait.runner.*`
continue to affect orchestration.

### Public Compatibility Surface

- `RunResult`
- `AIT_CONTEXT_BUDGET_CHARS`
- `_finish_attempt_locally`
- `_fit_transcript_field_budget`
- `_run_command_with_pty_transcript`
- `_strip_terminal_control`
- `_stage_all_changes`
- `_write_command_transcript`
- `run_agent_command`
- Patch points: `start_daemon`, `AitHarness`, `utc_now`,
  `add_attempt_memory_note`, `_write_command_transcript`, `_stage_all_changes`

### Verification Plan

```bash
uv run pytest tests/test_runner.py
uv run pytest tests/test_cli_run.py tests/test_cursor_capture.py tests/test_aider_capture.py tests/test_memory_security.py tests/test_brain.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
wc -l src/ait/runner.py src/ait/runner_*.py | sort -nr
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

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Keep `runner.py` as a patch surface | Existing tests and integrations patch module-level names | Package conversion would make imported helper globals harder to patch without changing tests |
