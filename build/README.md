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
