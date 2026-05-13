#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/demo.sh
. "$SCRIPT_DIR/lib/demo.sh"

require_command git
require_command node
require_command npm
require_command python3
require_command "$AIT_BIN"

info "resetting demo workspace: $DEMO_WORKSPACE"
rm -rf "$DEMO_WORKSPACE" "$DEMO_STATE_DIR"
mkdir -p "$DEMO_WORKSPACE"
cd "$DEMO_WORKSPACE"

git init -b main
mkdir -p src test

cat > package.json <<'JSON'
{"scripts":{"test":"node --test"},"type":"module"}
JSON

cat > src/calculator.js <<'JS'
export function add(a, b) {
  return a + b;
}
JS

cat > test/calculator.test.js <<'JS'
import test from 'node:test';
import assert from 'node:assert/strict';
import { add } from '../src/calculator.js';

test('add', () => {
  assert.equal(add(2, 3), 5);
});
JS

npm test
git add .
git -c user.name=Demo -c user.email=demo@example.com commit -m "seed demo app"

# Avoid capturing another repo's .ait/bin wrapper as the "real" Claude/Codex
# binary when this setup script is run from an already AIT-enabled shell.
PATH="$(python3 -c 'import os,sys; print(os.pathsep.join(p for p in sys.argv[1].split(os.pathsep) if not p.endswith("/.ait/bin")))' "$PATH")"
export PATH

"$AIT_BIN" init --adapter claude-code --adapter codex --no-shell-install
python3 <<'PY'
from __future__ import annotations

import json
from pathlib import Path


def patch_settings(path: Path, *, project_var: str, hook_ref: str) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))

    def walk(value):
        if isinstance(value, dict):
            command = value.get("command")
            if isinstance(command, str) and hook_ref in command:
                prefix = command.split('"', 1)[0].rstrip()
                value["command"] = (
                    f'{prefix} "${{AIT_WRAPPER_REPO:-${project_var}}}/{hook_ref}"'
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


patch_settings(
    Path(".claude/settings.json"),
    project_var="CLAUDE_PROJECT_DIR",
    hook_ref=".ait/adapters/claude-code/claude_code_hook.py",
)
patch_settings(
    Path(".codex/hooks.json"),
    project_var="CODEX_PROJECT_DIR",
    hook_ref=".ait/adapters/codex/codex_hook.py",
)
PY
export PATH="$DEMO_WORKSPACE/.ait/bin:$PATH"
"$AIT_BIN" adapter doctor claude-code
"$AIT_BIN" adapter doctor codex

git add .
if ! git diff --cached --quiet; then
  git -c user.name=Demo -c user.email=demo@example.com commit -m "initialize ait metadata"
fi

pass "demo workspace ready at $DEMO_WORKSPACE"
