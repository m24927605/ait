# ait Architecture Refactor Plan

## Purpose

This document records the large file-splitting refactor requested by the
2026-04-30 Staff review. It is intentionally a design document, not an
implementation patch. The current bugfix batch should keep behavior stable;
this refactor should be executed as a later mechanical series with full test
runs after each slice.

## Scope

The refactor covers four oversized areas:

- `src/ait/cli.py`
- `src/ait/memory.py`
- `src/ait/brain.py`
- `src/ait/db/repositories.py`
- `src/ait/report.py`

The file-size gate applies to all production modules, not only the initial
four target files. `src/ait/memory_eval.py` should be watched during this
work even though it is not currently the first split target.

Out of scope:

- changing public CLI behavior
- changing SQLite schema semantics
- changing memory ranking policy
- changing daemon protocol envelopes

## Target Module Layout

### CLI

Create `src/ait/cli/`:

- `__init__.py`: expose `main`
- `main.py`: root parser, root dispatch, shared error handling
- `init.py`: `init`, `bootstrap`, `doctor`, `status`, `repair`, `enable`
- `attempt.py`: attempt subcommands
- `intent.py`: intent subcommands
- `memory.py`: memory subcommands
- `graph.py`: graph/report commands
- `daemon.py`: daemon commands
- `shell.py`: shell integration
- `upgrade.py`: upgrade/install diagnostics

Compatibility:

- keep `python -m ait.cli` working through a thin shim during migration
- preserve all current command names, flags, output, and exit codes

### Memory

Create `src/ait/memory/`:

- `models.py`: dataclasses and typed records
- `policy.py`: policy loading, path/source checks
- `notes.py`: note CRUD and rendering
- `facts.py`: fact CRUD, supersession, validity
- `candidates.py`: candidate extraction and corroboration
- `recall.py`: search, temporal ranking, relevant memory rendering
- `importers.py`: agent memory import
- `lint.py`: memory lint and fix logic
- `eval.py`: retrieval evaluation

Introduce `MemoryRepository(conn)` and make high-level functions accept either
`repo_root` or an injected repository only at module boundaries. Internal
memory operations should not repeatedly call `connect_db + run_migrations`.
This repository seam must be introduced before moving read-only memory helpers
so extracted modules do not duplicate the current connection pattern.

Compatibility:

- keep `ait.memory` imports stable through re-export shims until one minor
  release after the refactor
- keep current SQLite table names and row formats unchanged

### Brain

Create `src/ait/brain/`:

- `build.py`: graph construction
- `render.py`: text/html/briefing rendering
- `store.py`: output file writes
- `models.py`: graph dataclasses

Remove reverse imports from `brain` into `app`. Callers should initialize the
repo before invoking brain builders.

Acceptance check:

- `grep -R -E "from ait\.app|import ait\.app" src/ait/brain*` returns empty

### Database Repositories

Split `src/ait/db/repositories.py`:

- `core_repositories.py`: intents, attempts, evidence, lifecycle core
- `memory_repositories.py`: memory notes/facts/edges/retrieval events
- `records.py`: shared dataclasses

Keep `ait.db` exports stable initially, but new code should import from the
specific repository module.

### Report

Create `src/ait/report/`:

- `models.py`: report dataclasses and typed records
- `status.py`: status report construction and serialization
- `graph.py`: graph report construction
- `html.py`: HTML rendering
- `health.py`: health checks and recommendations

Compatibility:

- keep `ait.report` imports stable through a shim during migration
- preserve report JSON keys and generated HTML structure unless a finding
  explicitly requires a behavior change

## Execution Plan

1. Add package skeletons and re-export shims with no logic movement.
2. Introduce `MemoryRepository` behind existing public functions.
3. Move memory read-only helpers, then write paths, then import/lint.
4. Move CLI parser/dispatcher one command family at a time.
5. Split brain rendering from graph building.
6. Split report status/graph/html/health modules.
7. Split database repository files and keep compatibility exports.
8. Remove compatibility shims only after one release cycle.

## Review Gates

Each slice must satisfy:

- no CLI output changes unless explicitly documented
- when CLI command surfaces move, update `docs/ai-vcs-mvp-spec.md` CLI Surface
  or document why no spec text changed
- `git diff --check`
- `wc -l src/ait/*.py src/ait/db/*.py | awk '$1 > 1000'` reviewed with any
  remaining large files justified in this document
- `grep -R -E "from ait\.app|import ait\.app" src/ait/brain*` stays empty
- targeted tests for touched command/module
- migration partial-apply tests remain green when DB repository code moves
- full `pytest`
- full `unittest discover`
- multi-process e2e tests for slices touching daemon, DB repositories, or
  workspace lifecycle

## Acceptance Criteria

- `cli.py` becomes a compatibility shim below 100 lines
- no production module exceeds 1,000 lines without documented reason
- `report.py` becomes a compatibility shim below 100 lines
- memory internals no longer open their own DB connection for every helper
- `brain` no longer imports from `app`
- all existing tests pass
- package public behavior remains backward compatible

## Rollback Strategy

Each slice must be independently revertible. If a package shim introduces an
import cycle or changes public imports, revert that slice and keep the old
single-file module until the dependency direction is corrected. Do not stack
logic movement on top of a failing shim.
