# Lower Python Floor to 3.11

Date: 2026-05-29
Scope: drop `requires-python` from `>=3.14` to `>=3.11`, update docs, and
verify the existing test suite passes on Python 3.11. No code changes.

## Problem

`pyproject.toml` sets `requires-python = ">=3.14"`, but the codebase only
uses features available since Python 3.11:

- `tomllib` (stdlib in 3.11+)
- `from datetime import UTC` (3.11+)

No 3.12-only, 3.13-only, or 3.14-only syntax or stdlib is used anywhere in
`src/ait/`. Grep evidence:

| Feature | Earliest Python | Used in codebase? |
|---|---|---|
| `tomllib` | 3.11 | yes — 7 files |
| `datetime.UTC` | 3.11 | yes — 17+ files |
| PEP 695 inline generics `def f[T](...)` | 3.12 | no |
| `@override` | 3.12 | no |
| `pathlib.Path.walk` | 3.12 | no |
| `itertools.batched` | 3.12 | no |
| `except*` / `ExceptionGroup` | 3.11 | no |
| PEP 750 t-strings | 3.14 | no |
| PEP 758 `except expr as ...` | 3.14 | no |

The `>=3.14` floor is therefore unnecessarily restrictive. It blocks every
user whose default `python3` is older than 3.14 — which is most macOS,
Ubuntu, Debian, and CI environments today (Python 3.14 was released
2025-10). Errors at install time look like:

```
ERROR: Package 'ait-vcs' requires a different Python: 3.9.6 not in '>=3.14'
```

This UX cliff was flagged in `docs/ait-rebrand-qa-reality.md` and
`docs/ait-rebrand-qa-report.md` (H6 row).

## Goal

Move the pip-install path's Python floor to the codebase's true minimum
(3.11) so install works out of the box for the vast majority of users.

## Non-goals

- Standalone binary release pipeline — that's a separate, larger project
  (Spec B, brainstormed next).
- 3.10 or earlier support — would require rewriting `datetime.UTC` usage
  to `datetime.timezone.utc` and replacing `tomllib` with `tomli` (or a
  conditional import). The 3.10 user base is shrinking; not worth the
  churn.
- CI matrix setup — the project currently has no CI. Spec deliberately
  declines to introduce one in this change. Verification remains a manual
  pre-release step.
- Any code changes — this spec is purely metadata and documentation.

## Design

### Change 1: `pyproject.toml`

```toml
requires-python = ">=3.11"
```

Add classifiers for the now-supported versions:

```toml
classifiers = [
  # ...existing...
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
]
```

(If a `Programming Language :: Python :: 3.14` line already exists,
keep it. Add the others. Order ascending.)

### Change 2: Documentation sweep

Every document that says "Python 3.14" or "python3.14" needs review.
Default: change to "Python 3.11+" or generalize the command to `python3`.
Exceptions: release tooling commands that the maintainer literally runs
with `python3.14` can stay as-is but should be footnoted.

Inventory:

| File | Line(s) | Current | Replacement |
|---|---|---|---|
| `pyproject.toml` | 11 | `requires-python = ">=3.14"` | `requires-python = ">=3.11"` |
| `pyproject.toml` | classifiers block | (no Python version classifiers) | add 3.11–3.14 entries |
| `docs/launch-kit-2026.md` | 50–51, 217, 309–310, 426–427, 451, 501 | "Python 3.14+" | "Python 3.11+" |
| `docs/claude-code-live-smoke.md` | 10 | "Python 3.14" | "Python 3.11+" |
| `docs/release-checklist.md` | 69–75 | `python3.14 -m build` etc. | keep `python3.14` literal; add a footnote "any Python ≥ 3.11 works; 3.14 is the maintainer's local default" |
| `docs/ait-hero-demo-recording-plan.md` | 61 | "Python 3.14+" | "Python 3.11+" |
| `docs/seo-strategy.md` | 63 | "Python 3.14+" inside product blurb | "Python 3.11+" |
| `docs/ai-vcs-mvp-spec.md` | 53 | "Python 3.14 ships a newer SQLite" | rewrite: "Python 3.11+ ships SQLite ≥ 3.39 which meets the 3.35 floor" |
| `docs/ait-rebrand-qa-reality.md` | 44 (H6 concern) | open issue describing the cliff | append "Resolved 2026-05-29 by lowering floor to 3.11." |
| `docs/ait-rebrand-qa-report.md` | 41 (H6 row) | "Reality" column flags 3.14 cliff | replace cell with "Resolved 2026-05-29 — floor lowered to 3.11." |
| `docs/getting-started.md` | search & update if mentions 3.14 | "Python 3.14" | "Python 3.11+" |

Check `README.md` too — same sweep.

### Change 3: CHANGELOG

Add to `CHANGELOG.md` (or equivalent):

```
## [Unreleased]
### Changed
- Lowered Python floor from 3.14 to 3.11. The codebase never used any
  3.12+ stdlib or syntax; the 3.14 minimum was unnecessarily restrictive
  and blocked most users at install time. No code changes — only
  metadata and documentation.
```

(Use the project's existing CHANGELOG style — see prior 1.4.3 entry as
reference.)

### Verification

Before tagging the release:

1. Create a clean Python 3.11 virtual environment outside the project's
   own `.venv`:

   ```bash
   /opt/homebrew/opt/python@3.11/bin/python3.11 -m venv /tmp/ait_311_check
   /tmp/ait_311_check/bin/pip install -e .
   /tmp/ait_311_check/bin/pip install pytest build
   PYTHONPATH=src /tmp/ait_311_check/bin/python -m unittest discover -s tests
   ```

   (Path adjusts for whichever Python 3.11 install the maintainer has —
   pyenv, asdf, brew `python@3.11`, etc.)

2. Expected: 955+ tests OK with exit 0. Any failure is a real regression
   and must be diagnosed before merging the change.

3. As a bonus sanity check, repeat with 3.12 and 3.13 if those Pythons
   are locally available. Failures on 3.12/3.13 would indicate the
   codebase actually does use a 3.14-only feature that the grep missed.

### Release sequence

This is a feature-level user-visible change to install requirements →
bumps the minor version per semver.

1. Bump `version = "1.5.0"` in `pyproject.toml`.
2. CHANGELOG entry under `## [1.5.0] - 2026-05-29`.
3. Commit the docs sweep, the pyproject change, and the CHANGELOG in
   either one or two commits (the maintainer's preference; both follow
   CLAUDE.md's "small self-contained unit" rule).
4. Verify on a clean 3.11 venv (see "Verification" above).
5. Tag `v1.5.0` per `docs/release-checklist.md`.

## Risk

Very low.

- Codebase grep is exhaustive for the suspect 3.12+ features.
- The change is metadata + docs only — zero code touched.
- The fallback path is trivial: revert the `pyproject.toml` edit if
  unexpected 3.11 incompatibilities surface during verification.

The one realistic failure mode is a transitive issue in the test
fixtures (e.g., a test uses a 3.12+ helper). If that happens, fix in the
same PR — the test is the bug, not the floor lowering.

## References

- `docs/ait-rebrand-qa-reality.md` — where the cliff was first flagged
- `docs/ait-rebrand-qa-report.md` H6 — bug-tracker-style entry
- `pyproject.toml` — the single line driving the install error
- `CLAUDE.md` — commit checklist and message format
- `docs/superpowers/specs/2026-05-29-standalone-binary-design.md` (next)
  — the larger sibling project for the binary path
