# Standalone Binary Release Pipeline

Date: 2026-05-29
Scope: ship `ait` as a single-file native binary via GitHub Releases,
`curl|sh` installer, and a Homebrew tap — in addition to the existing
pip / npm channels. Includes built-in `ait self-update`.

## Problem

Today `ait` only ships through pip and an npm wrapper that calls pip
underneath. Both paths still require the user to have a recent Python
installed and on PATH. Even after lowering the floor to Python 3.11
(sibling spec `2026-05-29-python-floor-3-11-design.md`), some users:

- Don't want to manage a Python environment for a CLI tool.
- Hit PEP 668 "externally managed environment" errors on system Python.
- Are on machines where the bundled Python is too old (default macOS
  Python is 3.9, Ubuntu 22.04 is 3.10).
- Just want `brew install ait` or `curl ... | sh` like every other dev
  tool they use.

## Goal

Ship `ait` as a self-contained native binary so that **no Python install
is required at the user's machine**. Make the install one command on
macOS and Linux, with verified checksums and automatic updates via
`brew upgrade` or `ait self-update`.

Coexist with pip — existing pip users are unaffected.

## Non-goals (v1)

- Windows binary. macOS / Linux cover the dominant developer base; WSL
  users can use the Linux binary.
- Apple Developer ID signing + notarization. $99/yr + maintenance.
  Defer until adoption justifies. v1 uses ad-hoc codesign which is
  sufficient on Apple Silicon and Brew strips quarantine.
- musl Linux binary (Alpine). glibc binary usually runs under `gcompat`;
  edge users go through pip.
- Linux distro packages (apt / rpm / snap).
- Passive update hint at every `ait` invocation. Only the explicit
  `ait self-update` exists.
- Multi-version coexistence (`ait@1.4` style aliases).
- Replacing pip publishing. Both channels coexist.

## Platforms

Four binaries per release:

| Target | GH Actions runner |
|---|---|
| `macos-arm64` | `macos-latest` |
| `macos-x86_64` | `macos-13` |
| `linux-x86_64` | `ubuntu-latest` |
| `linux-arm64` | `ubuntu-24.04-arm` |

## Channels

Three install paths, in maintainer-recommended order:

1. **Homebrew tap** (primary for macOS):
   `brew install m24927605/ait/ait`. Tap repo at
   `github.com/m24927605/homebrew-ait`. CI auto-updates the formula on
   each release.

2. **curl install script** (Linux + Mac users without brew):
   `curl -fsSL https://raw.githubusercontent.com/m24927605/ait/main/install.sh | sh`.
   Detects platform, downloads the right binary, verifies SHA256,
   installs to `/usr/local/bin` (or `~/.local/bin` if not writable).

3. **GitHub Releases direct download** (offline, CI, scripts):
   Per-release attachments with checksums file.

Existing pip / npm channels keep working unchanged.

## Architecture

### Build tool

PyInstaller, `--onefile`. Mature, well-supported by the Python CLI
ecosystem (`aws`, `gcloud`, `black`, etc.). ~50 MB binary, ~500 ms
cold-start cost from `/tmp` extraction. Tradeoff accepted in v1; Nuitka
or PyOxidizer can be reconsidered later if binary size or startup
become friction.

### Repository surface

```
.github/workflows/
  release-binary.yml          # new — build + checksums + tap update
build/
  ait.spec                    # PyInstaller spec
  hooks/                      # PyInstaller runtime hooks (if any)
  build_binary.sh             # local reproducible build entry
install.sh                    # root — curl|sh entry
src/ait/
  _frozen_version.py          # GENERATED at build time, gitignored
  self_update.py              # implementation
  cli/self_update.py          # CLI subcommand
scripts/release-smoke/
  binary_smoke.py             # smoke a built binary in hermetic tmpdir
  render_brew_formula.py      # render homebrew-ait Formula/ait.rb
homebrew-ait/                 # NEW SEPARATE repo: m24927605/homebrew-ait
  Formula/ait.rb
  README.md
```

### Install-method detection (runtime)

