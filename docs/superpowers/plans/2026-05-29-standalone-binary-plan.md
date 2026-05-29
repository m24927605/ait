# Standalone Binary Release Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `ait` as a single-file native binary for macOS (arm64 + x86_64) and Linux (x86_64 + arm64), distributable via GitHub Releases, `curl|sh`, and a Homebrew tap, with built-in `ait self-update`. Coexists with the existing pip / npm channels.

**Architecture:** Build with PyInstaller `--onefile`, inject `__version__` at build time via a generated `_frozen_version.py`. Four-binary matrix in a new GitHub Actions workflow that also generates checksums and pushes a refreshed Formula to the separate `m24927605/homebrew-ait` tap repo. `install.sh` is POSIX sh that detects platform, verifies SHA256, and drops the binary into `/usr/local/bin` or `~/.local/bin`. `ait self-update` detects how the binary was installed (pip vs brew vs binary) and either refuses with the right guidance or runs an atomic-replace update flow.

**Tech Stack:** PyInstaller 6.x (build-time only, not a runtime dep), POSIX sh, Ruby (Homebrew Formula), GitHub Actions (release-binary.yml), stdlib `urllib.request` / `subprocess` / `hashlib` / `webbrowser` / `tempfile` / `os.replace` for self-update, stdlib `unittest` with `unittest.mock` for tests.

---

## Conventions (read before any task)

- Repo root: `/Users/michael.chen/products/ait`
- Branch: create `feature/standalone-binary` from `main` before starting
- Python: `.venv/bin/python` (3.14.4) for tests; `/tmp/ait_311_verify/bin/python` (3.11.15) for cross-version verification when needed
- Test invocation:
  ```
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
  PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_X -v
  ```
- Commit message footer (CLAUDE.md mandate):
  ```
  docs:<comma-separated-paths>
  keyword:<comma-separated-keywords>

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- HEREDOC for `git commit -m`.
- After every commit verify only the intended files changed: `git diff HEAD~1 HEAD --stat`.

### What is in scope vs. out of scope

In scope:
- All code, CI workflow files, install scripts, test files.
- Local invocation of PyInstaller to verify the build runs on at least one platform (whichever the implementer's machine is).
- Unit tests for every Python module under `src/ait/self_update*` and `src/ait/cli/self_update.py`.
- Stub Brew Formula template + Python renderer.
- Documentation deltas in the main repo.

Out of scope:
- Creating the actual `m24927605/homebrew-ait` GitHub repository (maintainer one-time action — documented in `docs/release-checklist.md` as a manual step).
- Cutting a real release tag to trigger the CI workflow end-to-end.
- Notarizing macOS binaries (spec § Non-goals).
- Windows binary.

### Cross-platform testing reality

PyInstaller produces binaries that are platform-locked. An implementer on macOS arm64 can:
- Fully build + smoke `ait-<version>-macos-arm64`.
- Verify the CI workflow YAML by `actionlint` and dry-run with `act` if installed.
- Not produce `linux-arm64` / `linux-x86_64` / `macos-x86_64` binaries locally.

The CI matrix is what proves the other three platforms. Each task that touches CI says exactly which platforms it can be locally tested on.

---

## File Structure

New files:

```
build/
  ait.spec                    # PyInstaller spec
  build_binary.sh             # local reproducible build entry
  README.md                   # build/ folder explainer
scripts/
  release-smoke/
    binary_smoke.py           # smoke a built binary in hermetic tmpdir
    render_brew_formula.py    # render Formula/ait.rb for the tap repo
  homebrew-tap-template/      # scaffolding the maintainer copies to the tap repo
    Formula/
      ait.rb                  # template with placeholder SHA256s
    README.md                 # tap repo README
src/ait/
  self_update.py              # main implementation
  cli/
    self_update.py            # `ait self-update` subcommand
install.sh                    # root-level — curl|sh entry
.github/workflows/
  release-binary.yml          # 4-platform build + checksums + tap update
docs/
  install.md                  # per-platform install detail
  self-update.md              # `ait self-update` usage and dispatch
tests/
  self_update/
    __init__.py
    test_install_method.py
    test_version_compare.py
    test_cache.py
    test_download_verify.py
    test_atomic_replace.py
    test_permission_check.py
    test_dispatch_refusals.py
    test_cli_self_update.py
  release_smoke/
    test_binary_smoke_helper.py
    test_render_brew_formula.py
```

Generated at build time (gitignored):

```
src/ait/_frozen_version.py
```

Modified files:

```
.gitignore                                          # add _frozen_version.py
src/ait/cli_installation.py                         # frozen-version aware
src/ait/cli_parser.py                               # register self-update subcommand
src/ait/cli/main.py                                 # dispatch self-update
src/ait/cli/__init__.py                             # exports
README.md                                           # 3-path install section
README.zh-TW.md                                     # same
docs/release-checklist.md                           # add binary + tap sections
docs/ait-rebrand-qa-reality.md                      # note install cliff fully resolved
```

---

# Phase 1 — Build foundation

Local-runnable build that produces a working `ait` binary for the implementer's own platform.

## Task 1: PyInstaller spec and build entry

**Files:**
- Create: `build/ait.spec`
- Create: `build/build_binary.sh`
- Create: `build/README.md`

- [ ] **Step 1: Create the `build/` directory and entry script**

```bash
mkdir -p build
```

- [ ] **Step 2: Write `build/ait.spec`**

File: `build/ait.spec`

```python
# build/ait.spec — PyInstaller spec for `ait` standalone binary.
# Run from repo root: pyinstaller --clean --noconfirm build/ait.spec
# Output: build/dist/ait

