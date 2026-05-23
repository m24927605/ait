# Release Checklist

## Test Runtime Tiers

Pytest markers are registered in `pyproject.toml` and assigned in
`tests/conftest.py` so local development can skip the measured slow/release
families without changing the full release gate.

Fast local loop:

```bash
PYTHONPATH=src .venv/bin/pytest -m "not slow and not release" -q
```

Full release gate:

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

Optional parallel smoke, when `pytest-xdist` is installed:

```bash
PYTHONPATH=src .venv/bin/pytest -m "not serial" -n auto --dist=loadscope -q
PYTHONPATH=src .venv/bin/pytest -m serial -q
```

## SEO Drift Audit

Before any release that touches user-facing copy, verify the canonical
messaging architecture defined in [docs/seo-strategy.md](seo-strategy.md):

1. `mkdocs.yml site_description` matches the canonical L string.
2. `pyproject.toml` `description` matches canonical M.
3. `npm/ait-vcs/package.json` `description` matches canonical M.
4. README hero subhead and lead paragraph use canonical L.
5. `site-docs/llms.txt` blockquote matches canonical L (and all
   linked URLs return HTTP 200).
6. `overrides/main.html` JSON-LD `description` inherits from
   `config.site_description` (no hardcoded copy).
7. `softwareVersion` is **not** present in JSON-LD (drift hazard).
8. `pyproject.toml` and `npm/ait-vcs/package.json` versions match
   the intended Git tag.

If any line drifts, fix before tagging.

## Review Orchestration Release Gate

Any release that changes AIT Risk-Based Pre-Apply Review Orchestration
must pass this gate before tagging or uploading to PyPI. This gate is
required when the change touches any of:

- `src/ait/review*.py`
- `src/ait/cli/review.py`
- `src/ait/landing.py`
- `src/ait/query/*`
- `src/ait/report/*`
- `src/ait/db/schema.py`
- `src/ait/db/*review*`
- review policy, adapter, queue, benchmark, or finding lifecycle tests

Required checks:

1. Confirm review remains disabled by default unless CLI flags or repo
   policy opt in.
2. Confirm review failures never write `verified_status=failed`.
3. Confirm stale, malformed, missing, queued, running, failed, or blocked
   required reviews fail closed for auto apply.
4. Confirm human override is recorded as `overridden`; do not rewrite the
   original review or finding as `passed`.
5. Confirm reviewer adapters run as local configured commands only; AIT
   core must not gain direct network access or provider SDK calls.
6. Confirm reviewer adapters do not write the target attempt workspace.
7. Confirm trusted baseline snapshots exclude candidate, stale, and
   policy-blocked memory.
8. Confirm `ait query` review/finding fields are stable and do not crash
   when an attempt has no review rows.
9. Confirm benchmark fixtures run with fake reviewers and do not require a
   real LLM or network.

Recommended targeted commands:

```bash
PYTHONPATH=src uv run pytest tests/test_review_*.py -q
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_landing.py tests/test_cli_run_review.py -q
PYTHONPATH=src uv run pytest tests/test_query.py tests/test_review_query.py tests/test_review_query_dsl.py -q
PYTHONPATH=src uv run pytest tests/test_config.py tests/test_db_migrations.py -q
PYTHONPATH=src uv run python -m compileall -q src/ait
```

For Phase 6 review orchestration specifically, these tests must be green:

```bash
PYTHONPATH=src uv run pytest \
  tests/test_review_freshness.py \
  tests/test_review_queue_worker.py \
  tests/test_review_adapter_config.py \
  tests/test_review_gate_hardening.py \
  tests/test_review_query_dsl.py \
  tests/test_review_benchmark.py \
  -q
```

Benchmark smoke:

```bash
PYTHONPATH=src uv run python -m ait.cli review benchmark \
  tests/fixtures/review_benchmark/cases.json \
  --fake-reviewer fake:case \
  --format json
```

Do not tag or upload to PyPI if any of the following are true:

- review-disabled `ait run`, `ait apply`, or `ait recover` behavior changed
  without an explicit release note and migration plan
