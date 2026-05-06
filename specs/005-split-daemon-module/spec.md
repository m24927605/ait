# Feature Specification: Split Daemon Module

**Feature Branch**: `005-split-daemon-module`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Refactor the oversized daemon module into cohesive lifecycle, server loop, client handler, background task, stale cleanup, process inspection, and path/config helper modules while preserving daemon CLI behavior, socket protocol responses, pid/socket cleanup semantics, verifier/summarizer threading behavior, and local safety."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Daemon Lifecycle And CLI Behavior (Priority: P1)

As an AIT user, I want `ait daemon start|stop|status|prune|serve` and
daemon startup from `ait run` or native hooks to behave exactly as before, so
that refactoring does not leave stale sockets, stale PID files, or broken
daemon startup.

**Why this priority**: Daemon lifecycle owns subprocess startup, PID tracking,
socket cleanup, signal handling, and local-only fallback behavior used by core
run flows.

**Independent Test**: Run daemon lifecycle tests and daemon-consuming CLI/run
tests after the split. Existing imports from `ait.daemon` must continue to work.

**Acceptance Scenarios**:

1. **Given** a stale PID file or stale socket, **When** daemon startup or prune
   runs, **Then** stale state is cleaned and valid state is preserved.
2. **Given** a running daemon process, **When** stop runs, **Then** matching AIT
   daemon PIDs are terminated and unrelated live PIDs are not trusted.
3. **Given** CLI status, doctor, or run code imports daemon helpers, **When**
   imports execute, **Then** public behavior and JSON/text output remain
   compatible.

---

### User Story 2 - Preserve Server Loop, Protocol, And Background Work (Priority: P1)

As an AIT user, I want daemon socket clients, concurrent harnesses, background
verification, transcript summarization, and stale-attempt reaping to keep their
current behavior, so that attempt evidence and lifecycle records remain
trustworthy.

**Why this priority**: The daemon is an integration boundary between harnesses,
SQLite event processing, verifier threads, summarizer threads, and transcript
retention.

**Independent Test**: Run daemon concurrency, reaper, verifier-thread,
end-to-end, and runner tests. Existing monkey-patch seams in `ait.daemon` must
continue to affect the server loop.

**Acceptance Scenarios**:

1. **Given** two harness clients connect concurrently, **When** both stream
   events, **Then** evidence is recorded without cross-attempt corruption.
2. **Given** duplicate finish events, **When** the daemon processes them, **Then**
   verifier/summarizer work is scheduled only for non-duplicate lifecycle
   events.
3. **Given** a stale running attempt, **When** the reaper loop runs after
   startup grace, **Then** the attempt is marked crashed and transcript pruning
   remains best-effort.

---

### User Story 3 - Make Daemon Internals Cohesive (Priority: P2)

As a maintainer, I want lifecycle/status, stale-state cleanup, process
inspection, reaper behavior, and server/patch surface responsibilities
separated, so daemon changes can be made without editing one oversized module.

**Why this priority**: `src/ait/daemon.py` currently mixes public lifecycle
commands, subprocess management, socket serving, client protocol handling,
thread bookkeeping, stale cleanup, process inspection, signal handlers, config
lookup, and reaper logic.

**Independent Test**: Run architecture gates after the split. `src/ait/daemon.py`
remains the public and patch-compatible surface while focused helper modules own
the extracted responsibilities.

**Acceptance Scenarios**:

1. **Given** a maintainer inspects daemon files, **When** the refactor is
   complete, **Then** lifecycle/status helpers, reaper helpers, and low-level
   state/process helpers are no longer implemented in the same file as client
   protocol handling.
2. **Given** line-count and dependency-direction gates run, **When** the
   refactor is complete, **Then** daemon files satisfy documented thresholds and
   helper modules do not import `ait.daemon`.

### Edge Cases

- Tests and integrations that patch `ait.daemon.run_accept_loop`,
  `ait.daemon._handle_client`, `ait.daemon._verify_attempt_in_background`, or
  `ait.daemon.verify_attempt` still affect daemon behavior.