# The Analysis pathex must reference the source tree.
a = Analysis(
    ["../src/ait/__main__.py"],
    pathex=["../src"],
    binaries=[],
    datas=[("../src/ait/resources", "ait/resources")],
    hiddenimports=[
        # Filled empirically; see build/README.md for the discovery procedure.
        # Initial seed: the bug_report subpackage uses dynamic imports for
        # adapter modules and similar — list every submodule found via grep.
        "ait.bug_report",
        "ait.bug_report.api",
        "ait.bug_report.collector",
        "ait.bug_report.excepthook",
        "ait.bug_report.flush",
        "ait.bug_report.prompt",
        "ait.bug_report.builder",
        "ait.bug_report.submitter",
        "ait.bug_report.pending_queue",
        "ait.bug_report.seen_store",
        "ait.bug_report.config",
        "ait.bug_report.fingerprint",
        "ait.bug_report.redactor",
        "ait.bug_report.safety",
        "ait._frozen_version",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["test", "tests", "unittest", "doctest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="ait",
    onefile=True,
    console=True,
    strip=True,
    upx=False,   # UPX often false-positives in antivirus; binary size hit is acceptable
    target_arch=None,   # let PyInstaller pick the runner's native arch
)
```

- [ ] **Step 3: Write `build/build_binary.sh`**

File: `build/build_binary.sh`

```bash
#!/bin/bash
# build/build_binary.sh — local reproducible build entry for ait standalone binary.
#
# Usage:
#   ./build/build_binary.sh
#
# Prereqs:
#   - python3.14 on PATH (or any Python >= 3.11)
#   - pip install pyinstaller==6.* (one-time per Python install)
#
# Output:
#   build/dist/ait

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# 1. Generate frozen version module from pyproject.toml.
python -c "
import tomllib, pathlib
data = tomllib.load(open('pyproject.toml','rb'))
v = data['project']['version']
out = pathlib.Path('src/ait/_frozen_version.py')
out.write_text(f\"__version__ = {v!r}\n\", encoding='utf-8')
print(f'wrote {out} with version {v}')
"

# 2. Ensure PyInstaller is available.
if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "ERROR: PyInstaller is not installed in this Python. Run:" >&2
    echo "  pip install 'pyinstaller==6.*'" >&2
    exit 1
fi

# 3. Build.
cd build
pyinstaller --clean --noconfirm ait.spec

# 4. Report.
binary="$REPO_ROOT/build/dist/ait"
if [[ -x "$binary" ]]; then
    echo "Built: $binary"
    "$binary" --version || true
else
    echo "ERROR: build did not produce $binary" >&2
    exit 1
fi
```

- [ ] **Step 4: Make the script executable and write README**

```bash
chmod +x build/build_binary.sh
```

File: `build/README.md`

```markdown
# `build/`

PyInstaller artifacts and local build entry for the `ait` standalone binary.

## Files

- `ait.spec` — PyInstaller spec. `--onefile`, no UPX, strip enabled.
- `build_binary.sh` — local reproducible build. Generates `src/ait/_frozen_version.py`, runs PyInstaller, outputs `build/dist/ait`.
- `dist/` (gitignored) — PyInstaller output.

## Hidden imports discovery

PyInstaller can't statically see imports loaded by `importlib.import_module(...)`.
The initial `hiddenimports` list in `ait.spec` enumerates `ait.bug_report.*`
submodules and `ait._frozen_version`.

To discover additional hidden imports after a build:

1. Build: `./build/build_binary.sh`
2. Smoke: `python scripts/release-smoke/binary_smoke.py build/dist/ait`
3. If smoke fails with `ModuleNotFoundError: No module named 'ait.X.Y'`,
   add `"ait.X.Y"` to `hiddenimports` in `ait.spec`.
4. Re-build and re-smoke until clean.

The CI workflow (`release-binary.yml`) does this loop automatically by
running `binary_smoke.py` as a post-build step.

## Why `_frozen_version.py`?

PyInstaller binaries can't `tomllib.load("pyproject.toml")` at runtime
because `pyproject.toml` isn't bundled. The `build_binary.sh` script reads
the version from `pyproject.toml` at build time and writes it to
`src/ait/_frozen_version.py`. At runtime, `cli_installation.package_version()`
reads from that module instead. The file is gitignored.
```

- [ ] **Step 5: Add `_frozen_version.py` to `.gitignore`**

Inspect:

```bash
grep -n "_frozen_version\|src/ait/_frozen_version" .gitignore
```

If no match, append to `.gitignore`:

```
# Generated at build time by build/build_binary.sh
src/ait/_frozen_version.py
```

- [ ] **Step 6: Install PyInstaller into the test venv (one-time)**

```bash
.venv/bin/pip install 'pyinstaller==6.*'
```

Expected: `Successfully installed pyinstaller-6.x`.

- [ ] **Step 7: Run the build script**

```bash
./build/build_binary.sh
```

Expected: `Built: <repo>/build/dist/ait` and `ait 1.5.0` on the next line.

If it fails with `ModuleNotFoundError`, add the missing module to
`hiddenimports` in `ait.spec` and re-run. Iterate until the smoke `--version`
prints.

- [ ] **Step 8: Commit**

```bash
git add build/ait.spec build/build_binary.sh build/README.md .gitignore
git commit -m "$(cat <<'EOF'
feat(build): PyInstaller spec and local build entry

build/ait.spec — onefile, strip enabled, no UPX. build/build_binary.sh
generates src/ait/_frozen_version.py from pyproject.toml, runs
PyInstaller, smoke-tests --version on the result.

The hiddenimports list starts with the bug_report subpackage's modules
(loaded via the singleton import dance) and the frozen-version module.
Discovery procedure documented in build/README.md.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md,build/README.md
keyword:standalone-binary,pyinstaller,build

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_frozen_version.py` runtime wiring

Make `cli_installation.package_version()` prefer the frozen-version module when running as a PyInstaller binary.

**Files:**
- Modify: `src/ait/cli_installation.py`
- Create: `tests/self_update/__init__.py`
- Create: `tests/self_update/test_frozen_version.py`

- [ ] **Step 1: Read the current package_version implementation**

```bash
grep -n "def package_version" src/ait/cli_installation.py
```

Identify the current function body and its dependencies (likely reads `pyproject.toml` via `tomllib`).

- [ ] **Step 2: Write the failing test**

```bash
mkdir -p tests/self_update
touch tests/self_update/__init__.py
```

File: `tests/self_update/test_frozen_version.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli_installation import package_version


class FrozenVersionTests(unittest.TestCase):
    def test_returns_pyproject_version_when_not_frozen(self):
        # Real path: tomllib reads pyproject.toml
        v = package_version()
        self.assertEqual(v, "1.5.0")

    def test_returns_frozen_version_when_sys_frozen(self):
        # Simulate PyInstaller: sys.frozen = True + ait._frozen_version present.
        fake_mod = type(sys)("ait._frozen_version")
        fake_mod.__version__ = "9.9.9"
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.dict(sys.modules, {"ait._frozen_version": fake_mod}):
            self.assertEqual(package_version(), "9.9.9")

    def test_returns_unknown_when_frozen_but_module_missing(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.dict(sys.modules, {}, clear=False):
            sys.modules.pop("ait._frozen_version", None)
            self.assertEqual(package_version(), "unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_frozen_version -v
```

Expected: 2 of 3 cases pass (the non-frozen one), 1 case fails because `package_version()` doesn't yet honor `sys.frozen`.

- [ ] **Step 4: Modify `package_version()`**

Open `src/ait/cli_installation.py`. Find `def package_version()`. Replace its body with:

```python
def package_version() -> str:
    if getattr(sys, "frozen", False):
        try:
            from ait._frozen_version import __version__  # type: ignore[import]
            return __version__
        except ImportError:
            return "unknown"
    # Existing pyproject.toml read path follows here unchanged.
    # ...rest of the function body, exactly as it was before...
```

Important: preserve the existing logic for the non-frozen branch. Don't refactor it.

Also ensure `import sys` is at the top of the file (it likely already is).

- [ ] **Step 5: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_frozen_version -v
```

Expected: 3 of 3 pass.

- [ ] **Step 6: Smoke the actual frozen binary**

```bash
./build/build_binary.sh
./build/dist/ait --version
```

Expected: `ait 1.5.0` (read from the generated `_frozen_version.py`).

- [ ] **Step 7: Commit**

```bash
git add src/ait/cli_installation.py tests/self_update/__init__.py tests/self_update/test_frozen_version.py
git commit -m "$(cat <<'EOF'
feat(cli_installation): frozen-version aware package_version()

When sys.frozen is True (PyInstaller bundle), import __version__ from
ait._frozen_version. Falls back to "unknown" on ImportError. The
existing pyproject.toml path runs only when not frozen.

The _frozen_version.py module is generated by build/build_binary.sh
from pyproject.toml at build time. It is gitignored.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,version,cli_installation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `binary_smoke.py` helper

Smoke a built binary in a hermetic tmpdir. Used by CI and locally.

**Files:**
- Create: `scripts/release-smoke/binary_smoke.py`
- Create: `tests/release_smoke/__init__.py`
- Create: `tests/release_smoke/test_binary_smoke_helper.py`

- [ ] **Step 1: Write the failing test**

```bash
mkdir -p tests/release_smoke
touch tests/release_smoke/__init__.py
```

File: `tests/release_smoke/test_binary_smoke_helper.py`

```python
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "release-smoke"))

from binary_smoke import smoke, SmokeFailure


class BinarySmokeTests(unittest.TestCase):
    def test_smoke_returns_zero_when_all_checks_pass(self):
        # Mock subprocess.run to return success for the three expected calls.
        def fake_run(cmd, **kwargs):
            r = mock.Mock()
            r.returncode = 0
            r.stdout = "ait 1.5.0\n"
            return r
        with mock.patch("binary_smoke.subprocess.run", side_effect=fake_run):
            rc = smoke(Path("/fake/ait"))
        self.assertEqual(rc, 0)

    def test_smoke_raises_when_version_check_fails(self):
        def fake_run(cmd, **kwargs):
            r = mock.Mock()
            r.returncode = 1
            r.stderr = "could not import ait.X.Y"
            r.stdout = ""
            return r
        with mock.patch("binary_smoke.subprocess.run", side_effect=fake_run):
            with self.assertRaises(SmokeFailure):
                smoke(Path("/fake/ait"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails (import error)**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_binary_smoke_helper -v
```

Expected: ImportError on `binary_smoke`.

- [ ] **Step 3: Write implementation**

File: `scripts/release-smoke/binary_smoke.py`

```python
"""Smoke a built `ait` binary in a hermetic tmpdir.

Usage:
    python scripts/release-smoke/binary_smoke.py path/to/ait
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class SmokeFailure(RuntimeError):
    pass


def smoke(binary_path: Path) -> int:
    """Return 0 on success; raise SmokeFailure on any check failure."""
    with tempfile.TemporaryDirectory() as td:
        env = {
            "HOME": td,
            "XDG_CONFIG_HOME": td,
            "XDG_STATE_HOME": td,
            "AIT_BUG_REPORT": "never",
            "PATH": os.environ.get("PATH", ""),
        }

        # 1. --version returns success
        r = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"--version failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )
        if "ait" not in (r.stdout or ""):
            raise SmokeFailure(f"--version output missing 'ait': {r.stdout!r}")

        # 2. bug-report list works
        r = subprocess.run(
            [str(binary_path), "bug-report", "list"],
            capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"bug-report list failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )

        # 3. init in a fresh repo
        repo = Path(td) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True,
                       capture_output=True)
        r = subprocess.run(
            [str(binary_path), "init"],
            cwd=str(repo), capture_output=True, env=env, text=True, timeout=15,
        )
        if r.returncode != 0:
            raise SmokeFailure(
                f"init failed: rc={r.returncode}\nstderr:\n{r.stderr}"
            )
        if not (repo / ".ait").exists():
            raise SmokeFailure(".ait directory not created by init")

    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: binary_smoke.py <binary_path>", file=sys.stderr)
        return 2
    try:
        return smoke(Path(sys.argv[1]))
    except SmokeFailure as exc:
        print(f"binary smoke FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_binary_smoke_helper -v
```

Expected: 2 of 2 pass.

- [ ] **Step 5: Run smoke against the real built binary**

```bash
.venv/bin/python scripts/release-smoke/binary_smoke.py build/dist/ait
echo "exit=$?"
```

Expected: exit 0, no output (success is silent).

If it fails, fix `ait.spec` `hiddenimports`, rebuild, re-smoke.

- [ ] **Step 6: Commit**

```bash
git add scripts/release-smoke/binary_smoke.py tests/release_smoke/__init__.py tests/release_smoke/test_binary_smoke_helper.py
git commit -m "$(cat <<'EOF'
feat(release-smoke): binary_smoke.py for hermetic binary checks

Verifies that a built `ait` binary can execute --version, bug-report
list (exercises PyInstaller bundled resources), and init (exercises
.ait directory creation). Runs in a temp dir with XDG redirected so
no developer state is touched. Used by CI and locally.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,release-smoke

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `render_brew_formula.py` helper

Render a Homebrew Formula from a version + a checksums file.

**Files:**
- Create: `scripts/release-smoke/render_brew_formula.py`
- Create: `tests/release_smoke/test_render_brew_formula.py`

- [ ] **Step 1: Write the failing test**

File: `tests/release_smoke/test_render_brew_formula.py`

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "release-smoke"))

from render_brew_formula import parse_checksums, render_formula


SAMPLE_CHECKSUMS = """\
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-v1.5.1-macos-arm64
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  ait-v1.5.1-macos-x86_64
cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc  ait-v1.5.1-linux-x86_64
dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd  ait-v1.5.1-linux-arm64
"""


class RenderBrewFormulaTests(unittest.TestCase):
    def test_parse_checksums_returns_dict_keyed_by_target(self):
        out = parse_checksums(SAMPLE_CHECKSUMS, version="v1.5.1")
        self.assertEqual(out["macos-arm64"], "a" * 64)
        self.assertEqual(out["macos-x86_64"], "b" * 64)
        self.assertEqual(out["linux-x86_64"], "c" * 64)
        self.assertEqual(out["linux-arm64"], "d" * 64)

    def test_render_formula_includes_version_and_all_four_shas(self):
        sums = parse_checksums(SAMPLE_CHECKSUMS, version="v1.5.1")
        formula = render_formula(version="v1.5.1", checksums=sums)
        self.assertIn('version "1.5.1"', formula)
        self.assertIn("a" * 64, formula)
        self.assertIn("b" * 64, formula)
        self.assertIn("c" * 64, formula)
        self.assertIn("d" * 64, formula)
        # Structure sanity
        self.assertIn("class Ait < Formula", formula)
        self.assertIn("on_macos do", formula)
        self.assertIn("on_linux do", formula)

    def test_parse_checksums_raises_when_target_missing(self):
        bad = "aa  ait-v1.5.1-macos-arm64\n"  # only one entry
        with self.assertRaises(ValueError):
            parse_checksums(bad, version="v1.5.1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_render_brew_formula -v
```

Expected: ImportError on `render_brew_formula`.

- [ ] **Step 3: Write implementation**

File: `scripts/release-smoke/render_brew_formula.py`

```python
"""Render a Homebrew Formula from a version tag + a sha256 checksums file.

Usage:
    python scripts/release-smoke/render_brew_formula.py \
        --version v1.5.1 \
        --checksums checksums.txt \
        --output Formula/ait.rb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


TARGETS = ("macos-arm64", "macos-x86_64", "linux-x86_64", "linux-arm64")

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
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/{version_tag}/ait-{version_tag}-macos-x86_64"
      sha256 "{macos_x86_64}"
    end
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
    assert_match version.to_s, shell_output("#{bin}/ait --version")
  end
end
"""


def parse_checksums(content: str, *, version: str) -> dict[str, str]:
    """Parse `sha256  ait-<version>-<target>` lines into {target: sha}."""
    out: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        prefix = f"ait-{version}-"
        if not name.startswith(prefix):
            continue
        target = name[len(prefix):]
        out[target] = sha
    missing = [t for t in TARGETS if t not in out]
    if missing:
        raise ValueError(f"checksums missing entries for: {missing}")
    return out


def render_formula(*, version: str, checksums: dict[str, str]) -> str:
    version_no_v = version.lstrip("v")
    return _TEMPLATE.format(
        version_tag=version,
        version_no_v=version_no_v,
        macos_arm64=checksums["macos-arm64"],
        macos_x86_64=checksums["macos-x86_64"],
        linux_x86_64=checksums["linux-x86_64"],
        linux_arm64=checksums["linux-arm64"],
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True, help="version tag, e.g. v1.5.1")
    p.add_argument("--checksums", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    content = args.checksums.read_text(encoding="utf-8")
    sums = parse_checksums(content, version=args.version)
    formula = render_formula(version=args.version, checksums=sums)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_render_brew_formula -v
```

Expected: 3 of 3 pass.

- [ ] **Step 5: Local smoke**

```bash
cat > /tmp/sums.txt <<'EOF'
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-v1.5.1-macos-arm64
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  ait-v1.5.1-macos-x86_64
cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc  ait-v1.5.1-linux-x86_64
dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd  ait-v1.5.1-linux-arm64
EOF
.venv/bin/python scripts/release-smoke/render_brew_formula.py \
    --version v1.5.1 --checksums /tmp/sums.txt --output /tmp/ait.rb
head -10 /tmp/ait.rb
```

Expected: file starts with `class Ait < Formula` and contains `version "1.5.1"`.

- [ ] **Step 6: Commit**

```bash
git add scripts/release-smoke/render_brew_formula.py tests/release_smoke/test_render_brew_formula.py
git commit -m "$(cat <<'EOF'
feat(release-smoke): render_brew_formula.py for tap auto-update

Parses an sha256 checksums file produced by sha256sum on the four
release binaries, validates all four targets are present, and renders
the Homebrew Formula with version + URLs + checksums filled in.

Used by the update-tap CI job to push a fresh Formula into the
m24927605/homebrew-ait repo on every release.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,homebrew,formula

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 2 — CI workflow

Single workflow file with three jobs: `build`, `checksums`, `update-tap`. Local verification is via `actionlint` if available; full end-to-end verification requires a real release tag, which is a maintainer step.

## Task 5: `release-binary.yml` build job

**Files:**
- Create: `.github/workflows/release-binary.yml`

- [ ] **Step 1: Write the workflow file**

File: `.github/workflows/release-binary.yml`

```yaml
name: Release Binary

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      tag:
        description: "Release tag to build for (e.g. v1.5.1). Required for workflow_dispatch."
        required: true

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: macos-latest
            target: macos-arm64
          - os: macos-13
            target: macos-x86_64
          - os: ubuntu-latest
            target: linux-x86_64
          - os: ubuntu-24.04-arm
            target: linux-arm64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Resolve tag
        id: tag
        run: |
          if [ -n "${{ github.event.release.tag_name }}" ]; then
            echo "tag=${{ github.event.release.tag_name }}" >> $GITHUB_OUTPUT
          else
            echo "tag=${{ github.event.inputs.tag }}" >> $GITHUB_OUTPUT
          fi

      - name: Install build deps
        run: |
          python -m pip install --upgrade pip
          python -m pip install "pyinstaller==6.*"
          python -m pip install -e .

      - name: Inject frozen version
        run: |
          python -c '
          import tomllib, pathlib
          data = tomllib.load(open("pyproject.toml","rb"))
          v = data["project"]["version"]
          pathlib.Path("src/ait/_frozen_version.py").write_text(
              f"__version__ = {v!r}\n", encoding="utf-8")
          '

      - name: Build binary
        run: |
          cd build
          pyinstaller --clean --noconfirm ait.spec

      - name: Rename binary
        run: |
          mkdir -p dist
          mv build/dist/ait dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}

      - name: macOS ad-hoc sign
        if: startsWith(matrix.target, 'macos')
        run: |
          codesign --sign - --force --options runtime \
            dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}

      - name: Smoke
        run: |
          python scripts/release-smoke/binary_smoke.py \
            dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}

      - name: Upload to release
        if: github.event_name == 'release'
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}

      - name: Upload as workflow artifact
        if: github.event_name == 'workflow_dispatch'
        uses: actions/upload-artifact@v4
        with:
          name: ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}
          path: dist/ait-${{ steps.tag.outputs.tag }}-${{ matrix.target }}
```

- [ ] **Step 2: Verify YAML with actionlint if available**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/release-binary.yml
    echo "actionlint OK"
else
    echo "actionlint not installed; skipping. Install with: brew install actionlint"
fi
```

If actionlint isn't installed and you're on macOS, install it: `brew install actionlint`. Otherwise inspect the file manually for obvious typos.

- [ ] **Step 3: Commit (build job only — checksums and update-tap follow in Tasks 6 and 7)**

```bash
git add .github/workflows/release-binary.yml
git commit -m "$(cat <<'EOF'
feat(ci): release-binary workflow build job (4-platform matrix)

PyInstaller build for macos-arm64 / macos-x86_64 / linux-x86_64 /
linux-arm64. macOS targets get an ad-hoc codesign. Each build runs
binary_smoke.py before uploading either to the release (release
trigger) or as a workflow artifact (manual dispatch). Supports
workflow_dispatch with --tag for pre-release validation.

Checksums and brew tap update jobs follow in subsequent commits.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md,.github/workflows/release-binary.yml
keyword:standalone-binary,ci,github-actions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `release-binary.yml` checksums job

Append the `checksums` job that downloads all four binaries from the release and produces a single `ait-<tag>-checksums.txt`.

**Files:**
- Modify: `.github/workflows/release-binary.yml`

- [ ] **Step 1: Append the checksums job**

After the `build` job in `.github/workflows/release-binary.yml`, add:

```yaml

  checksums:
    needs: build
    if: github.event_name == 'release'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Resolve tag
        id: tag
        run: echo "tag=${{ github.event.release.tag_name }}" >> $GITHUB_OUTPUT

      - name: Download release binaries
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          mkdir -p dist
          gh release download "${{ steps.tag.outputs.tag }}" \
            -R "${{ github.repository }}" \
            -p 'ait-*-macos-arm64' \
            -p 'ait-*-macos-x86_64' \
            -p 'ait-*-linux-x86_64' \
            -p 'ait-*-linux-arm64' \
            -D dist/

      - name: Generate SHA256
        run: |
          cd dist
          sha256sum ait-${{ steps.tag.outputs.tag }}-* \
            > ait-${{ steps.tag.outputs.tag }}-checksums.txt
          cat ait-${{ steps.tag.outputs.tag }}-checksums.txt

      - name: Upload checksums to release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ait-${{ steps.tag.outputs.tag }}-checksums.txt
```

- [ ] **Step 2: Verify YAML**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/release-binary.yml
fi
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-binary.yml
git commit -m "$(cat <<'EOF'
feat(ci): release-binary checksums job

After the 4-platform build job completes, download all four release
binaries, sha256sum them, upload ait-<tag>-checksums.txt to the same
release. Gated on github.event_name == 'release' so manual dispatch
(workflow_dispatch) doesn't try to fetch from a non-existent release.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md,.github/workflows/release-binary.yml
keyword:standalone-binary,ci,checksums

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `release-binary.yml` update-tap job

Append the `update-tap` job that pushes a refreshed Formula to the `m24927605/homebrew-ait` repo.

**Files:**
- Modify: `.github/workflows/release-binary.yml`

- [ ] **Step 1: Append the update-tap job**

After the `checksums` job, add:

```yaml

  update-tap:
    needs: checksums
    if: github.event_name == 'release'
    runs-on: ubuntu-latest
    steps:
      - name: Resolve tag
        id: tag
        run: echo "tag=${{ github.event.release.tag_name }}" >> $GITHUB_OUTPUT

      - uses: actions/checkout@v5
        with:
          path: ait

      - name: Checkout tap repo
        uses: actions/checkout@v5
        with:
          repository: m24927605/homebrew-ait
          token: ${{ secrets.TAP_PUSH_TOKEN }}
          path: tap

      - name: Download checksums
        run: |
          curl -fsSL \
            "https://github.com/m24927605/ait/releases/download/${{ steps.tag.outputs.tag }}/ait-${{ steps.tag.outputs.tag }}-checksums.txt" \
            -o checksums.txt

      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Render formula
        run: |
          python ait/scripts/release-smoke/render_brew_formula.py \
            --version "${{ steps.tag.outputs.tag }}" \
            --checksums checksums.txt \
            --output tap/Formula/ait.rb

      - name: Commit and push
        working-directory: tap
        run: |
          git config user.email "release-bot@users.noreply.github.com"
          git config user.name "release-bot"
          git add Formula/ait.rb
          if git diff --cached --quiet; then
            echo "No changes — formula already up to date."
            exit 0
          fi
          git commit -m "ait ${{ steps.tag.outputs.tag }}"
          git push
```

- [ ] **Step 2: Verify YAML**

```bash
if command -v actionlint >/dev/null 2>&1; then
    actionlint .github/workflows/release-binary.yml
fi
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-binary.yml
git commit -m "$(cat <<'EOF'
feat(ci): release-binary update-tap job

After checksums lands on the release, render Formula/ait.rb via
render_brew_formula.py and push it to m24927605/homebrew-ait. The
push uses TAP_PUSH_TOKEN (a fine-grained PAT scoped only to the tap
repo). The job no-ops if the formula already matches (e.g. on a
re-run).

The maintainer creates m24927605/homebrew-ait and the TAP_PUSH_TOKEN
secret as a one-time setup; see docs/release-checklist.md.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md,.github/workflows/release-binary.yml
keyword:standalone-binary,ci,homebrew-tap

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 3 — install.sh and Homebrew tap template

## Task 8: `install.sh`

POSIX sh installer for `curl|sh` usage.

**Files:**
- Create: `install.sh`
- Create: `tests/release_smoke/test_install_sh.py`

- [ ] **Step 1: Write a smoke test that runs install.sh with mocked curl**

File: `tests/release_smoke/test_install_sh.py`

```python
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"


class InstallSshellSmokeTests(unittest.TestCase):
    """Smoke install.sh end-to-end with curl/sha mocked out.

    Build a PATH-only directory of fake `curl`, `sha256sum`, `shasum`
    that emit deterministic content, then run install.sh with --prefix
    pointing into a tmpdir and assert the resulting `ait` file is
    present.
    """

    def test_install_sh_detects_platform_and_places_binary(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            fake_bin = td / "fake_bin"
            fake_bin.mkdir()
            prefix = td / "prefix"

            # Fake curl: writes deterministic content.
            (fake_bin / "curl").write_text(textwrap.dedent("""\
                #!/bin/sh
                # Capture last arg as output file; emit different things based on URL.
                out=""
                last=""
                while [ $# -gt 0 ]; do
                    case "$1" in
                        -o) out="$2"; shift 2 ;;
                        *) last="$1"; shift ;;
                    esac
                done
                case "$last" in
                    *checksums.txt)
                        # 64 'a's -> matches what we make sha256sum print
                        printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ait-vTEST-PLATFORM\\n' > "$out"
                        ;;
                    *latest)
                        printf '{"tag_name": "vTEST"}\\n' > "$out"
                        ;;
                    *ait-vTEST-*)
                        printf 'fakebinary' > "$out"
                        ;;
                    *)
                        echo "FAKE_CURL: unknown URL $last" >&2; exit 1 ;;
                esac
            """))
            (fake_bin / "curl").chmod(0o755)

            # Fake shasum -a 256: print 'a'*64 deterministically.
            (fake_bin / "shasum").write_text(textwrap.dedent("""\
                #!/bin/sh
                printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  -\\n'
            """))
            (fake_bin / "shasum").chmod(0o755)
            # And sha256sum as a fallback on Linux:
            (fake_bin / "sha256sum").write_text(textwrap.dedent("""\
                #!/bin/sh
                printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  -\\n'
            """))
            (fake_bin / "sha256sum").chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH','')}"

            # Patch the target tuple to match what fake checksums say.
            # install.sh derives target from uname, so we also patch uname.
            (fake_bin / "uname").write_text(textwrap.dedent("""\
                #!/bin/sh
                case "$1" in
                    -s) echo "Test" ;;
                    -m) echo "PLATFORM" ;;
                    *) echo "Test" ;;
                esac
            """))
            (fake_bin / "uname").chmod(0o755)

            r = subprocess.run(
                ["sh", str(INSTALL_SH), "--prefix", str(prefix),
                 "--no-checksum"],   # we don't need to chase the checksum logic in this test
                capture_output=True, env=env, text=True, timeout=15,
            )
            if r.returncode != 0:
                self.fail(
                    f"install.sh failed rc={r.returncode}\n"
                    f"stdout:\n{r.stdout}\n"
                    f"stderr:\n{r.stderr}"
                )
            self.assertTrue((prefix / "ait").exists(),
                            f"expected {prefix}/ait to exist after install")


if __name__ == "__main__":
    unittest.main()
```

Note: This test focuses on the platform-detection + URL composition + file placement path. It uses `--no-checksum` to avoid mocking the (more complex) checksum verification flow; a separate test could cover that, but `--no-checksum` is the documented user-facing escape hatch, so its happy path is what we test.

- [ ] **Step 2: Run, verify it fails (install.sh doesn't exist)**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_install_sh -v
```

Expected: failure because `install.sh` doesn't exist.

- [ ] **Step 3: Write `install.sh`**

File: `install.sh`

```sh
#!/bin/sh
# install.sh — Install ait from GitHub Releases.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh -s -- --version v1.5.1
#   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh -s -- --prefix ~/.local
#
# Options:
#   --version <tag>   Install a specific tag (default: latest from GitHub Releases)
#   --prefix <dir>    Install directory (default: /usr/local/bin if writable, else ~/.local/bin)
#   --no-checksum     Skip SHA256 verification (NOT recommended)

set -eu

REPO="m24927605/ait"
DEFAULT_PREFIX_SYS="/usr/local/bin"
DEFAULT_PREFIX_USER="$HOME/.local/bin"

VERSION="latest"
PREFIX=""
SKIP_CHECKSUM=0

# --- argparse ---
while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            [ $# -ge 2 ] || { echo "--version requires a value" >&2; exit 2; }
            VERSION="$2"; shift 2 ;;
        --prefix)
            [ $# -ge 2 ] || { echo "--prefix requires a value" >&2; exit 2; }
            PREFIX="$2"; shift 2 ;;
        --no-checksum)
            SKIP_CHECKSUM=1; shift ;;
        -h|--help)
            sed -n '2,17p' "$0"; exit 0 ;;
        *)
            printf 'unknown arg: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# --- platform detection ---
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$os/$arch" in
    darwin/arm64)               target="macos-arm64" ;;
    darwin/x86_64)              target="macos-x86_64" ;;
    linux/x86_64|linux/amd64)   target="linux-x86_64" ;;
    linux/aarch64|linux/arm64)  target="linux-arm64" ;;
    test/platform)              target="PLATFORM" ;;   # for tests
    *) printf 'unsupported platform: %s/%s\n' "$os" "$arch" >&2; exit 1 ;;
esac

# --- resolve version ---
if [ "$VERSION" = "latest" ]; then
    VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)"
    [ -n "$VERSION" ] || { echo "could not resolve latest version" >&2; exit 1; }
fi

# --- pick install dir ---
if [ -z "$PREFIX" ]; then
    if [ -w "$DEFAULT_PREFIX_SYS" ] 2>/dev/null; then
        PREFIX="$DEFAULT_PREFIX_SYS"
    else
        PREFIX="$DEFAULT_PREFIX_USER"
    fi
fi
mkdir -p "$PREFIX"

# --- download binary + checksums ---
binary_name="ait-${VERSION}-${target}"
binary_url="https://github.com/${REPO}/releases/download/${VERSION}/${binary_name}"
checksum_url="https://github.com/${REPO}/releases/download/${VERSION}/ait-${VERSION}-checksums.txt"

tmp="$(mktemp -d -t ait-install.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

printf 'Downloading %s ...\n' "$binary_name"
curl -fSL --progress-bar "$binary_url" -o "$tmp/ait"

if [ "$SKIP_CHECKSUM" -eq 0 ]; then
    printf 'Verifying checksum ...\n'
    curl -fsSL "$checksum_url" -o "$tmp/checksums.txt"
    expected="$(grep " ${binary_name}\$" "$tmp/checksums.txt" | awk '{print $1}')"
    [ -n "$expected" ] || { echo "no checksum entry for ${binary_name}" >&2; exit 1; }
    if command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$tmp/ait" | awk '{print $1}')"
    elif command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$tmp/ait" | awk '{print $1}')"
    else
        echo "neither shasum nor sha256sum is available; rerun with --no-checksum to bypass" >&2
        exit 1
    fi
    [ "$expected" = "$actual" ] || {
        printf 'checksum mismatch: expected %s, got %s\n' "$expected" "$actual" >&2
        exit 1
    }
fi

# --- macOS: drop quarantine attribute ---
if [ "$os" = "darwin" ]; then
    xattr -d com.apple.quarantine "$tmp/ait" 2>/dev/null || true
fi

# --- install ---
chmod +x "$tmp/ait"
install_path="$PREFIX/ait"
mv "$tmp/ait" "$install_path"

printf 'Installed: %s\n' "$install_path"

# --- PATH check ---
case ":$PATH:" in
    *":$PREFIX:"*) ;;
    *) printf '\nNOTE: %s is not in your PATH. Add this to your shell profile:\n  export PATH="%s:$PATH"\n' "$PREFIX" "$PREFIX" ;;
esac

# --- verify ---
if command -v ait >/dev/null 2>&1; then
    ait --version
fi
```

- [ ] **Step 4: Make executable**

```bash
chmod +x install.sh
```

- [ ] **Step 5: Run test**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.release_smoke.test_install_sh -v
```

Expected: pass.

- [ ] **Step 6: Manual smoke (optional, requires real network)**

```bash
# Test the script syntax and argparse:
sh install.sh --help
# Test platform detection with a fake URL (will fail at download but
# proves detection works):
sh install.sh --version nope --prefix /tmp/ait-test || true
```

- [ ] **Step 7: Commit**

```bash
git add install.sh tests/release_smoke/test_install_sh.py
git commit -m "$(cat <<'EOF'
feat(install): POSIX install.sh for curl|sh setup

Single-file installer. Detects darwin/linux on arm64/x86_64. Resolves
latest tag via GitHub API unless --version is passed. Picks
/usr/local/bin or ~/.local/bin based on writability. Downloads binary
+ checksums; verifies SHA256 unless --no-checksum. macOS: strips
com.apple.quarantine. Atomic mv into place, then `ait --version`
check.

Tested with a hermetic fake-curl/sha/uname environment.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,install-sh,curl-bash

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Homebrew tap template scaffolding

Provide the maintainer with a ready-to-copy initial repo structure.

**Files:**
- Create: `scripts/homebrew-tap-template/Formula/ait.rb`
- Create: `scripts/homebrew-tap-template/README.md`
- Create: `scripts/homebrew-tap-template/SETUP.md`

- [ ] **Step 1: Write the initial Formula template**

File: `scripts/homebrew-tap-template/Formula/ait.rb`

```ruby
# This is the initial formula seed for m24927605/homebrew-ait.
# Replaced on every release by render_brew_formula.py via CI.
class Ait < Formula
  desc "AI-agent-native VCS layer that turns AI coding into reviewable attempts"
  homepage "https://github.com/m24927605/ait"
  version "1.5.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-arm64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-x86_64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-arm64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-x86_64"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  def install
    bin.install Dir["ait-*"][0] => "ait"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/ait --version")
  end
end
```

- [ ] **Step 2: Write tap-repo README**

File: `scripts/homebrew-tap-template/README.md`

```markdown
# homebrew-ait

Homebrew tap for [`ait`](https://github.com/m24927605/ait).

## Install

```bash
brew tap m24927605/ait
brew install ait
```

## Update

```bash
brew upgrade ait
```

## Notes

This tap is auto-updated on every `ait` release by the
[release-binary.yml](https://github.com/m24927605/ait/blob/main/.github/workflows/release-binary.yml)
workflow in the main repo. Do not hand-edit `Formula/ait.rb`; it will
be overwritten on the next release.

The formula points at signed (ad-hoc) binaries hosted on the main
repo's GitHub Releases. Homebrew strips `com.apple.quarantine` on
install so Gatekeeper does not prompt.
```

- [ ] **Step 3: Write maintainer setup instructions**

File: `scripts/homebrew-tap-template/SETUP.md`

```markdown
# Maintainer Setup — homebrew-ait

One-time setup. Required before the first release that ships binaries.

## 1. Create the tap repo

```bash
gh repo create m24927605/homebrew-ait --public \
    --description "Homebrew tap for ait" \
    --license MIT
```

## 2. Seed the tap repo from this template

From inside the main `ait` repo:

```bash
tmp=$(mktemp -d)
gh repo clone m24927605/homebrew-ait "$tmp/homebrew-ait"
cp -R scripts/homebrew-tap-template/Formula "$tmp/homebrew-ait/"
cp scripts/homebrew-tap-template/README.md "$tmp/homebrew-ait/"
cd "$tmp/homebrew-ait"
git add Formula README.md
git commit -m "initial tap seed"
git push
```

The placeholder SHA256s (all zeros) will be overwritten by the first
release of the binary pipeline.

## 3. Create the TAP_PUSH_TOKEN secret

Generate a fine-grained PAT scoped to write to `m24927605/homebrew-ait`
only:

```bash
gh auth refresh --scopes repo
# or visit https://github.com/settings/tokens?type=beta
```

Add the token as a secret in the main `ait` repo:

```bash
gh secret set TAP_PUSH_TOKEN --body "<paste-pat>" \
    -R m24927605/ait
```

## 4. Verify

Trigger a `workflow_dispatch` release-binary build to confirm CI can
build the binaries. Once that's clean, cut a real release tag to
exercise the full pipeline end-to-end (build + checksums + update-tap).
```

- [ ] **Step 4: Smoke the formula renders to something Homebrew would parse**

Re-render via the helper from Task 4:

```bash
# Synthesise a checksums file matching the initial-seed version:
cat > /tmp/seed-sums.txt <<'EOF'
1111111111111111111111111111111111111111111111111111111111111111  ait-v1.5.0-macos-arm64
2222222222222222222222222222222222222222222222222222222222222222  ait-v1.5.0-macos-x86_64
3333333333333333333333333333333333333333333333333333333333333333  ait-v1.5.0-linux-x86_64
4444444444444444444444444444444444444444444444444444444444444444  ait-v1.5.0-linux-arm64
EOF
.venv/bin/python scripts/release-smoke/render_brew_formula.py \
    --version v1.5.0 --checksums /tmp/seed-sums.txt --output /tmp/rendered.rb
diff scripts/homebrew-tap-template/Formula/ait.rb /tmp/rendered.rb || true
```

Expected: the diff shows ONLY the four SHA256 lines (the template has all-zero placeholders; the renderer has the synthesised hashes). Structure should be identical.

If the structure differs, fix `_TEMPLATE` in `render_brew_formula.py` so it matches the template — this guarantees CI will produce a formula that parses cleanly.

- [ ] **Step 5: Commit**

```bash
git add scripts/homebrew-tap-template/
git commit -m "$(cat <<'EOF'
feat(homebrew): tap repo template with initial seed and setup guide

scripts/homebrew-tap-template/ is what the maintainer copies into the
m24927605/homebrew-ait repo once at setup time. Includes Formula/ait.rb
with all-zero placeholder SHA256s (CI overwrites on first release),
the tap-repo README, and SETUP.md walking through repo create + secret
provisioning.

The template structure is kept in lockstep with what render_brew_formula.py
produces so the first real release lands a parseable formula.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,homebrew,tap-setup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 4 — `ait self-update`

Python implementation. Tests use mocked subprocess / urllib / tempfile so no real network or real binary swap happens.

## Task 10: `install_method()` detection

**Files:**
- Create: `src/ait/self_update.py`
- Create: `tests/self_update/test_install_method.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_install_method.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import install_method


class InstallMethodTests(unittest.TestCase):
    def test_not_frozen_returns_pip(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(install_method(), "pip")

    def test_frozen_under_cellar_returns_brew(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable",
                               "/opt/homebrew/Cellar/ait/1.5.1/bin/ait"):
            self.assertEqual(install_method(), "brew")

    def test_frozen_elsewhere_returns_binary(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", "/usr/local/bin/ait"):
            self.assertEqual(install_method(), "binary")

    def test_frozen_in_home_local_bin_returns_binary(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable",
                               "/Users/me/.local/bin/ait"):
            self.assertEqual(install_method(), "binary")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails (ImportError on install_method)**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_install_method -v
```

Expected: `ImportError: cannot import name 'install_method' from 'ait.self_update'`.

- [ ] **Step 3: Write implementation seed**

File: `src/ait/self_update.py`

```python
"""Self-update implementation for the `ait` standalone binary.

