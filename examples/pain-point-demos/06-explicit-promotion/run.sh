#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="06-explicit-promotion"
use_demo_workspace

if ! state_exists "05-parallel-agents" "claude_attempt_id"; then
  info "05-parallel-agents has not run; running prerequisite"
  "$DEMO_ROOT/05-parallel-agents/run.sh"
  "$DEMO_ROOT/05-parallel-agents/verify.sh"
fi

chosen="$(state_get "05-parallel-agents" "claude_attempt_id")"
status="$(attempt_verified_status "$chosen")"
if [ "$status" != "promoted" ]; then
  info "promoting Claude attempt $chosen to main"
  if ! "$AIT_BIN" attempt promote "$chosen" --to main >/dev/null; then
    info "promotion failed, rerunning 05-parallel-agents from the current main branch"
    "$DEMO_ROOT/05-parallel-agents/run.sh"
    "$DEMO_ROOT/05-parallel-agents/verify.sh"
    chosen="$(state_get "05-parallel-agents" "claude_attempt_id")"
    "$AIT_BIN" attempt promote "$chosen" --to main >/dev/null
  fi
else
  info "attempt $chosen is already promoted"
fi

state_set "$demo" "attempt_id" "$chosen"
pass "chosen attempt is promoted: $chosen"
