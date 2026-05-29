# CI/CD Optimization Design

Date: 2026-05-29
Scope: cut wall-clock time and runner-minute cost of `.github/workflows/`
without losing test coverage or release safety.

## Problem

The maintainer personally pays for GitHub Actions usage. Recent observation
across the last ~30 runs:

| Workflow | Avg duration | Cost driver |
|---|---|---|
| `docs.yml` | ~40 s | fine |
| `publish.yml` | ~55 s | fine |
| `ci.yml` | 2–3 min | runs on every push AND every PR; pip + deps reinstalled each time |
| `release-binary.yml` | **25–40+ min** | 4-platform matrix, macOS @ 10× minute multiplier, macos-13 queue + slow runner |

The single biggest cost item is the macOS Intel runner (`macos-13`):
GH-hosted Intel Mac queue routinely sits 15–30 minutes before the job
even starts, then bills at 10× the Linux multiplier once it runs. The
v1.6.0 build sat queued 41 minutes before we cancelled it; v1.6.1 sat
25 minutes before we cancelled.

Secondary cost contributors:

- `ci.yml` fires on **both** `push` and `pull_request`, so every PR
  produces two runs (push to feature branch + PR open).
- No pip / setup-python cache → each job reinstalls `pyinstaller`,
  `build`, `twine`, and `-e .` from scratch.
- All 1021 tests run on every push even though `pytest_collection_modifyitems`
  in `tests/conftest.py` auto-marks 94 of them as `slow / daemon / subprocess`.
  The fast-path marker filter that already exists per
  `docs/release-checklist.md` is not used by CI.
- `release-binary.yml` fires on every `release: published` event,
  including docs-only releases that don't change any binary.
- No `concurrency` cap → rapid pushes queue redundant runs of the
  superseded commits.

Separately, recent CI (1.5.1 onward) has been failing because the
`conftest.py` global `AIT_BUG_REPORT=never` (added to stop test runs
polluting `~/.local/state/ait/bug_reports/`) also disables the four
bug-report tests that need the pipeline alive to assert on it.

## Goal

Reduce per-release CI cost to a level the maintainer is willing to pay.
Concretely:

1. Stop spending macOS Intel runner minutes by default.
2. Halve the per-PR `ci.yml` runs (eliminate the push+PR duplicate).
3. Cache pip dependencies so the same deps don't get redownloaded
   every job.
4. Allow rapid pushes to cancel their own prior runs.
5. Stop firing `release-binary.yml` on releases that don't ship a binary.
6. Use the existing pytest marker split for PR-fast-path vs.
   release-gate full suite.

Also, fix the failing bug-report tests so CI goes green again — that's
a reliability prerequisite, not a perf gain, but it gates the value of
running CI at all.

## Non-goals (this change)

- No new test cases.
- No restructuring of the existing matrix beyond dropping `macos-13`.
- Apple Silicon support is preserved; macOS Intel users keep working
  through pip.
- No move off GitHub-hosted runners onto self-hosted.
- No paid larger-runner usage.
- Not adding a Windows target.

## Design

### Item 1 — Drop `macos-13` from `release-binary.yml`

The single biggest line item.

`.github/workflows/release-binary.yml`:

```yaml
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: macos-latest          # macos-arm64 — keep
            target: macos-arm64
          # - os: macos-13             # macos-x86_64 — DROP for now
          #   target: macos-x86_64
          - os: ubuntu-latest          # linux-x86_64 — keep
            target: linux-x86_64
          - os: ubuntu-24.04-arm       # linux-arm64 — keep
            target: linux-arm64
```

Three downstream files need a matching note:

- `scripts/release-smoke/render_brew_formula.py` (`TARGETS` tuple
  drops `"macos-x86_64"`)
- `scripts/release-smoke/binary_smoke.py` (no change — accepts any
  platform)
