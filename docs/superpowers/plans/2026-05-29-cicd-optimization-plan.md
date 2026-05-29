# CI/CD Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut GitHub Actions wall-clock time and runner-minute cost per the spec at `docs/superpowers/specs/2026-05-29-cicd-optimization-design.md`. Seven small, independently revertable changes across the four workflow files plus one Python test fix.

**Architecture:** Mostly `.github/workflows/*.yml` edits (drop macos-13, add concurrency, add pip cache, switch trigger model, add marker filter), plus one small `tests/conftest.py` refactor so the bug-report tests stop failing on CI.

**Tech Stack:** GitHub Actions YAML, `actions/setup-python@v6` cache feature, pytest markers, no new dependencies.

---

## Conventions (read before any task)

- Repo: `/Users/michael.chen/products/ait`
- Branch: create `fix/cicd-optimization` from current `main` before starting (`main` already has 1.6.1 + the spec doc committed at `b6d9edb`).
- **Hard rule from `memory/feedback_no_github_cicd_runs.md`**: do NOT `git push origin main`, do NOT `gh release create`, do NOT `gh workflow run`. All verification must be local — actionlint if installed, grep, local pytest, visual inspection.
- Test invocation (local only):
  ```
  PYTHONPATH=src:tests .venv/bin/python -m pytest tests/<module>.py -v
  ```
- Commit message footer (CLAUDE.md mandate):
  ```
  docs:<paths>
  keyword:<keys>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- HEREDOC for `git commit -m`.

---

## File inventory

| File | Touched by task |
|---|---|
| `tests/conftest.py` | T1 |
| `tests/bug_report/test_api.py` | T1 |
| `tests/bug_report/test_end_to_end_flow.py` | T1 |
| `tests/bug_report/test_excepthook.py` | T1 |
| `tests/bug_report/test_layer2_instrumentation.py` | T1 |
| `.github/workflows/ci.yml` | T2, T3, T4, T6 |
| `.github/workflows/docs.yml` | T3, T4 |
| `.github/workflows/publish.yml` | T3 |
| `.github/workflows/release-binary.yml` | T3, T5, T7 |
| `scripts/release-smoke/render_brew_formula.py` | T7 |
| `scripts/release-smoke/binary_smoke.py` | (none — no change) |
| `install.sh` | T7 |
| `scripts/homebrew-tap-template/Formula/ait.rb` | T7 |
| `docs/install.md` | T7 |
| `docs/release-checklist.md` | T5 |

---

## Task 1 — Fix CI-breaking bug-report tests (Item 7 in spec)

The autouse fixture in `tests/conftest.py:6-9` sets `AIT_BUG_REPORT=never` for every test. That env var disables the very pipeline the four bug-report tests need to assert on. They pass locally only because of subtle local state; CI's clean env exposes the bug.

**Files:**
- Modify: `tests/bug_report/test_api.py`
- Modify: `tests/bug_report/test_end_to_end_flow.py`
- Modify: `tests/bug_report/test_excepthook.py`
- Modify: `tests/bug_report/test_layer2_instrumentation.py`
- (No change to `tests/conftest.py` — the global setting stays correct for everything else.)

- [ ] **Step 1: Reproduce the failure locally**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest \
  tests/bug_report/test_api.py::ApiTests::test_report_internal_error_appends_to_collector \
  tests/bug_report/test_end_to_end_flow.py::EndToEndTests::test_non_tty_flush_writes_pending \
  tests/bug_report/test_excepthook.py::ExcepthookTests::test_install_records_ait_exception \
  tests/bug_report/test_layer2_instrumentation.py::Layer2Tests::test_each_layer2_category_records \
  -v
```

Expected: 4 failures with `AssertionError: 0 != 1` or similar — the bug-report pipeline never records anything because `AIT_BUG_REPORT=never` is set by `tests/conftest.py:9`.

If the tests pass locally, STOP and report: the bug only manifests on CI. The remaining steps still apply but should be applied "blind" since you can't reproduce.

- [ ] **Step 2: Add an `_enable_bug_report` fixture to each affected test class**

For each of the four test classes, add at the top of the class (after the `class` declaration, before any test methods):