```python
def install_method() -> str:
    """Returns: 'pip' | 'brew' | 'binary' | 'unknown'."""
    if not getattr(sys, "frozen", False):
        return "pip"
    exe = Path(sys.executable).resolve()
    if "/Cellar/" in str(exe) and "/ait/" in str(exe):
        return "brew"
    return "binary"
```

This drives `ait self-update`'s dispatch (see § Self-update).

### Version embedding

PyInstaller binary can't `tomllib.load("pyproject.toml")` at runtime.
Build CI injects a generated module:

```bash
# In .github/workflows/release-binary.yml, before PyInstaller runs:
python -c '
import tomllib
v = tomllib.load(open("pyproject.toml","rb"))["project"]["version"]
open("src/ait/_frozen_version.py","w").write(f"__version__ = {v!r}\n")
'
```

`_frozen_version.py` is in `.gitignore`. Runtime lookup:

```python
# src/ait/cli_installation.py
def package_version() -> str:
    if getattr(sys, "frozen", False):
        try:
            from ait._frozen_version import __version__
            return __version__
        except ImportError:
            return "unknown"
    # ...existing pyproject.toml read path for the pip case...
```

## PyInstaller spec

`build/ait.spec`:

```python
a = Analysis(
    ["../src/ait/__main__.py"],
    pathex=["../src"],
    binaries=[],
    datas=[("../src/ait/resources", "ait/resources")],
    hiddenimports=[
        "ait.bug_report",
        "ait.bug_report.api",
        "ait.bug_report.collector",
        "ait.bug_report.excepthook",
        # The full list is enumerated by the implementation task in two
        # passes: first build with `pyinstaller --collect-all ait build/ait.spec`
        # to capture everything statically reachable, then prune by repeatedly
        # running `binary_smoke.py` and adding any import that surfaces a
        # ModuleNotFoundError. Final list is what survives both passes.
    ],
    hookspath=["hooks"],
    runtime_hooks=[],
    excludes=["test", "tests", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="ait",
    onefile=True,
    console=True,
    strip=True,
    upx=False,                # UPX often gets false-positive AV flags
    target_arch=None,         # GH runner's native arch
)
```

`hiddenimports` final list is determined empirically during the
implementation plan, not pre-listed in this spec — anything loaded via
`importlib.import_module` or dynamic plugin discovery must be enumerated
once the build runs.

## CI workflow

`.github/workflows/release-binary.yml`:

```yaml
name: Release Binary
on:
  release: { types: [published] }
  workflow_dispatch:

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
        with: { python-version: "3.14" }
      - name: Install build deps
        run: pip install pyinstaller==6.* -e .
      - name: Inject frozen version
        run: |
          python -c '
          import tomllib
          v = tomllib.load(open("pyproject.toml","rb"))["project"]["version"]
          open("src/ait/_frozen_version.py","w").write(f"__version__ = {v!r}\n")
          '
      - name: Build binary
        working-directory: build
        run: pyinstaller --clean --noconfirm ait.spec
      - name: Rename
        run: |
          mkdir -p dist
          mv build/dist/ait dist/ait-${{ github.event.release.tag_name }}-${{ matrix.target }}
      - name: macOS ad-hoc sign
        if: startsWith(matrix.target, 'macos')
        run: codesign --sign - --force --options runtime dist/ait-*
      - name: Smoke
        run: python scripts/release-smoke/binary_smoke.py dist/ait-*
      - name: Upload to release
        uses: softprops/action-gh-release@v2
        with: { files: dist/ait-* }

  checksums:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download release assets
        env: { GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
        run: |
          mkdir -p dist
          gh release download ${{ github.event.release.tag_name }} \
            -R ${{ github.repository }} \
            -p 'ait-*' -D dist/
      - name: SHA256
        run: |
          cd dist
          sha256sum ait-* > ait-${{ github.event.release.tag_name }}-checksums.txt
      - uses: softprops/action-gh-release@v2
        with: { files: dist/ait-*-checksums.txt }

  update-tap:
    needs: checksums
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          repository: m24927605/homebrew-ait
          token: ${{ secrets.TAP_PUSH_TOKEN }}
          path: tap
      - name: Download checksums
        run: |
          curl -fsSL \
            "https://github.com/m24927605/ait/releases/download/${{ github.event.release.tag_name }}/ait-${{ github.event.release.tag_name }}-checksums.txt" \
            -o checksums.txt
      - uses: actions/checkout@v5
        with: { path: ait }
      - name: Render formula
        run: |
          python ait/scripts/release-smoke/render_brew_formula.py \
            --version "${{ github.event.release.tag_name }}" \
            --checksums checksums.txt \
            --output tap/Formula/ait.rb
      - name: Commit and push
        working-directory: tap
        run: |
          git config user.email "noreply@github.com"
          git config user.name "release-bot"
          git add Formula/ait.rb
          git commit -m "ait ${{ github.event.release.tag_name }}"
          git push
```