- `docs/install.md` (platforms table: mark `macos-x86_64` as "use pip
  on Intel Macs")
- `install.sh` (the `darwin/x86_64` branch should print a clear
  message recommending pip instead of failing with a download 404)
- `scripts/homebrew-tap-template/Formula/ait.rb` (drop the `on_intel`
  block under `on_macos`)

Recovery: if later we want Intel Mac binaries back, add the matrix
entry and the renderer/install paths together. Code stays ready.

### Item 2 — Stop the push+PR duplicate in `ci.yml`

`.github/workflows/ci.yml`:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

Effect: a feature branch push triggers only when the branch is `main`
(zero overhead during normal feature work). The PR triggers run on
PR open / sync. On merge, the resulting push to `main` runs once.

Saves: one full `ci.yml` run per push to a feature branch (currently
duplicated).

### Item 3 — pip cache in `setup-python`

All four workflows use `actions/setup-python@v6`. Add `cache: pip` and
a dependency manifest so the cache invalidates cleanly:

```yaml
- uses: actions/setup-python@v6
  with:
    python-version: "3.14"
    cache: pip
    cache-dependency-path: |
      pyproject.toml
```

Apply to:

- `ci.yml` (test job, release-smoke job)
- `publish.yml` (build job)
- `release-binary.yml` (each matrix job)
- `docs.yml` (build job)

PyInstaller, `build`, `twine`, and the editable install all benefit.

Saves: 20-60 s per job. release-binary.yml has 3 matrix jobs (post
item 1) → ~1–3 minutes per release on that workflow alone.

### Item 4 — Cancel in-flight superseded runs via `concurrency`

Top-level in each workflow (push triggers only — release/manual
dispatch should NOT cancel):

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'push' || github.event_name == 'pull_request' }}
```

Apply to: `ci.yml`, `docs.yml`. Leave `publish.yml` and
`release-binary.yml` without `cancel-in-progress` so a release tag
doesn't get cancelled mid-flight by another release.

Saves: variable. On rapid-iteration days (5+ pushes/hour), removes 50%+
of wasted runs.

### Item 5 — Make `release-binary.yml` opt-in instead of automatic

Right now `release-binary.yml` triggers on every `release: published`
event. Many releases don't change the binary (docs, CI tweaks, version
bumps). Switch it to require an opt-in:

Option A — `workflow_dispatch` only:

```yaml
on:
  workflow_dispatch:
    inputs:
      tag:
        description: "Release tag to build for (e.g. v1.6.2)."
        required: true
```

Pros: zero accidental fires. Cons: every binary release needs an extra
`gh workflow run` step.

Option B — release with a label:

```yaml
on:
  release:
    types: [released]   # only when explicitly "released" not "pre-released"
  workflow_dispatch:
    inputs:
      tag:
        description: "Release tag (workflow_dispatch only)"
        required: true

jobs:
  build:
    if: |
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.release.body, '<!-- ship-binary -->')
```

Pros: stays automatic for binary releases. Cons: maintainer needs to
remember the marker.

**Recommendation: Option A**. The maintainer explicitly does not want
automatic CI/CD runs. Binary releases become a deliberate
`gh workflow run release-binary.yml -f tag=vX.Y.Z` action.

### Item 6 — Split fast PR path from release-gate full suite

`tests/conftest.py:181`'s `pytest_collection_modifyitems` already
auto-marks tests by filename pattern. The markers exist; nothing uses
them.

`ci.yml` test job:

```yaml
- name: Run fast PR tests
  run: pytest -q -m "not (slow or daemon or subprocess or release)"
```

`publish.yml` (already release-gated):

```yaml
- name: Run release gate
  run: pytest -q   # full suite
