# Research: Split Adapters Module

## Decision: Keep `ait.adapters` As A Public Facade

**Rationale**: CLI parser code, CLI helpers, runner code, and tests import
`ADAPTERS`, result dataclasses, and public functions from `ait.adapters`.
Keeping `adapters.py` as a small facade preserves import compatibility while
allowing implementation code to move behind focused modules.

**Alternatives considered**:

- Convert `ait.adapters` to a package like `ait.query`. Rejected because a
  package conversion is unnecessary for this slice and increases compatibility
  risk for direct module imports.
- Move callers to new helper modules. Rejected because the public surface should
  remain stable during this refactor.

## Decision: Split By Adapter Responsibility, Not By Adapter Name

**Rationale**: The current coupling is between concern types: registry data,
settings/resource loading, wrapper generation, setup orchestration, and doctor
checks. Splitting by concern keeps shared behavior such as settings merge and
real binary discovery in one place.

**Alternatives considered**:

- Create one module per adapter. Rejected because it would duplicate shared
  settings merge, resource loading, wrapper, and doctor logic.
- Leave resource loading inside setup. Rejected because doctor checks also need
  resource existence and should not depend on setup writes.

## Decision: Share Wrapper Helpers Between Doctor And Setup

**Rationale**: Doctor and setup both need to reason about repo-local wrappers,
real agent binaries, and `.envrc`. A focused wrapper helper module avoids a
doctor/setup circular dependency and keeps subprocess/path concerns separate
from registry metadata.

**Alternatives considered**:

- Keep real binary checks in setup. Rejected because doctor must evaluate the
  same state without performing writes.
- Keep `.envrc` helpers in doctor. Rejected because setup owns the mutation path
  and doctor should remain read-only.

## Decision: Preserve Existing Tests As The Contract

**Rationale**: Adapter behavior spans CLI parser choices, JSON output,
generated hook files, generated settings, local shell wrappers, `.envrc`, and
temporary Git repositories. Existing tests exercise these compatibility
surfaces directly.

**Alternatives considered**:

- Rewrite tests around the new helper modules. Rejected because it would weaken
  the public behavior baseline for a mechanical refactor.