- Signal handler install/restore remains safe outside the main thread.
- Stale cleanup never deletes non-socket, non-file, or unrelated user paths.
- Process inspection still works on `/proc` platforms and falls back to `ps`.
- Client protocol errors still produce daemon error responses without crashing
  the server process.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST keep public imports from `ait.daemon` compatible for
  daemon lifecycle functions, `DaemonStatus`, server loop helpers, and existing
  private patch surfaces used by tests.
- **FR-002**: AIT MUST keep `start_daemon()`, `stop_daemon()`,
  `prune_daemon()`, `daemon_status()`, and `serve_daemon()` behavior compatible.
- **FR-003**: AIT MUST keep socket protocol responses and event-processing
  behavior compatible.
- **FR-004**: AIT MUST keep concurrent client handling and SQLite write locking
  behavior compatible.
- **FR-005**: AIT MUST keep background verifier and summarizer thread behavior,
  warning text, and join semantics compatible.
- **FR-006**: AIT MUST keep reaper loop startup grace, timer behavior, stale
  attempt recovery, and transcript pruning behavior compatible.
- **FR-007**: AIT MUST keep stale PID/socket detection and cleanup semantics
  compatible, including unrelated live PID safety.
- **FR-008**: Daemon lifecycle/status behavior MUST move to a focused module or
  modules separate from client protocol handling.
- **FR-009**: Daemon reaper behavior MUST move to a focused module separate
  from lifecycle startup and client handling.
- **FR-010**: Daemon path/config/process-inspection helpers MUST move to focused
  helper code separate from server/client protocol handling.
- **FR-011**: `src/ait/daemon.py` MUST remain the public import and
  monkey-patch surface for existing tests.
- **FR-012**: If a daemon bug is discovered during extraction, it MUST be fixed
  in the same slice with a regression test.

### Key Entities *(include if feature involves data)*

- **DaemonStatus**: Public daemon state snapshot used by CLI and runner code.
- **Daemon Lifecycle Command**: Start, stop, prune, status, and serve behavior.
- **Daemon Socket Server**: UNIX socket accept loop that runs client workers.
- **Client Handler**: NDJSON protocol event processor and response writer.
- **Background Task Thread**: Verifier or summarizer thread tracked for clean
  daemon shutdown.
- **Reaper Loop**: Timer-based stale attempt recovery and transcript pruning.
- **Daemon State Paths**: Socket path, PID file, and temporary PID replacement
  path under AIT-owned directories.
- **Process Inspection**: PID command lookup and AIT daemon PID validation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `uv run pytest tests/test_daemon_lifecycle.py tests/test_daemon_reaper.py tests/test_daemon_concurrency.py tests/test_daemon_verifier_threads.py tests/test_daemon_e2e.py` passes unchanged.
- **SC-002**: Targeted daemon consumers pass: `tests/test_cli_adapters.py`,
  `tests/test_cli_run.py`, `tests/test_runner.py`, `tests/test_claude_code_hook.py`,
  `tests/test_codex_hook.py`, and `tests/test_gemini_hook.py`.
- **SC-003**: Full `uv run pytest`, full `PYTHONPATH=src python3 -m unittest
  discover -s tests`, and `git diff --check` pass.
- **SC-004**: `src/ait/daemon.py` is below 420 lines.
- **SC-005**: No new `src/ait/daemon_*.py` helper exceeds 400 lines.
- **SC-006**: Daemon helper modules do not import `ait.daemon`.
- **SC-007**: Public imports and patch surfaces named in Edge Cases remain
  available from `ait.daemon`.

## Assumptions

- This slice does not change CLI commands, daemon socket protocol envelopes,
  SQLite schema, generated hook resources, or public daemon JSON/text output.
- Existing tests are the compatibility baseline.
- New tests are added only for newly discovered bugs or compatibility gaps.
