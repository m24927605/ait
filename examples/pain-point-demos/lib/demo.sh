#!/usr/bin/env bash
set -euo pipefail

AIT_BIN="${AIT_BIN:-ait}"
DEMO_ROOT="${DEMO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [ -z "${DEMO_WORKSPACE:-}" ]; then
  if [ -n "${AIT_PAIN_DEMO_WORKSPACE:-}" ]; then
    DEMO_WORKSPACE="$AIT_PAIN_DEMO_WORKSPACE"
  elif [ -n "${SCRIPT_DIR:-}" ] && [[ "$(basename "$SCRIPT_DIR")" =~ ^[0-9][0-9]- ]]; then
    DEMO_WORKSPACE="$SCRIPT_DIR/workspace"
  else
    DEMO_WORKSPACE="$DEMO_ROOT/workspace"
  fi
fi

if [ -z "${DEMO_STATE_DIR:-}" ]; then
  if [ -n "${AIT_PAIN_DEMO_STATE_DIR:-}" ]; then
    DEMO_STATE_DIR="$AIT_PAIN_DEMO_STATE_DIR"
  elif [ -n "${SCRIPT_DIR:-}" ] && [[ "$(basename "$SCRIPT_DIR")" =~ ^[0-9][0-9]- ]]; then
    DEMO_STATE_DIR="$SCRIPT_DIR/.state"
  else
    DEMO_STATE_DIR="$DEMO_ROOT/.state"
  fi
fi

info() {
  printf '==> %s\n' "$*"
}

pass() {
  printf 'PASS %s\n' "$*"
}

fail() {
  printf 'FAIL %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

initialize_demo_workspace() {
  local workspace="${1:-$DEMO_WORKSPACE}"
  local state_dir="${2:-$DEMO_STATE_DIR}"

  require_command git
  require_command node
  require_command npm
  require_command python3
  require_command "$AIT_BIN"

  info "resetting demo workspace: $workspace"
  rm -rf "$workspace" "$state_dir"
  mkdir -p "$workspace"
  cd "$workspace"

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
  # binary when this setup function is run from an already AIT-enabled shell.
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
  export PATH="$workspace/.ait/bin:$PATH"
  "$AIT_BIN" adapter doctor claude-code
  "$AIT_BIN" adapter doctor codex

  git add .
  if ! git diff --cached --quiet; then
    git -c user.name=Demo -c user.email=demo@example.com commit -m "initialize ait metadata"
  fi

  pass "demo workspace ready at $workspace"
}

run_claude_code() {
  (
    unset ANTHROPIC_API_KEY
    claude "$@"
  )
}

run_codex_cli() {
  codex exec --dangerously-bypass-approvals-and-sandbox "$@"
}

require_workspace() {
  if [ ! -d "$DEMO_WORKSPACE/.ait" ]; then
    initialize_demo_workspace "$DEMO_WORKSPACE" "$DEMO_STATE_DIR"
  fi
  [ -f "$DEMO_WORKSPACE/package.json" ] || fail "demo workspace is missing package.json: $DEMO_WORKSPACE"
}

use_demo_workspace() {
  require_workspace
  cd "$DEMO_WORKSPACE"
  export PATH="$DEMO_WORKSPACE/.ait/bin:$PATH"
}

state_path() {
  local demo="$1"
  local key="$2"
  printf '%s/%s/%s\n' "$DEMO_STATE_DIR" "$demo" "$key"
}

state_set() {
  local demo="$1"
  local key="$2"
  local value="$3"
  local path
  path="$(state_path "$demo" "$key")"
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$value" > "$path"
}

state_get() {
  local demo="$1"
  local key="$2"
  local path
  path="$(state_path "$demo" "$key")"
  [ -f "$path" ] || fail "missing demo state: $path"
  sed -n '1p' "$path"
}

state_exists() {
  local demo="$1"
  local key="$2"
  [ -f "$(state_path "$demo" "$key")" ]
}

latest_attempt_id() {
  "$AIT_BIN" attempt list --format jsonl --limit 1 |
    python3 -c 'import json,sys; line=sys.stdin.readline().strip(); print(json.loads(line)["id"] if line else "")'
}

query_attempt_id() {
  local expression="$1"
  "$AIT_BIN" query --on attempt "$expression" --format jsonl --limit 1 |
    python3 -c 'import json,sys; line=sys.stdin.readline().strip(); print(json.loads(line)["id"] if line else "")'
}

attempt_workspace() {
  local attempt="$1"
  "$AIT_BIN" attempt show "$attempt" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])'
}

attempt_verified_status() {
  local attempt="$1"
  "$AIT_BIN" attempt show "$attempt" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["verified_status"])'
}

attempt_raw_prompt_ref() {
  local attempt="$1"
  "$AIT_BIN" attempt show "$attempt" |
    python3 -c 'import json,sys; data=json.load(sys.stdin); e=data.get("evidence_summary") or {}; print(e.get("raw_prompt_ref") or data["attempt"].get("raw_trace_ref") or "")'
}

attempt_observed_tests_run() {
  local attempt="$1"
  "$AIT_BIN" attempt show "$attempt" |
    python3 -c 'import json,sys; data=json.load(sys.stdin); e=data.get("evidence_summary") or {}; print(e.get("observed_tests_run", 0))'
}

assert_file_exists() {
  local path="$1"
  [ -f "$path" ] || fail "expected file does not exist: $path"
}

assert_file_absent() {
  local path="$1"
  [ ! -e "$path" ] || fail "expected path to be absent: $path"
}

assert_file_contains() {
  local path="$1"
  local needle="$2"
  assert_file_exists "$path"
  grep -Fq "$needle" "$path" || fail "expected $path to contain: $needle"
}

assert_file_not_contains() {
  local path="$1"
  local needle="$2"
  assert_file_exists "$path"
  if grep -Fq "$needle" "$path"; then
    fail "expected $path not to contain: $needle"
  fi
}

assert_file_exact() {
  local path="$1"
  local expected="$2"
  assert_file_exists "$path"
  local actual
  actual="$(tr -d '\r\n' < "$path")"
  [ "$actual" = "$expected" ] || fail "expected $path to equal '$expected', got '$actual'"
}

require_demo_attempt() {
  local demo="$1"
  state_get "$demo" "attempt_id"
}
