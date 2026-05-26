# Slice 02: Release And Install Smoke Gates

狀態：Ready for implementation
目標：把 release checklist 中最關鍵的 PyPI/npm/wheel/install smoke 自動化，降低手動發版風險。

## Problem

目前 CI 主要跑 editable install 的 Python tests 與 3 個 npm unit tests。Publish workflow
只 build distributions 並 publish PyPI。Release checklist 已要求 `twine check`、
fresh wheel smoke、npm pack dry-run、PyPI smoke、global npm smoke，但這些尚未成為
required automated gate。

Python 3.14+ 也讓 install path 更脆弱；npm postinstall 會安裝同版 PyPI package，
因此 PyPI/npm 版本不同步會直接造成使用者安裝失敗。

## Objective

新增 release/install smoke gate：

- Build wheel/sdist and run `twine check`.
- Install built wheel into fresh venv and run CLI smoke.
- Run npm pack smoke before publish.
- Run npm package install smoke against local tarball.
- Validate PyPI/npm version ordering and package metadata consistency.
- Preserve manual checklist, but move must-pass items into CI/release workflows.

## Files To Change

- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
- `docs/release-checklist.md`
- `npm/ait-vcs/test/**` or new package smoke script
- optional `scripts/release-smoke/**`

## Files Not To Change

- Core attempt/apply/recover behavior
- SQLite schema
- Docs positioning except release checklist updates
- Product source files unless package smoke needs a tiny helper

## Design

Add three automation layers:

1. PR CI release-smoke job
   - `python -m build`
   - `python -m twine check dist/*`
   - install wheel into temp venv
   - run `ait --version`, `ait init --no-shell-install`, `ait status --no-interactive`
   - run a shell adapter attempt in a temp Git repo and `ait apply latest`

2. npm local package smoke
   - `npm --prefix npm/ait-vcs test`
   - `npm pack --dry-run`
   - `npm pack`
   - install tarball into isolated temp prefix
   - run `ait --version`
   - verify postinstall error is actionable when Python 3.14 is unavailable

3. Publish workflow guard
   - Build and smoke before PyPI publish.
   - Do not automate npm publish until PyPI version availability can be checked.
   - Add an explicit check that npm package version equals `pyproject.toml`.

## Python Version Strategy

This slice does not decide whether to lower `requires-python`.
It must make the current requirement honest:

- Failure message must say Python 3.14+ is required.
- Installer must recommend one direct remediation path.
- Release smoke must run with Python 3.14.
- A follow-up product decision can lower the minimum to 3.12/3.13 if feasible.

## Tests

Required tests:

1. `test_npm_installer_reports_missing_python_actionably`
   - Simulate no Python 3.14 candidates.
   - Assert message includes Python 3.14+ and a next step.

2. `test_package_versions_match`
   - Compare `pyproject.toml` and `npm/ait-vcs/package.json`.

3. `test_wheel_smoke_script_runs_fresh_repo`
   - Install built wheel in temp venv.
   - Run init/status/run/apply smoke.

4. `test_npm_pack_contains_expected_files`
   - Assert package includes bin/scripts/README and not repo internals.

## Verification Commands

```bash
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py tests/test_landing.py -q
python3.14 -m build
python3.14 -m twine check dist/*
npm --prefix npm/ait-vcs test
(cd npm/ait-vcs && npm pack --dry-run)
```

If `twine` or `build` is not installed locally, use an isolated CI job or `uvx`.

## Acceptance

- CI fails if the wheel cannot be installed and used from a fresh venv.
- CI fails if npm package metadata/version drifts from Python package metadata.
- Publish workflow does not upload to PyPI before build/check/smoke passes.
- Release checklist references the automated gate instead of leaving all checks manual.
- npm install failure for missing Python is actionable.

## Review Checklist

- Confirm workflows do not publish npm before PyPI version exists.
- Confirm smoke tests use installed artifacts, not editable source import.
- Confirm temp repos use temp HOME and do not modify developer shell rc.
- Confirm secrets/tokens are not printed in workflow logs.

## Rollback

Release-smoke workflow changes can be reverted without user data impact.
Do not remove manual checklist entries until automated gates have passed in CI at least once.