`tests/bug_report/test_api.py`:

```python
class ApiTests(unittest.TestCase):
    def setUp(self):
        # tests/conftest.py disables AIT_BUG_REPORT for the rest of the
        # suite to prevent state pollution. These tests are the ones that
        # need the pipeline alive — opt back in.
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("AIT_BUG_REPORT", None)
        # ... existing setUp body, if any
```

You'll also need `def tearDown(self): self._env_patch.stop()` if `setUp` already exists.

If the existing tests already have setUp / tearDown, integrate the env handling there. Check each file for the existing class structure first.

Concretely, for `tests/bug_report/test_api.py` (which currently does NOT have setUp / tearDown), add at the very top of the class:

```python
    def setUp(self):
        self._addCleanup_env()

    def _addCleanup_env(self):
        import os as _os
        original = _os.environ.get("AIT_BUG_REPORT")
        _os.environ.pop("AIT_BUG_REPORT", None)
        def _restore():
            if original is None:
                _os.environ.pop("AIT_BUG_REPORT", None)
            else:
                _os.environ["AIT_BUG_REPORT"] = original
        self.addCleanup(_restore)
```

For files that already have setUp, prepend a single line:

```python
    def setUp(self):
        # Opt back into the bug-report pipeline for THIS test class only.
        # (tests/conftest.py disables it globally to stop state pollution.)
        import os as _os
        original = _os.environ.pop("AIT_BUG_REPORT", None)
        self.addCleanup(
            lambda: _os.environ.__setitem__("AIT_BUG_REPORT", original)
            if original is not None else _os.environ.pop("AIT_BUG_REPORT", None)
        )
        # ... existing setUp body ...
```

If the test file uses pytest-style (no `unittest.TestCase`), use a fixture instead:

```python
import pytest

@pytest.fixture(autouse=True)
def _opt_in_bug_report(monkeypatch):
    monkeypatch.delenv("AIT_BUG_REPORT", raising=False)
```

Inspect each file first to choose the right pattern. The four files use unittest.TestCase based on the test names (camelCase, `self.assertEqual`).

- [ ] **Step 3: Re-run the four targeted tests**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest \
  tests/bug_report/test_api.py::ApiTests::test_report_internal_error_appends_to_collector \
  tests/bug_report/test_end_to_end_flow.py::EndToEndTests::test_non_tty_flush_writes_pending \
  tests/bug_report/test_excepthook.py::ExcepthookTests::test_install_records_ait_exception \
  tests/bug_report/test_layer2_instrumentation.py::Layer2Tests::test_each_layer2_category_records \
  -v
```

Expected: 4 pass.

- [ ] **Step 4: Re-run the full bug_report suite to confirm no regression**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/bug_report/ -q
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/bug_report/
git commit -m "$(cat <<'EOF'
fix(test): bug_report tests opt back into AIT_BUG_REPORT pipeline

tests/conftest.py:9 sets AIT_BUG_REPORT=never globally to stop test
runs polluting ~/.local/state/ait/bug_reports/. That same env var
disables the pipeline the four bug-report tests need to assert on.
They passed locally because of subtle local state but were failing
on every CI run since 1.5.1.

Per-class opt-in: each affected test class deletes AIT_BUG_REPORT in
setUp and restores it via addCleanup. The global default stays
correct for the rest of the suite.

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md
keyword:cicd,test,bug-report,fix

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Stop the push+PR duplicate in `ci.yml` (Item 2 in spec)

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Inspect current trigger**

```bash
sed -n '1,8p' .github/workflows/ci.yml
```

Expected: `on:\n  push:\n  pull_request:` with no branch filter.

- [ ] **Step 2: Add branch filter**

Edit `.github/workflows/ci.yml`. Replace:

```yaml
on:
  push:
  pull_request:
