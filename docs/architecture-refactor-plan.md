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

### Database Repositories

Split `src/ait/db/repositories.py`:

- `core_repositories.py`: intents, attempts, evidence, lifecycle core
- `memory_repositories.py`: memory notes/facts/edges/retrieval events
- `records.py`: shared dataclasses

Keep `ait.db` exports stable initially, but new code should import from the
specific repository module.

## Execution Plan

1. Add package skeletons and re-export shims with no logic movement.
2. Move CLI parser/dispatcher one command family at a time.
3. Move memory read-only helpers first, then write paths, then import/lint.
4. Introduce `MemoryRepository` behind existing public functions.
5. Split brain rendering from graph building.
6. Split database repository files and keep compatibility exports.
7. Remove compatibility shims only after one release cycle.

## Review Gates

Each slice must satisfy:

- no CLI output changes unless explicitly documented
- `git diff --check`
- targeted tests for touched command/module
- full `pytest`
- full `unittest discover`

## Acceptance Criteria

- `cli.py` becomes a compatibility shim below 100 lines
- no production module exceeds 1,000 lines without documented reason
- memory internals no longer open their own DB connection for every helper
- `brain` no longer imports from `app`
- all existing tests pass
- package public behavior remains backward compatible
