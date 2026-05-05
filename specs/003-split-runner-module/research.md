# Research: Split Runner Module

## Decision: Keep `ait.runner` As A Module

**Rationale**: Existing tests patch `ait.runner.start_daemon`,
`ait.runner._write_command_transcript`, `ait.runner._stage_all_changes`, and
other module-level symbols. Keeping `runner.py` as the orchestration module
preserves that patch surface.

**Alternatives considered**:

- Convert `ait.runner` to a package like `ait.query`. Rejected because
  `run_agent_command()` would likely execute inside a submodule, causing patches
  against facade symbols to stop affecting orchestration.

## Decision: Move Helpers That Do Not Own Patch Semantics

**Rationale**: PTY handling, context rendering, transcript persistence, and
semantic refusal checks are cohesive and can be imported into `runner.py`.
`runner.py` still calls imported module-level names, so patching those names in
`ait.runner` works for tests that need it.

**Alternatives considered**:

- Move `_finish_attempt_locally` into a helper module. Rejected because tests
  patch `ait.runner.utc_now` and call `_finish_attempt_locally`; moving it would
  break that established patch seam.
- Move `_write_command_transcript_best_effort`. Rejected because it must call
  the patchable `ait.runner._write_command_transcript` global.

## Decision: Preserve Existing Tests As The Contract

**Rationale**: Runner behavior spans subprocess execution, daemon fallback,
memory, reporting, transcripts, and Git commits. Existing tests are broad and
exercise the compatibility surface.

**Alternatives considered**:

- Rewrite tests around the new helper modules. Rejected because it would weaken
  public behavior protection for a mechanical refactor.