```

Saves: 30–60 s on every CI test job. Important: ensure the auto-mark
logic in conftest is still actively assigning markers — see "Open
Questions" below.

### Item 7 (reliability, blocks CI being meaningful) — Fix bug-report test conftest

Recent CI fails on 4 tests:

```
tests/bug_report/test_api.py::ApiTests::test_report_internal_error_appends_to_collector
tests/bug_report/test_end_to_end_flow.py::EndToEndTests::test_non_tty_flush_writes_pending
tests/bug_report/test_excepthook.py::ExcepthookTests::test_install_records_ait_exception
tests/bug_report/test_layer2_instrumentation.py::Layer2Tests::test_each_layer2_category_records
```

Root cause: `tests/conftest.py` sets `AIT_BUG_REPORT=never` globally
to stop test-suite subprocess runs from polluting `~/.local/state/`.
That same env var disables the very pipeline the four bug-report tests
need to assert on. The bug-report tests pass locally because of subtle
fixture differences; CI's clean env exposes the bug.

Fix: change the global conftest setting to be applied via fixture
that the bug-report tests can OVERRIDE. Two viable approaches:

1. **fixture-scoped env**: replace the `monkeypatch.setenv("AIT_BUG_REPORT", "never")`
   in conftest with a fixture that yields, then the bug-report tests
   request a counter-fixture that unsets it.
2. **inverse**: keep conftest unchanged, have each affected bug-report
   test explicitly `monkeypatch.delenv("AIT_BUG_REPORT", raising=False)`
   in their own setUp.

**Recommendation: approach 2**. Smaller surface area; the four tests
that need the pipeline are the ones that opt back in. Adds 4 lines.

## Roll-out order

Items are independent except for #1 cascading into renderer/install
script changes. Suggested order matches priority/risk:

1. **Item 7** (CI reliability) — small, makes CI useful again
2. **Item 2** (push+PR de-dup) — 4-line change, zero risk
3. **Item 4** (`concurrency`) — 3-line change, zero risk
4. **Item 3** (pip cache) — apply to all 4 workflows
5. **Item 6** (pytest -m split) — small change
6. **Item 1** (drop macos-13) — largest cost saving, requires
   coordinated changes in renderer + install.sh + tap template + docs
7. **Item 5** (release-binary opt-in) — last because it changes the
   release procedure; should be paired with a `docs/release-checklist.md`
   update

## Verification (per item, no actual CI runs)

Since the maintainer does not want to spend CI minutes verifying CI
config changes, everything below is **local-only** or **dry-run**.

- **Item 1**: `grep -n macos-13 .github/workflows/release-binary.yml`
  returns nothing. `python scripts/release-smoke/render_brew_formula.py
  --version v1.6.2 --checksums /tmp/sums.txt --output /tmp/x.rb` with
  a 3-line `sums.txt` succeeds (no error about missing `macos-x86_64`).
- **Item 2**: visually verify `ci.yml` `on:` block now has `branches: [main]`
  under both `push` and `pull_request`.
- **Item 3**: `actionlint .github/workflows/*.yml` (if installed) shows
  no errors.
- **Item 4**: visual check the `concurrency:` block is only on `ci.yml`
  and `docs.yml`, not on `publish.yml` or `release-binary.yml`.
- **Item 5**: `grep -n 'on:' .github/workflows/release-binary.yml` shows
  only `workflow_dispatch`, not `release`.
- **Item 6**: locally
  `PYTHONPATH=src:tests .venv/bin/python -m pytest -q -m "not (slow or daemon or subprocess or release)"`
  passes and takes meaningfully less time than the full suite.
- **Item 7**: locally, the four bug-report tests pass with
  `AIT_BUG_REPORT` either set OR unset.

The first real CI hit only happens when the maintainer next chooses
to ship a release.

## Open questions

1. **Marker auto-assignment in conftest** — needs a spot-check that
   `pytest_collection_modifyitems` still classifies the test files we
   think it does. Auto-marking by filename is fragile (rename a file →
   the marker stops applying). Worth replacing with explicit
   `@pytest.mark.slow` decorators on those modules? Out of scope for
   this spec, log as follow-up.

2. **Item 5 vs. maintainer convenience** — switching to
   `workflow_dispatch`-only means every binary release needs an extra
   step. If the maintainer prefers the old auto-on-release behavior
   (despite paying for it), revisit Item 5 and adopt the label-gated
   Option B instead.

## Non-functional checks

- Total CI runs eliminated per release once items 1+2+4+5 land:
  - macOS Intel: 1 → 0 builds (saves the 30+ min queue + 10× minutes)
  - Release-binary on docs releases: full pipeline → no pipeline
  - PR push duplicates: 2 → 1 ci.yml run
  - Superseded pushes on rapid iteration: ~2-3 wasted runs cancelled
- Cost ceiling per binary release after item 1:
  - 1× macOS Apple Silicon job (10× multiplier, ~2 min wall) ≈ 20
    minute-units
  - 2× Linux jobs (1× multiplier, ~1 min wall each) ≈ 2 minute-units
  - Total ≈ 22 minute-units, down from 50+ today

## References

- `.github/workflows/ci.yml`
- `.github/workflows/release-binary.yml`
- `.github/workflows/publish.yml`
- `.github/workflows/docs.yml`
- `tests/conftest.py`
- `pyproject.toml` (`[tool.pytest.ini_options].markers`)
- `docs/release-checklist.md`
- `~/.claude/projects/-Users-michael-chen-products-ait/memory/feedback_no_github_cicd_runs.md`
  — explicit user rule that CI/CD must not be auto-triggered