```

with:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

- [ ] **Step 3: Visual verify**

```bash
sed -n '1,10p' .github/workflows/ci.yml
```

Both `push` and `pull_request` should now have `branches: [main]`.

- [ ] **Step 4: actionlint if available**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/ci.yml
    echo "actionlint OK"
else
    echo "actionlint not installed; skipped"
fi
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci: limit ci.yml triggers to main-branch push/PR

Was firing on every push to every branch AND on every PR open/sync,
causing 2x runs per PR (push to feature branch + PR event). Branch
filter pins both triggers to main, so feature-branch development
incurs zero CI cost until the PR is opened.

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md
keyword:cicd,cost,ci-trigger

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Add `concurrency` cancel-in-progress (Item 4 in spec)

Apply only to `ci.yml` and `docs.yml` (NOT to release-binary or publish — those are release events and must complete).

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/docs.yml`

- [ ] **Step 1: Add concurrency block to `ci.yml`**

After the `on:` block and before `jobs:` in `.github/workflows/ci.yml`, insert:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Final structure should look like:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    ...
```

- [ ] **Step 2: Add the same block to `docs.yml`**

Read `.github/workflows/docs.yml` first to find the right insertion point. Add the same `concurrency:` block after `on:` and before `jobs:`.

- [ ] **Step 3: Visual verify both files**

```bash
grep -A 2 "^concurrency:" .github/workflows/ci.yml .github/workflows/docs.yml
```

Expected: both files show the concurrency block.

- [ ] **Step 4: actionlint if available**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/ci.yml .github/workflows/docs.yml
fi
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/docs.yml
git commit -m "$(cat <<'EOF'
ci: cancel in-progress ci.yml and docs.yml on new push to same ref

When the maintainer pushes 3 quick commits, only the latest's CI run
matters. Adding concurrency.cancel-in-progress for ci.yml and
docs.yml cancels superseded runs immediately. NOT applied to
publish.yml or release-binary.yml — those are release events that
must complete.

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md
keyword:cicd,cost,concurrency

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Add `cache: pip` to all setup-python steps (Item 3 in spec)

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/docs.yml`
- Modify: `.github/workflows/publish.yml`
- Modify: `.github/workflows/release-binary.yml`

- [ ] **Step 1: Find all `setup-python` uses**

```bash
grep -n "setup-python" .github/workflows/*.yml
```

- [ ] **Step 2: For each `actions/setup-python@v6` block, add `cache: pip` and `cache-dependency-path`**

For every block of the shape:

```yaml
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
```

Replace with:

```yaml
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: pyproject.toml
```

Apply this to EVERY occurrence across the four workflow files. Use the Edit tool with enough surrounding context per occurrence to make `old_string` unique.

- [ ] **Step 3: Visual verify**

```bash
grep -B 1 -A 4 "setup-python" .github/workflows/*.yml | head -40
```

Every `setup-python` block should now include `cache: pip` and `cache-dependency-path: pyproject.toml`.

