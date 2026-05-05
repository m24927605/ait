# Feature Specification: Split Runner Module

**Feature Branch**: `003-split-runner-module`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Refactor the oversized runner module into cohesive orchestration, context, transcript, PTY, finalization, and local harness modules while preserving run_agent_command public behavior and fixing any discovered runner bugs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Wrapped Run Behavior (Priority: P1)

As an AIT user, I want `ait run` and `run_agent_command()` to behave exactly as
before after internals are split, so that agent execution, attempt lifecycle,
auto-commit, reports, and memory side effects remain trustworthy.

**Why this priority**: Runner is the highest-risk orchestration path and touches
worktrees, daemon events, transcripts, memory, and commits.

**Independent Test**: Run `tests/test_runner.py` after the split. All existing
run lifecycle, local-only, auto-commit, context, memory, and transcript tests
must pass unchanged.

**Acceptance Scenarios**:

1. **Given** a successful wrapped command, **When** it completes, **Then** the
   attempt is finished, verified, optionally committed, reported, and returned
   with the same `RunResult` fields.
2. **Given** daemon startup fails, **When** a wrapped command runs, **Then** the
   local-only fallback records the finish event as before.
3. **Given** auto-commit or transcript post-processing is interrupted, **When**
   the runner handles the interruption, **Then** the same exit code and warning
   behavior are preserved.

---

### User Story 2 - Preserve Test And Extension Patch Surface (Priority: P1)

As a maintainer, I want existing tests and extension code that patch
`ait.runner.start_daemon`, `ait.runner._write_command_transcript`,
`ait.runner._stage_all_changes`, and related symbols to keep working, so that
the refactor does not break established integration seams.

**Why this priority**: Runner tests intentionally patch module-level names to
simulate daemon failure, transcript interrupts, and git staging interrupts.

**Independent Test**: Run runner tests that use `unittest.mock.patch` against
`ait.runner.*` symbols without modifying the tests.

**Acceptance Scenarios**:

1. **Given** a test patches `ait.runner._write_command_transcript`, **When**
   `run_agent_command()` captures output, **Then** the patched function is used.
2. **Given** a test patches `ait.runner._stage_all_changes`, **When**
   auto-commit runs, **Then** the patched function is used.
3. **Given** code imports `AIT_CONTEXT_BUDGET_CHARS`,
   `_finish_attempt_locally`, `_fit_transcript_field_budget`,
   `_run_command_with_pty_transcript`, `_strip_terminal_control`, or
   `run_agent_command` from `ait.runner`, **When** imports are evaluated,
   **Then** they still succeed.

---

### User Story 3 - Make Runner Internals Cohesive (Priority: P2)

As a maintainer, I want PTY handling, context building, transcript persistence,
and semantic exit-code helpers separated from the command orchestration path, so
that future changes can be made in the relevant module.

**Why this priority**: `runner.py` currently mixes orchestration with terminal
I/O, transcript normalization, context assembly, semantic refusal detection, and
Git staging helpers.

**Independent Test**: Inspect module boundaries and line counts after the split.
`runner.py` remains the public orchestrator and patch surface, while extracted
helper modules each own one responsibility.

**Acceptance Scenarios**:

1. **Given** a maintainer inspects runner files, **When** the refactor is
   complete, **Then** PTY, transcript, context, and semantic helper concerns are
   not implemented in the same file as the main orchestration function.
2. **Given** line-count gates run, **When** the refactor is complete, **Then**
   `src/ait/runner.py` is below 600 lines and no new runner helper exceeds 400
   lines.

### Edge Cases

- PTY transcript capture still relays terminal bytes and restores terminal
  settings.
- Transcript writing still redacts text, honors memory exclusion, writes
  normalized sidecars, and treats `KeyboardInterrupt` as interrupted
  post-processing.
- Context file generation still enforces the configured budget.
- Refusal detection still returns semantic exit code `3` only when the command
  succeeded, looks like a refusal, and produced no meaningful workspace changes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST keep `run_agent_command()` public behavior compatible.
- **FR-002**: AIT MUST keep `RunResult` fields and values compatible.
- **FR-003**: AIT MUST keep runner symbols used by existing tests importable
  from `ait.runner`.
- **FR-004**: Module-level patch points used by existing tests MUST keep
  affecting `run_agent_command()`.
- **FR-005**: PTY handling MUST be moved to a focused helper module.
- **FR-006**: Context file rendering and budget fitting MUST be moved to a
  focused helper module.
- **FR-007**: Transcript persistence, redaction, normalization, and trace-name
  helpers MUST be moved to a focused helper module.
- **FR-008**: Semantic exit-code/refusal helpers MUST be moved to a focused
  helper module.
- **FR-009**: `src/ait/runner.py` MUST remain the orchestration and public patch
  surface rather than becoming a hidden package implementation.
- **FR-010**: If a runner bug is discovered during extraction, it MUST be fixed
  in the same slice with a regression test.

### Key Entities *(include if feature involves data)*

- **RunResult**: Public result returned after a wrapped run.
- **PTY Completed Process**: Internal command result for terminal capture.
- **Command Transcript**: Raw/redacted trace and normalized transcript sidecar.
- **Context File**: Generated `.ait-context.md` injected into wrapped worktrees.
- **Semantic Exit Decision**: Refusal detection and workspace-change check used
  to convert successful no-op refusals to exit code `3`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `uv run pytest tests/test_runner.py` passes unchanged.
- **SC-002**: Targeted runner consumers pass: `tests/test_cli_run.py`,
  `tests/test_cursor_capture.py`, `tests/test_aider_capture.py`,
  `tests/test_memory_security.py`, and `tests/test_brain.py`.
- **SC-003**: Full `uv run pytest`, full `PYTHONPATH=src python3 -m unittest
  discover -s tests`, and `git diff --check` pass.
- **SC-004**: `src/ait/runner.py` is below 600 lines.
- **SC-005**: No new `src/ait/runner_*.py` helper exceeds 400 lines.
- **SC-006**: Public imports and patch points named in User Story 2 remain
  available from `ait.runner`.

## Assumptions

- This slice does not change CLI flags, output format, SQLite schema, daemon
  protocol, worktree lifecycle, or memory policy behavior.
- Existing tests are the compatibility baseline.
- New tests are added only for newly discovered bugs or compatibility gaps.