Required secret: `TAP_PUSH_TOKEN` — a fine-grained GitHub PAT scoped to
write to `m24927605/homebrew-ait` only.

## install.sh

POSIX sh (not bash), ~100 lines. Lives at the repo root and is served
via raw.githubusercontent.com.

Behaviour:

- Detect `os` and `arch` from `uname`. Supports the 4 target tuples.
- Resolve `latest` tag via GitHub API unless `--version` passed.
- Pick install prefix: `/usr/local/bin` if writable, else
  `~/.local/bin`. Override with `--prefix`.
- Download binary + checksums file. Verify SHA256 unless
  `--no-checksum` (off by default; rejecting the install is the safer
  default).
- On macOS: `xattr -d com.apple.quarantine` best-effort.
- `chmod +x`, atomic rename into place.
- Print a warning if the install prefix isn't on `PATH`.
- Verify with `ait --version`.

Full source is in § "install.sh" of the brainstorm transcript (≈100
lines POSIX shell). The implementation plan reproduces it verbatim.

Hosting: `raw.githubusercontent.com/m24927605/ait/main/install.sh`. If
the project later registers a domain (e.g. `ait.dev`), redirect there.

## Homebrew tap

Separate public repo `m24927605/homebrew-ait` (`homebrew-` prefix is a
Brew convention so users can do `brew tap m24927605/ait`).

`Formula/ait.rb`:

```ruby
class Ait < Formula
  desc "AI-agent-native VCS layer that turns AI coding into reviewable attempts"
  homepage "https://github.com/m24927605/ait"
  version "1.5.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-arm64"
      sha256 "<SHA256_OF_MACOS_ARM64>"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-macos-x86_64"
      sha256 "<SHA256_OF_MACOS_X86_64>"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-arm64"
      sha256 "<SHA256_OF_LINUX_ARM64>"
    end
    on_intel do
      url "https://github.com/m24927605/ait/releases/download/v1.5.0/ait-v1.5.0-linux-x86_64"
      sha256 "<SHA256_OF_LINUX_X86_64>"
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

The four `<SHA256_OF_…>` placeholders are filled in by
`render_brew_formula.py` (~50-line helper) from the checksums file.

Brew automatically strips `com.apple.quarantine` so even ad-hoc-signed
binaries install cleanly via `brew install`.

One-time setup for the tap (executed by the maintainer at
implementation time, not by CI):

```bash
gh repo create m24927605/homebrew-ait --public \
  --description "Homebrew tap for ait"
# seed with placeholder Formula/ait.rb and README.md
# set TAP_PUSH_TOKEN secret in m24927605/ait
```

## `ait self-update`

Subcommand of the `ait` CLI. Implementation in `src/ait/self_update.py`
plus thin argparse wiring in `src/ait/cli/self_update.py`.

CLI surface:

```
ait self-update [OPTIONS]

OPTIONS:
  --check       Only check for an update, don't download
  --yes         Skip confirmation prompt
  --force       Update even if already at latest
  --json        Machine-readable output for agents
