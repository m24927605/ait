#!/bin/bash
# build/build_binary.sh — local reproducible build entry for ait standalone binary.
#
# Usage:
#   ./build/build_binary.sh
#
# Prereqs:
#   - python on PATH (any Python >= 3.11)
#   - pip install pyinstaller==6.* (one-time per Python install)
#
# Output:
#   build/dist/ait

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

python -c "
import tomllib, pathlib
data = tomllib.load(open('pyproject.toml','rb'))
v = data['project']['version']
out = pathlib.Path('src/ait/_frozen_version.py')
out.write_text(f\"__version__ = {v!r}\n\", encoding='utf-8')
print(f'wrote {out} with version {v}')
"

if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "ERROR: PyInstaller is not installed in this Python. Run:" >&2
    echo "  pip install 'pyinstaller==6.*'" >&2
    exit 1
fi

cd build
pyinstaller --clean --noconfirm ait.spec

binary="$REPO_ROOT/build/dist/ait"
if [[ -x "$binary" ]]; then
    echo "Built: $binary"
    "$binary" --version || true
else
    echo "ERROR: build did not produce $binary" >&2
    exit 1
fi