Public entry point: run(args) called by cli/self_update.py.
"""
from __future__ import annotations

import sys
from pathlib import Path


def install_method() -> str:
    """Detect how this ait was installed.

    Returns 'pip' | 'brew' | 'binary' | 'unknown'.
    """
    if not getattr(sys, "frozen", False):
        return "pip"
    exe = str(Path(sys.executable).resolve()) if sys.executable else ""
    # Homebrew Cellar layout: .../Cellar/ait/<version>/bin/ait
    if "/Cellar/" in exe and "/ait/" in exe:
        return "brew"
    return "binary"
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_install_method -v
```

Expected: 4 of 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_install_method.py
git commit -m "$(cat <<'EOF'
feat(self-update): install_method() detection

Returns 'pip' when not sys.frozen, 'brew' when the executable lives
under a Cellar/ait/ path, else 'binary'. This drives ait self-update's
dispatch so the same command produces sensible refusal messages
depending on how the user installed ait.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,install-method

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Version compare helper

**Files:**
- Modify: `src/ait/self_update.py` (add `compare_versions`)
- Create: `tests/self_update/test_version_compare.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_version_compare.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import compare_versions


class CompareVersionsTests(unittest.TestCase):
    def test_equal(self):
        self.assertEqual(compare_versions("1.5.0", "1.5.0"), 0)
        self.assertEqual(compare_versions("v1.5.0", "1.5.0"), 0)
        self.assertEqual(compare_versions("1.5.0", "v1.5.0"), 0)

    def test_older(self):
        self.assertEqual(compare_versions("1.5.0", "1.5.1"), -1)
        self.assertEqual(compare_versions("1.4.3", "1.5.0"), -1)
        self.assertEqual(compare_versions("0.9.9", "1.0.0"), -1)

    def test_newer(self):
        self.assertEqual(compare_versions("1.5.1", "1.5.0"), 1)
        self.assertEqual(compare_versions("2.0.0", "1.9.9"), 1)

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            compare_versions("notaversion", "1.5.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_version_compare -v
```

- [ ] **Step 3: Append `compare_versions` to `src/ait/self_update.py`**

Add (at the end of the file):

```python
def compare_versions(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if equal, 1 if a > b.

    Accepts either `1.5.0` or `v1.5.0` forms. Raises ValueError on malformed
    input. AIT versions are always MAJOR.MINOR.PATCH.
    """
    def _parse(s: str) -> tuple[int, int, int]:
        s = s.lstrip("v")
        parts = s.split(".")
        if len(parts) != 3:
            raise ValueError(f"not a 3-part semver: {s!r}")
        try:
            return tuple(int(p) for p in parts)  # type: ignore[return-value]
        except ValueError:
            raise ValueError(f"non-integer component in {s!r}")

    pa = _parse(a)
    pb = _parse(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_version_compare -v
```

Expected: 4 of 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_version_compare.py
git commit -m "$(cat <<'EOF'
feat(self-update): compare_versions semver-3 helper

Tuple-compare integer-parsed MAJOR.MINOR.PATCH. Accepts v-prefixed
form. Raises ValueError on malformed input. Avoids pulling in the
third-party `packaging` library — AIT versions are always strict
3-part semver so a stdlib parse is enough.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,semver

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Latest-release cache

**Files:**
- Modify: `src/ait/self_update.py`
- Create: `tests/self_update/test_cache.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_cache.py`

```python
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import (
    cache_path,
    load_cache,
    save_cache,
    is_cache_fresh,
)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_cache_path_under_xdg_state(self):
        p = cache_path()
        self.assertEqual(
            p,
            Path(self._td.name) / "ait" / "self_update_cache.json",
        )

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_cache())

    def test_round_trip(self):
        save_cache({
            "tag_name": "v1.5.1",
            "asset_urls": {"macos-arm64": "https://x/y"},
            "checksums_url": "https://x/sums.txt",
        }, now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        cached = load_cache()
        self.assertIsNotNone(cached)
        self.assertEqual(cached["latest"]["tag_name"], "v1.5.1")
        self.assertEqual(cached["fetched_at"], "2026-05-29T12:00:00Z")

    def test_is_cache_fresh_within_ttl(self):
        save_cache({"tag_name": "v1.5.1"},
                   now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        # 30 min later (TTL is 1 hour)
        self.assertTrue(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 12, 30, tzinfo=dt.timezone.utc)))

    def test_is_cache_fresh_expired(self):
        save_cache({"tag_name": "v1.5.1"},
                   now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        # 90 min later
        self.assertFalse(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 13, 30, tzinfo=dt.timezone.utc)))

    def test_is_cache_fresh_no_cache(self):
        self.assertFalse(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_cache -v
```

- [ ] **Step 3: Append cache helpers to `src/ait/self_update.py`**

Add:

```python
import datetime as _dt
import json as _json
import os as _os


_CACHE_TTL_SECONDS = 3600


def _xdg_state_dir() -> Path:
    val = _os.environ.get("XDG_STATE_HOME")
    if val:
        return Path(val)
    return Path.home() / ".local" / "state"


def cache_path() -> Path:
    return _xdg_state_dir() / "ait" / "self_update_cache.json"


def save_cache(latest: dict, *, now: _dt.datetime) -> None:
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "fetched_at": now.isoformat().replace("+00:00", "Z"),
        "ttl_seconds": _CACHE_TTL_SECONDS,
        "latest": latest,
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(_json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def load_cache() -> dict | None:
    p = cache_path()
    if not p.exists():
        return None
    try:
        return _json.loads(p.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return None


def is_cache_fresh(*, now: _dt.datetime) -> bool:
    cached = load_cache()
    if cached is None:
        return False
    fetched_at_str = cached.get("fetched_at", "")
    try:
        fetched_at = _dt.datetime.fromisoformat(
            fetched_at_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    ttl = int(cached.get("ttl_seconds", _CACHE_TTL_SECONDS))
    return (now - fetched_at).total_seconds() < ttl
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_cache -v
```

Expected: 6 of 6 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_cache.py
git commit -m "$(cat <<'EOF'
feat(self-update): XDG-state release-info cache

cache_path() honors XDG_STATE_HOME. save_cache/load_cache do atomic
write through .tmp + replace. is_cache_fresh() compares against
ttl_seconds (1 hour default) so repeated `ait self-update` invocations
don't hammer GitHub Releases API.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,cache,xdg

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Download + SHA256 verify

**Files:**
- Modify: `src/ait/self_update.py`
- Create: `tests/self_update/test_download_verify.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_download_verify.py`

```python
from __future__ import annotations

import hashlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import (
    ChecksumMismatch,
    download_and_verify,
)


class DownloadVerifyTests(unittest.TestCase):
    def test_happy_path_returns_bytes(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        with mock.patch("ait.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(content)
            out = download_and_verify("https://x/y", expected_sha256=expected)
        self.assertEqual(out, content)

    def test_checksum_mismatch_raises(self):
        content = b"hello world"
        wrong = "0" * 64
        with mock.patch("ait.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(content)
            with self.assertRaises(ChecksumMismatch):
                download_and_verify("https://x/y", expected_sha256=wrong)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_download_verify -v
```

- [ ] **Step 3: Append to `src/ait/self_update.py`**

Add:

```python
import hashlib as _hashlib
import urllib.request


class ChecksumMismatch(RuntimeError):
    pass


def download_and_verify(url: str, *, expected_sha256: str,
                        timeout: int = 60) -> bytes:
    """Download `url` and verify its sha256. Returns the bytes on match,
    raises ChecksumMismatch otherwise."""
    with urllib.request.urlopen(url, timeout=timeout) as fh:
        content = fh.read()
    actual = _hashlib.sha256(content).hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise ChecksumMismatch(
            f"sha256 mismatch: expected {expected_sha256!r}, got {actual!r}"
        )
    return content
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_download_verify -v
```

Expected: 2 of 2 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_download_verify.py
git commit -m "$(cat <<'EOF'
feat(self-update): download_and_verify with sha256

Read the URL into memory, sha256, compare against the expected value.
Raises ChecksumMismatch on a hash that doesn't agree. Used by the
update flow to confirm a downloaded binary matches the release's
checksums.txt entry before atomic replace.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,checksum

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Atomic replace

**Files:**
- Modify: `src/ait/self_update.py`
- Create: `tests/self_update/test_atomic_replace.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_atomic_replace.py`

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import atomic_replace


class AtomicReplaceTests(unittest.TestCase):
    def test_replaces_existing_file_with_new_content(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            target.write_text("old binary", encoding="utf-8")
            atomic_replace(target, b"new binary")
            self.assertEqual(target.read_bytes(), b"new binary")

    def test_creates_file_when_missing(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            atomic_replace(target, b"new binary")
            self.assertEqual(target.read_bytes(), b"new binary")

    def test_failure_cleans_up_tmp_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as td_str:
            td = Path(td_str)
            target = td / "ait"
            target.write_text("old binary", encoding="utf-8")
            with mock.patch("os.replace", side_effect=PermissionError("no")):
                with self.assertRaises(PermissionError):
                    atomic_replace(target, b"new binary")
            # Target unchanged
            self.assertEqual(target.read_text(encoding="utf-8"), "old binary")
            # No leftover .ait.new.* in the directory
            leftovers = [p.name for p in td.iterdir() if p.name.startswith(".ait.new")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_atomic_replace -v
```

- [ ] **Step 3: Append to `src/ait/self_update.py`**

```python
import contextlib
import tempfile


def atomic_replace(target: Path, content: bytes) -> None:
    """Write `content` to a sibling of `target` then atomically rename.

    Atomic on POSIX same-filesystem (os.replace). Tmp is cleaned up
    on any failure.
    """
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(dir=str(target_dir), prefix=".ait.new.")
    tmp = Path(tmp_str)
    try:
        with _os.fdopen(fd, "wb") as fh:
            fh.write(content)
        _os.chmod(tmp_str, 0o755)
        _os.replace(tmp_str, str(target))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
```

- [ ] **Step 4: Run tests, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_atomic_replace -v
```

Expected: 3 of 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_atomic_replace.py
git commit -m "$(cat <<'EOF'
feat(self-update): atomic_replace via mkstemp + os.replace

Writes new bytes to a sibling .ait.new.* tempfile in the target's
parent dir (same filesystem so os.replace is atomic on POSIX), chmod
0o755, then atomically swaps it into place. On failure the tempfile
is unlinked and the original target is preserved.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,atomic-replace

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Permission check + dispatch refusals

**Files:**
- Modify: `src/ait/self_update.py`
- Create: `tests/self_update/test_permission_check.py`
- Create: `tests/self_update/test_dispatch_refusals.py`

- [ ] **Step 1: Write tests**

File: `tests/self_update/test_permission_check.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import check_install_path_writable, InstallPathNotWritable


class PermissionCheckTests(unittest.TestCase):
    def test_writable_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "ait"
            target.write_text("x")
            check_install_path_writable(target)  # no raise

    def test_non_writable_dir_raises(self):
        with mock.patch("os.access", return_value=False):
            with self.assertRaises(InstallPathNotWritable) as ctx:
                check_install_path_writable(Path("/usr/local/bin/ait"))
            self.assertIn("/usr/local/bin", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

File: `tests/self_update/test_dispatch_refusals.py`

```python
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import refuse_with_message


class RefuseTests(unittest.TestCase):
    def test_pip_refusal_mentions_pip_install_upgrade(self):
        buf = io.StringIO()
        rc = refuse_with_message("pip", stdout=buf)
        self.assertEqual(rc, 1)
        self.assertIn("pip install --upgrade ait-vcs", buf.getvalue())

    def test_brew_refusal_mentions_brew_upgrade(self):
        buf = io.StringIO()
        rc = refuse_with_message("brew", stdout=buf)
        self.assertEqual(rc, 1)
        self.assertIn("brew upgrade ait", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify they fail**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_permission_check tests.self_update.test_dispatch_refusals -v
```

- [ ] **Step 3: Append to `src/ait/self_update.py`**

```python
class InstallPathNotWritable(RuntimeError):
    pass


def check_install_path_writable(target: Path) -> None:
    """Raise InstallPathNotWritable if we can't write into target.parent."""
    if not _os.access(str(target.parent), _os.W_OK):
        raise InstallPathNotWritable(
            f"cannot write to {target.parent}\n"
            f"re-run with sudo, or move ait to a user-owned path."
        )


def refuse_with_message(method: str, *, stdout=None) -> int:
    """Print the right refusal message and return exit code 1."""
    out = stdout if stdout is not None else sys.stdout
    if method == "pip":
        print(
            "You installed ait via pip. Run `pip install --upgrade ait-vcs` instead.",
            file=out,
        )
    elif method == "brew":
        print(
            "You installed ait via Homebrew. Run `brew upgrade ait` instead.",
            file=out,
        )
    else:
        print(f"ait self-update is not supported for install method: {method}",
              file=out)
    return 1
```

- [ ] **Step 4: Run, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_permission_check tests.self_update.test_dispatch_refusals -v
```

Expected: 4 of 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/ait/self_update.py tests/self_update/test_permission_check.py tests/self_update/test_dispatch_refusals.py
git commit -m "$(cat <<'EOF'
feat(self-update): permission check + pip/brew refusal messages

check_install_path_writable raises InstallPathNotWritable before we
spend bandwidth on a download we can't ultimately complete.
refuse_with_message prints the correct upgrade command for pip and
brew install paths and exits 1.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,permission,refusal

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: CLI subcommand wiring

Glue everything into `ait self-update`.

**Files:**
- Create: `src/ait/cli/self_update.py`
- Modify: `src/ait/cli_parser.py`
- Modify: `src/ait/cli/main.py`
- Create: `tests/self_update/test_cli_self_update.py`

- [ ] **Step 1: Write the failing test**

File: `tests/self_update/test_cli_self_update.py`

```python
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli.self_update import handle


class CliSelfUpdateTests(unittest.TestCase):
    def test_pip_install_method_returns_refusal_code(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="pip"):
            args = mock.Mock(check=False, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 1)

    def test_brew_install_method_returns_refusal_code(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="brew"):
            args = mock.Mock(check=False, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 1)

    def test_binary_already_up_to_date_returns_zero(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="binary"), \
             mock.patch("ait.cli.self_update.package_version", return_value="1.5.0"), \
             mock.patch("ait.cli.self_update.fetch_latest",
                        return_value={"tag_name": "v1.5.0"}):
            args = mock.Mock(check=False, yes=True, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 0)

    def test_check_only_returns_zero_even_when_newer_available(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="binary"), \
             mock.patch("ait.cli.self_update.package_version", return_value="1.5.0"), \
             mock.patch("ait.cli.self_update.fetch_latest",
                        return_value={"tag_name": "v1.5.1"}):
            args = mock.Mock(check=True, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.self_update.test_cli_self_update -v
```

- [ ] **Step 3: Write the CLI handler**

File: `src/ait/cli/self_update.py`

```python
"""CLI dispatch for `ait self-update`."""
from __future__ import annotations

import argparse
import sys
import urllib.request
import urllib.error
import json
import datetime as dt

from ait.cli_installation import package_version
from ait.self_update import (
    install_method,
    compare_versions,
    refuse_with_message,
    check_install_path_writable,
    download_and_verify,
    atomic_replace,
    load_cache,
    save_cache,
    is_cache_fresh,
    InstallPathNotWritable,
    ChecksumMismatch,
)


REPO = "m24927605/ait"
_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def fetch_latest() -> dict:
    """Return the latest release JSON. Honors the 1h cache."""
    now = dt.datetime.now(dt.timezone.utc)
    if is_cache_fresh(now=now):
        cached = load_cache()
        if cached is not None:
            return cached["latest"]
    with urllib.request.urlopen(_API_LATEST, timeout=15) as fh:
        data = json.loads(fh.read().decode("utf-8"))
    latest = {
        "tag_name": data.get("tag_name", ""),
        "published_at": data.get("published_at", ""),
    }
    save_cache(latest, now=now)
    return latest


def handle(args: argparse.Namespace) -> int:
    method = install_method()
    if method in ("pip", "brew", "unknown"):
        return refuse_with_message(method)

    current = package_version()
    try:
        latest = fetch_latest()
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"could not check for updates: {exc}", file=sys.stderr)
        return 1
    latest_tag = latest.get("tag_name", "")
    if not latest_tag:
        print("could not determine latest tag", file=sys.stderr)
        return 1

    cmp = compare_versions(current, latest_tag)
    if cmp >= 0 and not args.force:
        print(f"already at the latest version ({current}).")
        return 0

    print(f"Update available: {current} -> {latest_tag}")
    if args.check:
        return 0

    # Confirmation
    if not args.yes:
        prompt = f"Update ait from {current} to {latest_tag}? [Y/n]: "
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("", "y", "yes"):
            print("aborted.")
            return 0

    # Target path & permission check
    from pathlib import Path
    target = Path(sys.executable).resolve()
    try:
        check_install_path_writable(target)
    except InstallPathNotWritable as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    # Resolve target binary URL + sha256 for the running platform
    import platform
    sys_platform = platform.system().lower()
    arch = platform.machine().lower()
    if sys_platform == "darwin" and arch == "arm64":
        target_name = "macos-arm64"
    elif sys_platform == "darwin" and arch in ("x86_64", "amd64"):
        target_name = "macos-x86_64"
    elif sys_platform == "linux" and arch in ("x86_64", "amd64"):
        target_name = "linux-x86_64"
    elif sys_platform == "linux" and arch in ("aarch64", "arm64"):
        target_name = "linux-arm64"
    else:
        print(f"no binary available for {sys_platform}/{arch}",
              file=sys.stderr)
        return 1

    binary_url = (
        f"https://github.com/{REPO}/releases/download/{latest_tag}/"
        f"ait-{latest_tag}-{target_name}"
    )
    checksums_url = (
        f"https://github.com/{REPO}/releases/download/{latest_tag}/"
        f"ait-{latest_tag}-checksums.txt"
    )

    # Download checksums, find ours
    try:
        with urllib.request.urlopen(checksums_url, timeout=15) as fh:
            sums = fh.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"could not fetch checksums: {exc}", file=sys.stderr)
        return 1
    expected_sha = ""
    for line in sums.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == f"ait-{latest_tag}-{target_name}":
            expected_sha = parts[0]
            break
    if not expected_sha:
        print(f"no checksum for ait-{latest_tag}-{target_name}", file=sys.stderr)
        return 1

    # Download binary + verify
    print("Downloading new binary...")
    try:
        content = download_and_verify(binary_url, expected_sha256=expected_sha)
    except (urllib.error.URLError, ChecksumMismatch) as exc:
        print(f"download/verify failed: {exc}", file=sys.stderr)
        return 1

    # Atomic replace
    atomic_replace(target, content)
    print(f"Updated to {latest_tag}. Run `ait --version` to verify.")
    return 0
```

- [ ] **Step 4: Register the subcommand in the argparse layer**

Read `src/ait/cli_parser.py` to find the top-level subparsers (`subparsers = parser.add_subparsers(...)`). Find where existing subcommands are registered (e.g. `bug_report` from prior work). Add:

```python
    self_update_parser = subparsers.add_parser("self-update")
    self_update_parser.add_argument("--check", action="store_true",
                                    help="check for updates without downloading")
    self_update_parser.add_argument("--yes", action="store_true",
                                    help="skip the confirmation prompt")
    self_update_parser.add_argument("--force", action="store_true",
                                    help="update even if current >= latest")
    self_update_parser.add_argument("--json", action="store_true",
                                    help="machine-readable output for agents")
```

- [ ] **Step 5: Register the dispatch in `src/ait/cli/main.py`**

Read the existing `_HANDLERS` dispatch dict (the pattern was used for the bug-report subcommand). Add a corresponding entry:

```python
from ait.cli import self_update as self_update_cli
# ... inside the _HANDLERS dict or equivalent dispatch ...
"self-update": self_update_cli.handle,
```

Follow the project's existing pattern exactly — do not introduce a different dispatch shape.

- [ ] **Step 6: Run all self_update tests**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/self_update -v
```

Expected: all green.

- [ ] **Step 7: Smoke the CLI**

```bash
PYTHONPATH=src .venv/bin/python -m ait.cli self-update --help
PYTHONPATH=src .venv/bin/python -m ait.cli self-update --check
```

Expected:
- `--help` prints the subcommand help.
- `--check` prints `You installed ait via pip. Run \`pip install --upgrade ait-vcs\` instead.` and exits 1 (because in this dev environment `sys.frozen` is False).

- [ ] **Step 8: Commit**

```bash
git add src/ait/cli/self_update.py src/ait/cli_parser.py src/ait/cli/main.py tests/self_update/test_cli_self_update.py
git commit -m "$(cat <<'EOF'
feat(cli): ait self-update subcommand

Wires install_method dispatch, semver compare, atomic-replace, sha256
verify, and the cache into a single CLI handler. Refuses cleanly when
the user installed via pip or brew. In dev (non-frozen) environments
the dispatch returns the pip refusal because sys.frozen is False —
that's correct: only the frozen binary should ever attempt
self-update.

docs:docs/superpowers/specs/2026-05-29-standalone-binary-design.md,docs/superpowers/plans/2026-05-29-standalone-binary-plan.md
keyword:standalone-binary,self-update,cli

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 5 — Documentation

## Task 17: README install section + new docs

**Files:**
- Modify: `README.md`
- Modify: `README.zh-TW.md`
- Create: `docs/install.md`
- Create: `docs/self-update.md`
- Modify: `docs/release-checklist.md`
- Modify: `docs/ait-rebrand-qa-reality.md`

- [ ] **Step 1: Update README install section**

In `README.md`, find the existing install section (currently it just says `pip install ait-vcs`). Replace with a three-path section:

```markdown
## Install

**Recommended for macOS:**

```bash
brew tap m24927605/ait
brew install ait
```

**curl install script (macOS + Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
```

**pip (any Python ≥ 3.11):**

```bash
pip install ait-vcs        # or: pipx install ait-vcs
```

Verify with `ait --version`. See [docs/install.md](docs/install.md)
for per-platform detail, offline install, and uninstall.
```

Repeat the equivalent edit in `README.zh-TW.md` (Chinese strings).

- [ ] **Step 2: Write `docs/install.md`**

File: `docs/install.md`

```markdown
# Installing `ait`

`ait` ships through three channels. Pick whichever fits.

## Homebrew (macOS, recommended)

```bash
brew tap m24927605/ait
brew install ait
ait --version
```

Updates: `brew upgrade ait`.

Brew strips `com.apple.quarantine` on install, so the ad-hoc-signed
binary runs without Gatekeeper prompts.

## curl install script (macOS + Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
```

Behind the scenes the script:

1. Detects your OS and CPU from `uname`.
2. Resolves the latest tag from `api.github.com/repos/m24927605/ait/releases/latest`.
3. Picks `/usr/local/bin` if writable, else `~/.local/bin`.
4. Downloads the binary and the release's `checksums.txt`.
5. Verifies SHA256.
6. On macOS, removes `com.apple.quarantine`.
7. `chmod +x`, mv into place.

Options:

```bash
curl -fsSL https://... | sh -s -- --version v1.5.1
curl -fsSL https://... | sh -s -- --prefix ~/.local
curl -fsSL https://... | sh -s -- --no-checksum   # not recommended
```

Updates: re-run the install command (downloads the latest tag and
overwrites). Or use `ait self-update` (see below).

## pip / pipx

```bash
pip install ait-vcs          # in a venv
pipx install ait-vcs         # isolated install
```

Requires Python ≥ 3.11.

Updates: `pip install --upgrade ait-vcs` (or `pipx upgrade ait-vcs`).

## Offline install (binary)

Download the binary and checksums for your platform from
<https://github.com/m24927605/ait/releases>:

```bash
sha256sum -c <(grep ait-v1.5.1-linux-x86_64 ait-v1.5.1-checksums.txt)
chmod +x ait-v1.5.1-linux-x86_64
sudo mv ait-v1.5.1-linux-x86_64 /usr/local/bin/ait
ait --version
```

## Verifying a binary

Every release publishes `ait-<tag>-checksums.txt` next to the binaries.

```bash
curl -LO https://github.com/m24927605/ait/releases/download/v1.5.1/ait-v1.5.1-checksums.txt
curl -LO https://github.com/m24927605/ait/releases/download/v1.5.1/ait-v1.5.1-linux-x86_64
sha256sum -c <(grep ait-v1.5.1-linux-x86_64 ait-v1.5.1-checksums.txt)
```

## Uninstall

- **Brew:** `brew uninstall ait && brew untap m24927605/ait`
- **curl install:** `rm <prefix>/ait` (default `/usr/local/bin/ait`
  or `~/.local/bin/ait`). State under `~/.config/ait` and
  `~/.local/state/ait` is left in place — remove manually if desired.
- **pip:** `pip uninstall ait-vcs`

## Platforms

| Target | Binary name | Built on |
|---|---|---|
| macOS arm64 (Apple Silicon) | `ait-<tag>-macos-arm64` | macos-latest |
| macOS x86_64 (Intel) | `ait-<tag>-macos-x86_64` | macos-13 |
| Linux x86_64 | `ait-<tag>-linux-x86_64` | ubuntu-latest |
| Linux arm64 | `ait-<tag>-linux-arm64` | ubuntu-24.04-arm |

Windows: not supported in v1; use the pip path under WSL or native
Python 3.11+.
```

- [ ] **Step 3: Write `docs/self-update.md`**

File: `docs/self-update.md`

```markdown
# `ait self-update`

Built-in updater for the standalone binary.

## Usage

```bash
ait self-update            # interactive
ait self-update --yes      # no prompt
ait self-update --check    # check only, don't download
ait self-update --force    # update even if already at latest
ait self-update --json     # machine-readable output for agents
```

## Behavior by install method

`ait self-update` first detects how the binary was installed:

| Method | Behavior |
|---|---|
| Brew | Refuses with `"Run \`brew upgrade ait\` instead."` exit 1 |
| pip | Refuses with `"Run \`pip install --upgrade ait-vcs\` instead."` exit 1 |
| Standalone binary | Runs the update flow below |

## Update flow

1. Read current version from the binary's embedded `__version__`.
2. Query `api.github.com/repos/m24927605/ait/releases/latest`. Cached
   for 1 hour at `$XDG_STATE_HOME/ait/self_update_cache.json`.
3. Compare. If current ≥ latest, exit 0 ("Already at latest").
4. Show the update plan. Prompt `[Y/n]` unless `--yes`.
5. Check that the install dir is writable. If not, print a sudo hint
   and exit 1 *before* downloading.
6. Download the platform-specific binary and the release's
   `checksums.txt`.
7. Verify SHA256.
8. Atomic-replace via `mkstemp` + `os.replace` (POSIX same-filesystem).

## Failure modes

- **Network failure** → exit 1, original binary untouched.
- **Checksum mismatch** → exit 1, original binary untouched.
- **Permission denied** → exit 1 *before* the download, sudo hint
  printed.
- **`sys.frozen` not set** (e.g. running from pip) → refuses with the
  pip upgrade hint.

## Self-replace safety

POSIX allows `unlink`/`replace` of a currently-executing binary. The
running process holds the inode of the old binary; the new file lives
at a new inode. The currently-running `ait self-update` completes
normally; the next invocation picks up the new binary. Linux and
macOS both safe. Windows is not supported.
```

- [ ] **Step 4: Update `docs/release-checklist.md`**

Read the existing checklist. Append a section:

```markdown

## Binary release pipeline

The binary pipeline (PyInstaller build, checksums, Brew tap update)
runs via `.github/workflows/release-binary.yml`. It is triggered by
the same `release: types: [published]` event as the PyPI publish
workflow.

Before the first release that ships binaries:

1. Create the tap repo: see `scripts/homebrew-tap-template/SETUP.md`.
2. Generate the `TAP_PUSH_TOKEN` PAT and add it to the main repo's
   Actions secrets.

Per release:

1. Cut the release as usual (`gh release create vX.Y.Z`).
2. Watch the `Release Binary` workflow run. Four binaries upload to
   the release; checksums lands next; tap formula updates.
3. Smoke-install on at least one platform:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh
   ait --version       # expect: ait X.Y.Z
   ```
4. Smoke `brew upgrade ait` on a Mac you have brew on.

If the build job fails for a platform, fix the cause (typically a
missing `hiddenimport` in `build/ait.spec`) and re-run via
`workflow_dispatch`.
```

- [ ] **Step 5: Mark the QA tracker entry resolved**

In `docs/ait-rebrand-qa-reality.md`, find the H6 resolution note left by Spec A and extend it:

```markdown
> **Resolved 2026-05-29.** Floor lowered to 3.11 per
> `docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md`.
> Standalone binary release (Spec B) — see
> `docs/superpowers/specs/2026-05-29-standalone-binary-design.md` —
> additionally ships `brew install ait` and curl|sh paths so install
> works without any Python at all.
```

- [ ] **Step 6: Commit**

```bash
git add README.md README.zh-TW.md docs/install.md docs/self-update.md \
        docs/release-checklist.md docs/ait-rebrand-qa-reality.md
git commit -m "$(cat <<'EOF'
docs: install paths, self-update guide, release checklist

README install section restructured: brew first (Mac recommended),
curl|sh second, pip third. New docs/install.md covers all three plus
offline install and uninstall. New docs/self-update.md covers usage,
install-method dispatch, and the atomic-replace flow.
release-checklist.md gains a "Binary release pipeline" section
explaining the one-time tap setup and per-release verification.
QA tracker entry extended to note the install cliff is now fully
resolved via the binary path.

docs:README.md,README.zh-TW.md,docs/install.md,docs/self-update.md,docs/release-checklist.md,docs/ait-rebrand-qa-reality.md,docs/superpowers/specs/2026-05-29-standalone-binary-design.md
keyword:standalone-binary,docs,install,self-update

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Final integration smoke

Build a binary locally and smoke the entire flow end-to-end.

**Files:** none (verification only)

- [ ] **Step 1: Full clean rebuild**

```bash
rm -rf build/dist build/build
./build/build_binary.sh
```

Expected: `Built: <repo>/build/dist/ait` followed by `ait 1.5.0`.

- [ ] **Step 2: Run binary_smoke against the fresh build**

```bash
.venv/bin/python scripts/release-smoke/binary_smoke.py build/dist/ait
echo "exit=$?"
```

Expected: exit 0.

- [ ] **Step 3: Confirm `--version` and one functional subcommand work**

```bash
./build/dist/ait --version
./build/dist/ait --help | head -20
```

Expected: shows version + help.

- [ ] **Step 4: Run the full unit test suite**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests 2>&1 | tail -5
```

Expected: 970+ tests, OK. The new tests under `tests/self_update/` and
`tests/release_smoke/` are part of this count.

- [ ] **Step 5: Run binary self-update flow (refuses appropriately in dev)**

```bash
./build/dist/ait self-update --check
```

Expected: prints something like `Update available: 1.5.0 -> v1.5.1`
if a real newer release exists, OR `already at the latest version
(1.5.0).` if 1.5.0 is the latest.

If no real release exists yet (likely during this development cycle),
expect a network error message about not being able to fetch the
release info — which is the correct behavior given the binary isn't
yet published.

- [ ] **Step 6: No commit — verification only**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

---

# Self-review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| Build tool (PyInstaller) | T1 |
| Repository surface | T1, T2, T3, T4, T5, T8, T9, T10–T16 |
| Storage layout for self_update cache | T12 |
| Install method detection | T10 |
| Version embedding via `_frozen_version.py` | T1, T2 |
| Build CI workflow (build, checksums, update-tap) | T5, T6, T7 |
| `install.sh` | T8 |
| Homebrew tap | T9 (template + setup guide) |
| `ait self-update` flow | T10, T11, T12, T13, T14, T15, T16 |
| Tests (per spec § Tests) | T2, T3, T4, T10, T11, T12, T13, T14, T15, T16 |
| Documentation deltas | T17 |
| Manual acceptance | T18 (local) + maintainer post-release steps in T17's release-checklist update |

**Placeholder scan:** Searched plan for "TBD", "TODO", "implement later", "Similar to Task N", "Add appropriate error handling" — none present. The phrase "(currently it just says...)" in Task 17 Step 1 is a present-tense reference to the file's pre-change state; engineers should grep the file to find the existing content.

**Type consistency:**

| Symbol | Defined in | Used in |
|---|---|---|
| `install_method() -> str` | T10 | T16, T17 |
| `compare_versions(a, b) -> int` | T11 | T16 |
| `cache_path() -> Path` | T12 | T12 tests |
| `save_cache(latest, *, now)` | T12 | T16 |
| `load_cache() -> dict \| None` | T12 | T16 |
| `is_cache_fresh(*, now) -> bool` | T12 | T16 |
| `download_and_verify(url, *, expected_sha256)` | T13 | T16 |
| `atomic_replace(target, content)` | T14 | T16 |
| `check_install_path_writable(target)` | T15 | T16 |
| `refuse_with_message(method)` | T15 | T16 |
| `ChecksumMismatch` exception | T13 | T16 |
| `InstallPathNotWritable` exception | T15 | T16 |
| `SmokeFailure` exception | T3 | T18 (binary smoke step) |
| `parse_checksums`, `render_formula` | T4 | T9 (template smoke), CI T7 |

All signatures match where used.

**Scope check:** One feature, one branch. CI and self_update could theoretically be separate sub-projects, but the spec intentionally bundled them so that v1 ships a complete usable binary pipeline. Keep as one plan.

**One outstanding gap** intentionally accepted: the plan can't actually verify the end-to-end CI workflow without a real release tag. T17's release-checklist update is the maintainer's playbook for that.

---

# Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-29-standalone-binary-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Recommended here because several tasks touch existing modules (`cli_installation.py`, `cli_parser.py`, `cli/main.py`) where the existing pattern matters more than the plan's hypothetical structure — fresh-context subagents are good at adapting.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.