```

### Dispatch by install method

| Method | Behaviour |
|---|---|
| `pip` | `print("You installed ait via pip. Run `pip install --upgrade ait-vcs` instead.")` exit 1 |
| `brew` | `print("You installed ait via Homebrew. Run `brew upgrade ait` instead.")` exit 1 |
| `binary` | Run the update flow below |
| `unknown` | Warn that install method couldn't be determined and ask y/N to proceed as `binary` |

### Binary update flow

1. **Resolve current version** via `package_version()` (reads
   `_frozen_version.__version__`).
2. **Query GitHub Releases API** for `latest`. Cache the JSON for 1 hour
   at `XDG_STATE_HOME/ait/self_update_cache.json` so back-to-back
   invocations don't hit the API.
3. **Compare versions** via `packaging.version.Version` — but
   `packaging` is third-party. Substitute with `tuple(map(int, v.lstrip('v').split('.')))` semver-3 parsing; AIT's versions are always `MAJOR.MINOR.PATCH`. Reject `--force = false` if current ≥ latest.
4. **Show plan** to the user. Prompt `[Y/n]` unless `--yes`:

   ```
   Update ait from 1.5.0 to 1.5.1?
     - Source: github.com/m24927605/ait/releases/download/v1.5.1/ait-v1.5.1-macos-arm64
     - Install path: /usr/local/bin/ait
   Continue? [Y/n]
   ```

5. **Download** new binary + checksums to a temp file in the same
   directory as the install path (so `os.replace` is same-filesystem).
6. **Verify SHA256** against the release's `checksums.txt`. Mismatch →
   abort, leave existing binary in place.
7. **Permission check**: `os.access(install_dir, os.W_OK)`. If not
   writable, print a clear "re-run with sudo or change install path"
   error and exit 1 *before* downloading (don't waste a 50 MB
   download).
8. **Atomic rename**:
   - `tempfile.mkstemp(dir=install_dir, prefix=".ait.new.")`
   - Write content, `chmod 0o755`
   - macOS: `xattr -d com.apple.quarantine` best-effort
   - `os.replace(tmp, target)` — atomic on POSIX same-FS
9. **Print result**: `Updated to 1.5.1. Run \`ait --version\` to
   verify.`

### Self-replace safety

POSIX allows `unlink`/`replace` of a currently-executing binary. The
kernel holds the inode of the running process; the new file lives at a
new inode. The currently-running process completes normally; the next
invocation picks up the new binary. Linux + macOS both safe. Windows
breaks here but Windows is a non-goal.

### Cache schema

`<XDG_STATE_HOME>/ait/self_update_cache.json`:

```json
{
  "schema_version": 1,
  "fetched_at": "2026-05-29T10:00:00Z",
  "ttl_seconds": 3600,
  "latest": {
    "tag_name": "v1.5.1",
    "published_at": "2026-05-28T12:00:00Z",
    "asset_urls": {
      "macos-arm64": "https://github.com/.../ait-v1.5.1-macos-arm64",
      "macos-x86_64": "...",
      "linux-x86_64": "...",
      "linux-arm64": "..."
    },
    "checksums_url": "https://github.com/.../ait-v1.5.1-checksums.txt"
  }
}
```

### Tests

stdlib `unittest`, `tests/self_update/`:

| File | Coverage |
|---|---|
| `test_install_method.py` | mock `sys.frozen` + path; verify pip / brew / binary / unknown |
| `test_version_compare.py` | semver 3-tuple parsing; equal / older / newer; v-prefix handling |
| `test_atomic_replace.py` | tmp + replace lands target; failure path leaves old binary |
| `test_permission_check.py` | non-writable dir returns clean error without downloading |
| `test_cache.py` | 1h TTL respected; cache miss triggers refetch; stale → refetch |
| `test_cli_self_update.py` | argparse + dispatch table; `--check`, `--yes`, `--force`, `--json` |
| `test_dispatch_refusals.py` | pip / brew methods refuse with the expected message |

All mock `urllib.request` and `subprocess` — no network or real file
replaces outside `tmpdir`.

## Release smoke for binaries

`scripts/release-smoke/binary_smoke.py` runs in each CI build job and
locally before tag:

