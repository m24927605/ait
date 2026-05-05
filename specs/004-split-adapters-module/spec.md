# Feature Specification: Split Adapters Module

**Feature Branch**: `004-split-adapters-module`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Refactor the oversized adapters module into cohesive models, registry, doctor, setup, resource, and wrapper modules while preserving ait.adapters public imports, CLI adapter behavior, native hook setup, and automation bootstrap behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Adapter Discovery And CLI Behavior (Priority: P1)

As an AIT user, I want adapter listing, lookup, status, hints, and CLI adapter
commands to behave exactly as before, so that existing workflows for Claude
Code, Codex, Gemini, Cursor, and Aider remain compatible.

**Why this priority**: Adapter metadata feeds multiple CLI paths and command
parsers. A behavior change here would affect users before any setup action runs.

**Independent Test**: Run adapter and adapter-consuming CLI tests after the
split. Existing public imports from `ait.adapters` and `ADAPTERS` must continue
to work unchanged.

**Acceptance Scenarios**:

1. **Given** a supported adapter name or alias, **When** adapter lookup runs,
   **Then** the same adapter metadata and errors are returned as before.
2. **Given** CLI commands display adapter status, hints, or setup choices,
   **When** they import from `ait.adapters`, **Then** command behavior and
   formatting remain compatible.
3. **Given** external code imports public adapter dataclasses and functions
   from `ait.adapters`, **When** those imports are evaluated, **Then** they
   still succeed without package migration changes.

---

### User Story 2 - Preserve Setup, Bootstrap, And Doctor Behavior (Priority: P1)

As an AIT user, I want native hook setup, automation bootstrap, `.envrc`
updates, wrapper generation, and doctor checks to keep their current behavior,
so that refactoring does not change local repository setup or shell behavior.

**Why this priority**: Setup and doctor code touches repository files, shell
configuration, generated hook resources, and real agent binary detection.

**Independent Test**: Run adapter setup, native hook, and CLI adapter tests
against temporary repositories. Existing tests must pass unchanged.

**Acceptance Scenarios**:

1. **Given** a repository without native hooks, **When** adapter setup runs,
   **Then** the same files are written with the same idempotent behavior.
2. **Given** automation bootstrap is requested, **When** wrappers and `.envrc`
   are generated, **Then** doctor checks report the same ready/missing state as
   before.
3. **Given** generated settings already exist, **When** setup merges new
   settings, **Then** existing user-owned settings are preserved.

---

### User Story 3 - Make Adapter Internals Cohesive (Priority: P2)

As a maintainer, I want adapter models, registry metadata, resource loading,
settings merging, doctor checks, wrapper helpers, and setup orchestration split
by responsibility, so that future adapter changes stay local to the relevant
module.

**Why this priority**: `src/ait/adapters.py` currently combines dataclasses,
registry data, filesystem writes, JSON merging, shell snippets, real binary
discovery, and status checks in one oversized module.

**Independent Test**: Inspect module boundaries and run architecture gates.
`src/ait/adapters.py` becomes a small compatibility facade while focused helper
modules each own one responsibility.

**Acceptance Scenarios**:

1. **Given** a maintainer inspects adapter code, **When** the refactor is
   complete, **Then** registry data, resource loading, doctor checks, setup
   orchestration, and wrapper helpers are not implemented in one file.
2. **Given** line-count and dependency-direction gates run, **When** the
   refactor is complete, **Then** the adapter facade and helper modules satisfy
   the documented thresholds and helper modules do not import the facade.

### Edge Cases

- Unknown adapter names still raise `AdapterError` with the existing supported
  adapter wording.
- Setup remains idempotent for existing hook files, generated settings files,
  wrappers, and `.envrc`.
- Generated JSON settings still merge nested dictionaries without deleting
  unrelated user values.
- Real binary discovery still avoids selecting AIT-generated wrappers as the
  real agent binary.
- Automation doctor results still report adapter doctor checks alongside
  wrapper, `.envrc`, and real binary checks.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST keep public imports from `ait.adapters` compatible for
  adapter dataclasses, result dataclasses, `ADAPTERS`, and public functions.
- **FR-002**: AIT MUST keep adapter lookup, alias handling, listing order, and
  unknown-adapter errors compatible.
- **FR-003**: AIT MUST keep CLI adapter/status/hint/init/runtime/memory/query
  helper behavior compatible.
- **FR-004**: AIT MUST keep native hook setup behavior compatible for Claude
  Code, Codex, Gemini, Cursor, and Aider resources.
- **FR-005**: AIT MUST keep automation bootstrap, shell snippet, wrapper, and
  `.envrc` behavior compatible.
- **FR-006**: AIT MUST keep adapter doctor and automation doctor result fields,
  `.ok` behavior, and check semantics compatible.
- **FR-007**: Adapter dataclasses and `AdapterError` MUST move to a focused
  model module.
- **FR-008**: Adapter registry metadata and lookup/listing behavior MUST move
  to a focused registry module.
- **FR-009**: Resource loading, JSON settings generation, and settings merge
  behavior MUST move to focused helper modules.
- **FR-010**: Doctor checks MUST move to a focused doctor module that does not
  own setup writes.
- **FR-011**: Wrapper and `.envrc` helper behavior MUST move to focused helper
  code shared by doctor/setup flows without circular facade imports.
- **FR-012**: Setup/bootstrap orchestration MUST move to a focused setup module
  while `src/ait/adapters.py` remains the public compatibility facade.
- **FR-013**: If an adapter bug is discovered during extraction, it MUST be
  fixed in the same slice with a regression test.

### Key Entities *(include if feature involves data)*

- **AgentAdapter**: Public metadata describing one supported agent adapter.
- **AdapterDoctorCheck**: Public check result for one doctor condition.
- **AdapterDoctorResult**: Public aggregate doctor result for adapter setup.
- **AutomationDoctorResult**: Public aggregate doctor result for wrapper and
  shell automation readiness.
- **AdapterSetupResult**: Public result describing setup writes.
- **AdapterBootstrapResult**: Public result describing bootstrap output.
- **AdapterAutoEnableResult**: Public result describing automatic enablement.
- **Adapter Registry**: Supported adapter metadata keyed by canonical name and
  aliases.
- **Adapter Resource**: Generated hook, settings, or command content loaded
  from packaged resources.
- **Wrapper Environment**: Generated wrapper scripts, `.envrc`, and real agent
  binary discovery state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `uv run pytest tests/test_adapters.py` passes unchanged.
- **SC-002**: Targeted adapter consumers pass: `tests/test_cli_adapters.py`,
  `tests/test_claude_code_hook.py`, `tests/test_codex_hook.py`, and
  `tests/test_gemini_hook.py`.
- **SC-003**: Full `uv run pytest`, full `PYTHONPATH=src python3 -m unittest
  discover -s tests`, and `git diff --check` pass.
- **SC-004**: `src/ait/adapters.py` is below 150 lines and acts only as the
  public compatibility facade.
- **SC-005**: No new `src/ait/adapter_*.py` helper exceeds 400 lines.
- **SC-006**: Adapter helper modules do not import `ait.adapters`.
- **SC-007**: Public imports named in the contract remain available from
  `ait.adapters`.

## Assumptions

- This slice does not change CLI flags, CLI output contracts, generated
  resource file contents, shell commands, or adapter support policy.
- Existing tests are the compatibility baseline.
- New tests are added only for newly discovered bugs or compatibility gaps.