- a required review can be bypassed because of stale, malformed, or missing
  evidence
- review status is mixed into verifier semantics
- the DB migration is not backward compatible for existing `.ait` state
- packaging smoke cannot install and import `ait`
- test failures are explained only as local flakiness without a recorded
  reproduction or mitigation

## Attempt Provenance Hardening Gate

Any release that changes prompt capture, transcript capture, runner failure
evidence, adapter wrapper/hook behavior, memory import/backfill, global agent
memory discovery, `ait status`, `ait attempt show`, `ait query`, `ait graph`,
or future inspection commands must be reviewed against
[`docs/attempt-provenance-hardening-spec.md`](attempt-provenance-hardening-spec.md).

Do not broaden README, website, PyPI, or GitHub metadata claims around
auditability, governance, prompt history, failure explainability, or bypass
detection unless the acceptance criteria in that spec pass. Any backfill or
global agent memory discovery feature must satisfy the spec's zero-interference
rules: dry-run writes nothing, import writes only under `.ait/`, source files
and global agent stores are never modified, and inferred history is advisory by
default.

At minimum, run:

```bash
PYTHONPATH=src uv run pytest tests/test_cli_run.py tests/test_query.py -q
PYTHONPATH=src uv run pytest tests/test_*transcript*.py tests/test_*hook*.py -q
PYTHONPATH=src uv run pytest tests/test_cli_adapters.py tests/test_cli_attempt_list.py -q
PYTHONPATH=src uv run pytest tests/test_memory*.py -q
git diff --check
```

## Tagged Release

Before tagging:

1. Classify the release bump using
   [`docs/versioning-policy.md`](versioning-policy.md). Use the highest required
   level across all shipped changes: patch, minor, or major.
2. Confirm `pyproject.toml`, `npm/ait-vcs/package.json`, README install
   examples, and docs/site version references match the intended tag.
3. Confirm `CHANGELOG.md` has an entry for the intended tag.
4. Run `git status --short`.
5. Run `.venv/bin/pytest -q`.
6. Run `git diff --check`.
7. Run the Review Orchestration Release Gate if review-related files
   changed.
8. Confirm README install and quickstart are current.
9. Build with `.venv/bin/python -m build`.
10. Check artifacts with `.venv/bin/python -m twine check dist/*`.
11. Run `npm --prefix npm/ait-vcs test`.
12. Run `(cd npm/ait-vcs && npm pack --dry-run)`.
13. Run a fresh venv smoke test from `dist/*.whl`, including the
   plain-directory init smoke and PATH-based agent wrapper smoke below.
14. Tag with the intended `vX.Y.Z`.
15. Push `main` and `vX.Y.Z` to GitHub.
16. Create a GitHub release with the built wheel and sdist.
17. Confirm GitHub Actions CI and Publish pass.
18. Confirm PyPI lists the new version.
19. Run a fresh venv smoke test from PyPI, including the plain-directory
    init smoke and PATH-based agent wrapper smoke below.
20. Publish the npm package from `npm/ait-vcs` after PyPI lists the same
    version.
21. Run a fresh global npm smoke test with `npm install -g ait-vcs`.

## Plain Directory Init Smoke

Run this once against the local wheel and once against the just-published
PyPI version:

```bash
set -e
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/pip" install -q dist/ait_vcs-X.Y.Z-py3-none-any.whl
repo="$tmpdir/repo" && mkdir "$repo" && cd "$repo"
bin="$tmpdir/bin" && mkdir "$bin"
cat > "$bin/claude" <<'SH'
#!/bin/sh
printf 'real claude reached\n'
SH
chmod +x "$bin/claude"
PATH="$bin:$PATH" "$tmpdir/venv/bin/ait" init --adapter claude-code --format json > init.json
"$tmpdir/venv/bin/python" - <<'PY'
import json
from pathlib import Path
init = json.loads(Path('init.json').read_text())
config = json.loads(Path('.ait/config.json').read_text())
assert Path('.git').exists()
assert init['git_initialized'] is True, init
assert init['baseline_commit_created'] is True, init
assert init['installed_adapters'] == ['claude-code'], init
assert not config['repo_identity'].startswith('unborn:'), config
print('plain-directory init smoke ok')
PY
```