```python
def smoke(binary_path: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        env = {
            "HOME": td,
            "XDG_CONFIG_HOME": td,
            "XDG_STATE_HOME": td,
            "AIT_BUG_REPORT": "never",
            "PATH": os.environ["PATH"],
        }
        # 1. --version matches embedded version
        r = subprocess.run([binary_path, "--version"],
                           capture_output=True, env=env, text=True, timeout=10)
        assert r.returncode == 0
        assert PACKAGE_VERSION in r.stdout

        # 2. bug-report list works (PyInstaller bundled resources OK)
        r = subprocess.run([binary_path, "bug-report", "list"],
                           capture_output=True, env=env, text=True, timeout=10)
        assert r.returncode == 0

        # 3. init creates a .ait dir
        repo = Path(td) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, env=env)
        r = subprocess.run([binary_path, "init"], cwd=repo,
                           capture_output=True, env=env, timeout=10)
        assert r.returncode == 0
        assert (repo / ".ait").exists()
```

If any assertion fails, CI marks the build job red and the release
fails to attach that platform's binary. Brew tap update job is gated
on `checksums` so a partial release won't half-update Brew.

## Documentation deltas

| File | Change |
|---|---|
| `README.md` | Install section: 3 paths (brew / curl\|sh / pip) in that order with version-prominent snippets |
| `docs/install.md` (new) | Per-platform detail, checksum verification, offline install, uninstall |
| `docs/self-update.md` (new) | `ait self-update` usage, install-method dispatch, failure modes, permission notes |
| `docs/release-checklist.md` | Add "Binary build" and "Brew tap" sections to the release procedure |
| `homebrew-ait/README.md` (new repo) | tap usage; how to override version via `brew install ait@1.4` if multi-version is ever added (currently not) |
| `docs/ait-rebrand-qa-reality.md` | Note that the install cliff is now resolved by the binary + 3.11-floor combo |

## Release sequence

1. Maintainer:
   - Bump `pyproject.toml` version + `npm/ait-vcs/package.json`
   - Update `CHANGELOG`
   - Commit + push
   - `gh release create v1.5.1 --generate-notes`
2. CI fans out:
   - `publish.yml`: PyPI wheel + sdist + npm smoke (existing)
   - `release-binary.yml` build matrix: 4 binaries
   - `release-binary.yml` checksums: aggregate SHA256
   - `release-binary.yml` update-tap: push new formula
3. Within ~5 min wall clock: all channels at the new version.

## Risks

| Risk | Mitigation |
|---|---|
| PyInstaller hiddenimports incomplete | `binary_smoke.py` catches at CI; iterate `hiddenimports` list until smoke passes |
| Linux arm64 GH-hosted runner unavailable / quota | `ubuntu-24.04-arm` is GA and free for public repos as of 2025; private-repo fallback is `qemu-user-static` cross-build (defer to v2 if needed) |
| GitHub API rate limit on `install.sh` (unauthenticated 60 req/hr/IP) | Mostly fine for individual installs; popular spikes can pre-fetch `latest` then pin with `--version` |
| Brew tap push fails after binaries up | update-tap job emails on failure; release notes mention "brew tap update in progress" |
| `ait self-update` partial download leaves bad binary | Same-FS `mkstemp` + `os.replace` atomic; on failure tmp file cleaned up; original binary untouched |
| User runs `ait self-update` from pip install | `install_method` detection returns `pip` → refuse with helpful message |
| User runs `ait self-update` without write perms | Permission check before download, clear sudo guidance |
| `_frozen_version.py` generation diverges from `pyproject.toml` in dev workflows | File is gitignored and CI-only; dev runs go through the pyproject reading path so they always have the real version |

## References

- `pyproject.toml` — single version source of truth
- `docs/release-checklist.md` — existing release process this extends
- `.github/workflows/publish.yml` — existing PyPI publish template
- `npm/ait-vcs/package.json` — existing companion channel
- `docs/superpowers/specs/2026-05-29-python-floor-3-11-design.md` —
  sibling spec, lands first
- `docs/ait-rebrand-qa-reality.md` — original install-cliff complaint
- `CLAUDE.md` — commit checklist; this spec produces multi-commit work