- [ ] **Step 4: actionlint if available**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/*.yml
fi
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/
git commit -m "$(cat <<'EOF'
ci: enable pip cache in setup-python across all workflows

actions/setup-python@v6 has built-in pip caching keyed on a
dependency manifest. Was unused — every job reinstalled pyinstaller,
build, twine, and editable -e . from scratch. Adding cache: pip with
cache-dependency-path: pyproject.toml saves 20-60s per job. Biggest
effect on release-binary.yml (3 matrix jobs).

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md
keyword:cicd,cost,pip-cache

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Switch ci.yml to fast PR path via pytest markers (Item 6 in spec)

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/release-checklist.md`

- [ ] **Step 1: Confirm pytest marker auto-assignment is active**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest --collect-only -q \
  -m "not (slow or daemon or subprocess or release)" 2>&1 | tail -3
```

Expected output should show a meaningful subset (e.g. "920 tests collected, 101 deselected") — confirming `tests/conftest.py:pytest_collection_modifyitems` is auto-marking by filename.

If the deselect count is 0, the auto-marking is broken; STOP and report.

- [ ] **Step 2: Update ci.yml's "Run tests" step**

Find the line in `.github/workflows/ci.yml`:

```yaml
      - name: Run tests
        run: pytest -q
```

Replace with:

```yaml
      - name: Run fast PR tests
        # The full suite runs in publish.yml on release. Auto-markers
        # are assigned by tests/conftest.py.
        run: pytest -q -m "not (slow or daemon or subprocess or release)"
```

- [ ] **Step 3: Confirm publish.yml is still full-suite**

```bash
grep -n "pytest\|release-smoke" .github/workflows/publish.yml | head -5
```

publish.yml uses `python scripts/release-smoke/wheel_smoke.py` rather than `pytest -q` directly, so the release gate is already covered by a different code path. No change needed there.

But there's a release gate test in CI's `release-smoke` job too:

```yaml
- name: Run release smoke tests
  run: python -m pytest tests/test_release_smoke.py -q
```

That stays as-is — it's already targeting a single file, not the whole suite.

- [ ] **Step 4: Update `docs/release-checklist.md`**

Add a note in the "Test Runtime Tiers" section noting that CI's PR-fast path uses the marker filter and that releases must hit `python -m pytest -q` (no filter) locally before tagging.

```bash
grep -n "fast local loop\|Fast local loop" docs/release-checklist.md | head -3
```

If found, add immediately after that section:

```markdown

CI's `ci.yml` test job mirrors the fast local loop — it filters out
`slow / daemon / subprocess / release` markers. The full suite is a
manual pre-tag gate the maintainer runs locally before pushing a
release tag.
```

- [ ] **Step 5: Run the fast path locally and confirm it's quicker**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest -q \
  -m "not (slow or daemon or subprocess or release)" 2>&1 | tail -3
```

Expected: faster than the full suite (saves 30-60s typically).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml docs/release-checklist.md
git commit -m "$(cat <<'EOF'
ci: PR fast-path runs only fast markers; full suite stays a local gate

tests/conftest.py auto-assigns slow / daemon / subprocess / release
markers by filename. ci.yml now filters those out so PR/push runs
exercise only the fast subset. The full suite remains a pre-tag
manual local step (documented in docs/release-checklist.md).

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md,docs/release-checklist.md
keyword:cicd,cost,pytest-markers

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Drop `macos-13` (Intel Mac) from release-binary.yml (Item 1 in spec)

The single largest cost item: macOS Intel runners have a 10× minute multiplier and frequently queue 15-30 minutes.

**Files:**
- Modify: `.github/workflows/release-binary.yml`
- Modify: `scripts/release-smoke/render_brew_formula.py`
- Modify: `install.sh`
- Modify: `scripts/homebrew-tap-template/Formula/ait.rb`
- Modify: `docs/install.md`

- [ ] **Step 1: Drop macos-13 from the matrix**

In `.github/workflows/release-binary.yml`, find:

```yaml
        include:
          - os: macos-latest
            target: macos-arm64
          - os: macos-13
            target: macos-x86_64
          - os: ubuntu-latest
            target: linux-x86_64
          - os: ubuntu-24.04-arm
            target: linux-arm64
```

Replace with:

```yaml
        include:
          - os: macos-latest
            target: macos-arm64
          # macos-x86_64 dropped 2026-05-29: 10x runner cost + 15-30min
          # queue. Intel Mac users install via pip; see docs/install.md.
          - os: ubuntu-latest
            target: linux-x86_64
          - os: ubuntu-24.04-arm
            target: linux-arm64
```

- [ ] **Step 2: Update `scripts/release-smoke/render_brew_formula.py`**

Find the `TARGETS = (...)` tuple. Drop `"macos-x86_64"`:

```python
TARGETS = ("macos-arm64", "linux-x86_64", "linux-arm64")
```

Also update `_TEMPLATE` to drop the `on_intel do ... end` block under `on_macos`:

```python
_TEMPLATE = """\
class Ait < Formula
  desc "AI-agent-native VCS layer that turns AI coding into reviewable attempts"
  homepage "https://github.com/m24927605/ait"
  version "{version_no_v}"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-macos-arm64"
      sha256 "{macos_arm64}"
    end
    # macos-x86_64 not produced — Intel Mac users install via pip.
  end

  on_linux do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-linux-arm64"
      sha256 "{linux_arm64}"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-linux-x86_64"
      sha256 "{linux_x86_64}"
    end
  end

  def install
    bin.install Dir["ait-*"][0] => "ait"
  end

  test do
    assert_match version.to_s, shell_output("#{{bin}}/ait --version")
  end
end
"""
```

Also update `render_formula` to no longer require `macos_x86_64`:

```python
def render_formula(*, version: str, checksums: dict[str, str]) -> str:
    version_no_v = version.lstrip("v")
    return _TEMPLATE.format(
        version_tag=version,
        version_no_v=version_no_v,
        macos_arm64=checksums["macos-arm64"],
        linux_x86_64=checksums["linux-x86_64"],
        linux_arm64=checksums["linux-arm64"],
    )
```

- [ ] **Step 3: Update `scripts/homebrew-tap-template/Formula/ait.rb` to match**

Read the file first, then drop the `on_intel do ... end` block under `on_macos do`. Keep the structure consistent with the renderer's output.

- [ ] **Step 4: Update `install.sh` so darwin/x86_64 prints a useful message**

In `install.sh`, find the platform detection block:

```sh
case "$os/$arch" in
    darwin/arm64)               target="macos-arm64" ;;
    darwin/x86_64)              target="macos-x86_64" ;;
    ...
```

Replace the `darwin/x86_64` branch:

```sh
    darwin/x86_64)
        cat >&2 <<'MSG'
Intel Mac is not supported by the standalone binary.
Install via pip instead:
  pip install ait-vcs       # or: pipx install ait-vcs
See https://github.com/m24927605/ait/blob/main/docs/install.md
MSG
        exit 1
        ;;
```

- [ ] **Step 5: Update `docs/install.md` platforms table**

Find the platforms table (the markdown table listing target / binary name / built on). Replace the `macos-x86_64` row with a note. The end result should look like:

```markdown
| Target | Binary name | Built on |
|---|---|---|
| macOS arm64 (Apple Silicon) | `ait-<tag>-macos-arm64` | macos-latest |
| macOS Intel (x86_64) | — (use pip) | n/a |
| Linux x86_64 | `ait-<tag>-linux-x86_64` | ubuntu-latest |
| Linux arm64 | `ait-<tag>-linux-arm64` | ubuntu-24.04-arm |
```

If the doc has prose explaining Intel Mac installation, ensure it points to pip:

```markdown
**Intel Mac users**: the standalone binary is not produced for Intel
Mac (the GitHub-hosted Intel Mac runner has both a 10× cost multiplier
and a 15-30 minute queue). Use the pip path:

```bash
pip install ait-vcs       # or: pipx install ait-vcs
```
```

- [ ] **Step 6: Update render_brew_formula tests if any reference macos-x86_64**

```bash
grep -n "macos-x86_64\|macos_x86_64" tests/release_smoke/test_render_brew_formula.py
```

If found, update the fixtures in `tests/release_smoke/test_render_brew_formula.py` to drop the `macos-x86_64` checksum entry and adjust assertions.

The sample `SAMPLE_CHECKSUMS` in that file currently has 4 entries — drop the macos-x86_64 line so the test exercises the new 3-target shape.

- [ ] **Step 7: Run the renderer tests locally**

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest tests/release_smoke/test_render_brew_formula.py -v
```

Expected: all green.

- [ ] **Step 8: Smoke render**

```bash
cat > /tmp/sums.txt <<'EOF'
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-v1.6.2-macos-arm64
cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc  ait-v1.6.2-linux-x86_64
dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd  ait-v1.6.2-linux-arm64
EOF
.venv/bin/python scripts/release-smoke/render_brew_formula.py \
    --version v1.6.2 --checksums /tmp/sums.txt --output /tmp/x.rb
head -20 /tmp/x.rb
```

Expected: renders a valid formula with three platforms, no `macos-x86_64` URL or sha line.

- [ ] **Step 9: Smoke install.sh's new Intel Mac branch**

Construct a hermetic test with fake `uname` returning `Darwin / x86_64`:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/bin"
cat > "$tmp/bin/uname" <<'EOF'
#!/bin/sh
case "$1" in
    -s) echo "Darwin" ;;
    -m) echo "x86_64" ;;
esac
EOF
chmod +x "$tmp/bin/uname"
PATH="$tmp/bin:$PATH" sh install.sh 2>&1 | head -5
```

Expected: prints the "Intel Mac is not supported" message and exits non-zero.

- [ ] **Step 10: Commit**

```bash
git add .github/workflows/release-binary.yml \
        scripts/release-smoke/render_brew_formula.py \
        scripts/homebrew-tap-template/Formula/ait.rb \
        install.sh \
        docs/install.md \
        tests/release_smoke/test_render_brew_formula.py
git commit -m "$(cat <<'EOF'
ci: drop macos-x86_64 from the binary release matrix

GitHub-hosted Intel Mac runners cost 10x Linux minutes AND queue
15-30 minutes before they start. v1.6.0 cancelled after 41 min still
queued; v1.6.1 cancelled after 25 min. Apple Silicon now covers >90%
of new Macs; Intel Mac users install via pip.

Cascading changes:
- render_brew_formula.py and the Homebrew tap template drop the
  on_intel branch under on_macos.
- install.sh's darwin/x86_64 branch now prints a clear pointer to the
  pip install path instead of attempting an impossible binary download.
- docs/install.md platforms table and prose updated.
- test_render_brew_formula fixtures updated to the 3-target shape.

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md,docs/install.md
keyword:cicd,cost,macos-intel

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — Make release-binary.yml workflow_dispatch only (Item 5 in spec)

Right now the workflow fires on every `release: published` event. Per the maintainer's no-auto-CI rule, switch to dispatch-only.

**Files:**
- Modify: `.github/workflows/release-binary.yml`
- Modify: `docs/release-checklist.md`

- [ ] **Step 1: Read the current `on:` block**

```bash
sed -n '1,15p' .github/workflows/release-binary.yml
```

Expected: `on:` includes both `release: types: [published]` and `workflow_dispatch:`.

- [ ] **Step 2: Drop the `release:` trigger**

Edit `.github/workflows/release-binary.yml`. Replace:

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      tag:
        description: "Release tag to build for (e.g. v1.5.1). Required for workflow_dispatch."
        required: true
```

with:

```yaml
on:
  # release trigger intentionally removed 2026-05-29 — see
  # docs/superpowers/specs/2026-05-29-cicd-optimization-design.md and
  # memory/feedback_no_github_cicd_runs.md. Binary builds are now
  # opt-in via `gh workflow run`.
  workflow_dispatch:
    inputs:
      tag:
        description: "Release tag to build for (e.g. v1.6.2). Required."
        required: true
```

- [ ] **Step 3: Update all `if: github.event_name == 'release'` conditions**

The build job's Upload to release step, checksums job, and update-tap job all check `github.event_name == 'release'`. Since release events no longer trigger this workflow, those conditions need updating.

Find each occurrence:

```bash
grep -n "github.event_name == 'release'" .github/workflows/release-binary.yml
```

For the build job's "Upload to release" step (line ~84): change to always upload when running via workflow_dispatch:

```yaml
      - name: Upload to release
        if: github.event_name == 'workflow_dispatch'
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}
          tag_name: ${{ github.event.inputs.tag }}
```

Note: with workflow_dispatch we have to pass `tag_name` explicitly because there's no `github.event.release.tag_name`.

Delete the "Upload as workflow artifact" step entirely — we only need release-attachment now.

For the checksums job: change `if: github.event_name == 'release'` to `if: github.event_name == 'workflow_dispatch'`. Same pattern for resolving the tag — replace `github.event.release.tag_name` with `github.event.inputs.tag`.

For the update-tap job: same — replace the condition with `if: github.event_name == 'workflow_dispatch' && vars.AIT_TAP_UPDATE_ENABLED == 'true'`. Replace the tag resolution similarly.

- [ ] **Step 4: Verify the final shape**

```bash
grep -n "github.event_name\|github.event.release\|github.event.inputs" .github/workflows/release-binary.yml
```

Every reference should now be `workflow_dispatch` or `github.event.inputs.tag` — no `github.event.release.tag_name` anywhere.

- [ ] **Step 5: actionlint if available**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/release-binary.yml
fi
```

- [ ] **Step 6: Update `docs/release-checklist.md` to reflect the new flow**

Find the "Binary release pipeline" section in `docs/release-checklist.md`. Replace its content with:

```markdown

## Binary release pipeline

The binary pipeline at `.github/workflows/release-binary.yml` is
opt-in via `workflow_dispatch` (it no longer fires automatically on
release publish). This is per the no-auto-CI policy at
`memory/feedback_no_github_cicd_runs.md`.

Per release that ships binaries:

1. Tag and create the GitHub release as usual (`gh release create
   vX.Y.Z ...`). This runs PyPI publish + npm smoke but NOT
   release-binary.
2. After the release is published and you actually want binaries,
   manually trigger:
   ```bash
   gh workflow run release-binary.yml -f tag=vX.Y.Z
   ```
3. Watch the four-platform matrix complete. Binaries upload directly
   to the existing release via `tag_name: <tag>`.
4. Checksums + (when `vars.AIT_TAP_UPDATE_ENABLED == 'true'`) Brew
   tap update follow automatically.

If a release ships only pip (docs change, version bump, etc.), skip
step 2 entirely — no binary, no cost.

One-time setup for Brew tap auto-update remains as documented in
`scripts/homebrew-tap-template/SETUP.md`.
```

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release-binary.yml docs/release-checklist.md
git commit -m "$(cat <<'EOF'
ci: release-binary.yml is workflow_dispatch only

Per memory/feedback_no_github_cicd_runs.md (no auto-CI/CD spend), the
binary pipeline is now an explicit `gh workflow run` step. Docs-only
or pip-only releases incur zero CI cost. When binaries are wanted,
maintainer runs `gh workflow run release-binary.yml -f tag=vX.Y.Z`
after the release is published.

Build job uploads now pass tag_name explicitly since we no longer
have github.event.release.tag_name. Checksums and update-tap jobs
gated on workflow_dispatch.

docs:docs/superpowers/specs/2026-05-29-cicd-optimization-design.md,docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md,docs/release-checklist.md
keyword:cicd,cost,opt-in,workflow_dispatch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (no commit)

After all seven tasks, verify the suite still works on the same Python the maintainer uses:

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest -q \
  -m "not (slow or daemon or subprocess or release)" 2>&1 | tail -5
```

Expected: green, fast (under a minute).

Then a full local sanity:

```bash
PYTHONPATH=src:tests .venv/bin/python -m pytest -q 2>&1 | tail -5
```

Expected: green. This is the local release-gate run that, per the spec, replaces the auto-CI full-suite that's no longer enforced on every push.

DO NOT push to origin. DO NOT trigger any workflow. The branch ends in a local-ready state; the maintainer decides when to merge.

---

# Self-review

**Spec coverage:**

| Spec item | Plan task |
|---|---|
| Item 1 — drop macos-13 | Task 6 |
| Item 2 — ci.yml push+PR de-dup | Task 2 |
| Item 3 — pip cache | Task 4 |
| Item 4 — concurrency | Task 3 |
| Item 5 — release-binary opt-in | Task 7 |
| Item 6 — pytest marker filter | Task 5 |
| Item 7 — bug-report conftest fix | Task 1 |
| Spec roll-out order | Followed: T1 (reliability) → T2 → T3 → T4 → T5 → T6 → T7 |
| Spec verification (local-only) | Each task's verify step is local; no `git push`, no `gh workflow run`. |

**Placeholder scan:** No "TBD", "TODO", "implement later" in plan text. Task 1 Step 2 has an explicit "If existing tests already have setUp" branch — both branches show concrete code, no "do something" handwave.

**Type consistency:** No new types or functions introduced — purely YAML + small Python test fixture edits. Names match across tasks (e.g. `AIT_BUG_REPORT`, `cache: pip`, `concurrency.group`, `vars.AIT_TAP_UPDATE_ENABLED`).

**Scope check:** Single focused PR. Each task is one commit and independently revertable.

---

# Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-29-cicd-optimization-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Useful here because the tasks span multiple workflow files plus a Python test fix.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints. Each task is small (YAML edits + one local pytest), so inline is also reasonable.
