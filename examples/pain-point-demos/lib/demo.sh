#!/usr/bin/env bash
set -euo pipefail

DEMO_WORKSPACE="${AIT_PAIN_DEMO_WORKSPACE:-$HOME/lab/ait-pain-demo}"
DEMO_STATE_DIR="${AIT_PAIN_DEMO_STATE_DIR:-$HOME/lab/ait-pain-demo-state}"
AIT_BIN="${AIT_BIN:-ait}"

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

run_claude_code() {
  (
    unset ANTHROPIC_API_KEY
    claude "$@"
  )
}

require_workspace() {
  [ -d "$DEMO_WORKSPACE/.ait" ] || fail "demo workspace not initialized: run examples/pain-point-demos/setup.sh first"
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
