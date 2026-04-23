# CLAUDE.md

This file gives Claude Code the project-specific context it needs to work on this
repository safely and consistently. It mirrors the rules in `AGENT.md` but adds
the technical details Claude Code needs (stack, commands, layout, entry points).

When `AGENT.md` and this file disagree, treat them as equally authoritative and
ask before diverging.

## Project Overview

`ait` is an AI-agent-native VCS layer that sits on top of Git. It adds
structured intent tracking, isolated attempts, queryable execution history, and
durable linkage between attempts and Git commits. It is **not** a replacement
for Git.

Canonical specs live in `docs/`:

- `docs/ai-vcs-mvp-spec.md` — v1 spec (frozen surface)
- `docs/implementation-notes.md` — non-blocking clarifications and known limits
- `docs/protocol-appendix.md` — daemon protocol details
- `docs/implementation-plan.md` — milestones, acceptance criteria, breakdown
- `docs/parallel-development.md` — parallel work coordination

Treat the spec as the source of truth. If implementation and spec disagree, that
is a bug to be reviewed, not a silent divergence.

## Tech Stack

- Python `>=3.14` (see `pyproject.toml`)
- SQLite via stdlib `sqlite3`
- stdlib `unittest` for tests
- stdlib `argparse`, `socket`, `subprocess` — no runtime dependencies

The project must stay dependency-free unless a new dependency is explicitly
approved and documented.

## Repository Layout

```
src/ait/
  __init__.py
  cli.py                # argparse entry point (`ait ...`)
  app.py                # high-level operations (init/intent/attempt/show/...)
  config.py             # .ait dir bootstrap, install_nonce, local config
  repo.py               # git repo root resolution, repo_id derivation
  ids.py                # ULID generation
  hooks.py              # post-rewrite hook installer
  workspace.py          # worktree provisioning, commit helpers, ref updates
  daemon.py             # daemon process lifecycle (start/stop/serve)
  daemon_transport.py   # NDJSON unix socket transport
  protocol.py           # event envelope + payload schemas and validation
  events.py             # event handlers, dedupe, reaper, lifecycle updates
  verifier.py           # succeeded/promoted/failed determination
  query.py              # DSL parser, whitelisted fields, SQL lowering, blame
  reconcile.py          # post-rewrite reconciliation
  db/
    __init__.py         # re-exports
    core.py             # connect_db, run_migrations, meta table helpers
    schema.py           # migrations tuple, SCHEMA_VERSION
    repositories.py     # typed insert/get/list helpers per table
tests/
  test_*.py             # stdlib unittest
docs/                   # see above
AGENT.md                # base working rules
CLAUDE.md               # this file
pyproject.toml
```

## How to Run

Install in editable mode for CLI access:

```bash
pip install -e .
```

Run the full test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run a single test module:

```bash
PYTHONPATH=src python3 -m unittest tests.test_app_flow -v
```

Invoke the CLI without installing:

```bash
PYTHONPATH=src python3 -m ait.cli <command>
```

## Working Rules

These duplicate `AGENT.md` by design so Claude Code sees them in isolation.

1. Commit by small, self-contained functionality. Do not bundle unrelated work
   into one commit.
2. Every commit message must include the referenced document file names and
   paths, plus explicit keywords:
   `docs:../path/to/a.md,../path/to/b.md keyword:xxxx,oooo`
3. Review the change three times before every commit.
4. If a refactor need is discovered, write or update the refactor document
   immediately so future refactoring has a clear basis.
5. If attention quality drops, notify the user explicitly.
6. Keep documents concise. Do not let documents grow too long; split them when
   necessary.
7. Do not guess before development. Verify the facts and relevant context
   first, then implement.
8. Do not lie, fabricate, or falsify. No fake results, no fake completion, no
   fake data.
9. Use sub-agents actively for parallel development when parallel work is
   beneficial and appropriate.
10. Do not over-expand scope. Follow the documents, keep moving by phase, and
    avoid endless work that blocks the next stage.

## Commit Checklist

Before every commit Claude Code must confirm:

1. Scope is limited to one small feature or one tight logical unit.
2. Related docs are identified and listed in the commit message.
3. Keywords are included in the commit message.
4. Review pass 1 completed.
5. Review pass 2 completed.
6. Review pass 3 completed.
7. `PYTHONPATH=src python3 -m unittest discover -s tests` is green.

## Documentation Rules

1. Prefer short, focused documents.
2. Split documents when a single file becomes hard to review or maintain.
3. When architecture or implementation changes imply later refactoring, record
   that explicitly in docs.
4. Any spec-level behavior change must land in `docs/ai-vcs-mvp-spec.md` or
   `docs/implementation-notes.md` in the same PR as the code change.

## Integrity Rules

1. Never claim tests ran if they did not.
2. Never claim a feature is complete if it is partial.
3. Never invent data, logs, outputs, or review results.
4. When uncertain, stop and verify.

## Spec Alignment Checklist

When touching code in these modules, re-read the matching spec section first:

| Module | Spec section |
| --- | --- |
| `app.py` lifecycle handlers | `ai-vcs-mvp-spec.md` → Lifecycle, Intent Transition Rules |
| `events.py`, `daemon.py` | `protocol-appendix.md` + spec Harness Integration Protocol |
| `query.py` | spec Query And Indexing |
| `verifier.py` | spec Lifecycle → Attempt Lifecycle, Verification Rules |
| `db/schema.py` | spec Storage Mapping + Identity And Namespacing |
| `workspace.py` | spec Workspace Model |
| `hooks.py`, `reconcile.py` | spec Storage Mapping → Rewrite Reconciliation |

## Non-Goals

Do not add in v1:

- semantic diff or semantic merge
- agent-to-agent review or policy enforcement (schema extension points only)
- cross-machine sync of AI metadata
- non-Git backends

These are reserved as extension points in the spec.