## PATH Agent Wrapper Smoke

Run this once against the local wheel and once against the just-published
PyPI version. The important detail is that the smoke invokes the agent
command through `PATH`; it should not call `.ait/bin/<command>` directly.
Use `claude` for the default release smoke, and use the automated test
suite for adapter parity across `codex`, `aider`, `gemini`, and
`cursor`.

For a local wheel:

```bash
set -e
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/pip" install -q dist/ait_vcs-X.Y.Z-py3-none-any.whl
repo="$tmpdir/repo" && mkdir "$repo" && cd "$repo"
git init -q
git config user.email test@example.com
git config user.name 'Test User'
printf 'hello\n' > README.md
git add README.md
git commit -qm init
bin="$tmpdir/bin" && mkdir "$bin"
cat > "$bin/claude" <<'SH'
#!/bin/sh
printf 'real claude reached\n'
printf 'agent wrote through PATH claude\n' > path-claude-output.txt
SH
chmod +x "$bin/claude"
PATH="$bin:$PATH" "$tmpdir/venv/bin/ait" init --adapter claude-code --format json > init.json
rm .ait/memory-policy.json
printf 'Prefer direct PATH claude use.\n' > CLAUDE.md
PATH="$repo/.ait/bin:$bin:$PATH" claude --fake-prompt > wrapper.json
"$tmpdir/venv/bin/ait" memory --format json > memory.json
"$tmpdir/venv/bin/python" - <<'PY'
import json
from pathlib import Path
init = json.loads(Path('init.json').read_text())
wrapper = json.loads(Path('wrapper.json').read_text())
memory = json.loads(Path('memory.json').read_text())
assert init['installed_adapters'] == ['claude-code'], init
assert wrapper['exit_code'] == 0, wrapper
assert wrapper['attempt']['commits'], wrapper
assert Path('.ait/memory-policy.json').exists()
assert Path(wrapper['workspace_ref'], 'path-claude-output.txt').exists(), wrapper
sources = {item['source'] for item in memory['notes']}
assert 'agent-memory:claude:CLAUDE.md' in sources, sources
assert any(source.startswith('attempt-memory:') for source in sources), sources
print('PATH claude smoke ok')
PY
```

For PyPI, replace the install line with:

```bash
"$tmpdir/venv/bin/pip" install -q --no-cache-dir ait-vcs==X.Y.Z
```

## PyPI Release

The PyPI distribution is `ait-vcs`; the `ait` name is already owned by
another project on PyPI. The CLI entry point remains `ait`.

Before uploading:

1. Confirm `pyproject.toml` version matches the PyPI release version.
2. Run `.venv/bin/pytest -q`.
3. Run the Review Orchestration Release Gate if review-related files
   changed.
4. Build with `.venv/bin/python -m build`.
5. Check artifacts with `.venv/bin/python -m twine check dist/*`.
6. Upload with `.venv/bin/python -m twine upload dist/*`, or publish
   through GitHub trusted publishing.
7. Smoke test with `pip install ait-vcs`.

GitHub trusted publishing is also configured through
`.github/workflows/publish.yml`. On PyPI, create a pending trusted
publisher for:

```text
PyPI project: ait-vcs
Owner: m24927605
Repository: ait
Workflow: publish.yml
Environment: pypi
```

Then publish a GitHub release or run the workflow manually.

## npm Release

The npm distribution is `ait-vcs`; the `ait` name is already owned by
another project on npm. The npm package exports the `ait` command and
installs the matching PyPI release into a package-private virtual
environment during postinstall.

Before publishing npm:

1. Confirm `npm/ait-vcs/package.json` version matches `pyproject.toml`.
2. Confirm the matching PyPI version is already available.
3. Run `npm --prefix npm/ait-vcs test`.
4. Run `(cd npm/ait-vcs && npm pack --dry-run)`.
5. From `npm/ait-vcs`, run `npm publish --access public`.
6. Smoke test with `npm install -g ait-vcs`.
