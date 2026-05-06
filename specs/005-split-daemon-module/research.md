# Research: Split Daemon Module

## Decision: Keep `ait.daemon` As Public And Patch Surface

**Rationale**: Existing tests and integrations import public lifecycle
functions from `ait.daemon` and patch module-level names such as
`run_accept_loop`, `_handle_client`, `_verify_attempt_in_background`, and
`verify_attempt`. Keeping `daemon.py` as the orchestration surface preserves
these semantics.

**Alternatives considered**:

- Convert `ait.daemon` to a package. Rejected because import and patch behavior
  would be harder to preserve for a mechanical refactor.
- Move client handler and verifier thread code into helper modules. Rejected
  for this slice because those functions own established patch semantics.

## Decision: Extract Lifecycle/State/Reaper Before Client Protocol

**Rationale**: Lifecycle/status, stale cleanup, process inspection, path/config
lookup, and timed reaping are cohesive and can move without changing the daemon
protocol or test patch seams.

**Alternatives considered**:

- Split by runtime mode such as "server" and "cli". Rejected because the daemon
  lifecycle functions and CLI share low-level status/state helpers.
- Move only pure path helpers. Rejected because it would not materially reduce
  the oversized module or separate responsibility boundaries.

## Decision: Preserve Existing Tests As The Contract

**Rationale**: Daemon behavior spans subprocesses, UNIX sockets, SQLite writes,
threading, signal handling, stale cleanup, and runner fallback. Existing tests
cover those integration surfaces directly.

**Alternatives considered**:

- Rewrite tests around helper modules. Rejected because it would weaken
  behavior protection during a refactor.
