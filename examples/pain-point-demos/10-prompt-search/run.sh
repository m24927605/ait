#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="10-prompt-search"
use_demo_workspace

if ! state_exists "04-memory-reuse" "claude_attempt_id"; then
  info "04-memory-reuse has not run; running prerequisite"
  "$DEMO_ROOT/04-memory-reuse/run.sh"
  "$DEMO_ROOT/04-memory-reuse/verify.sh"
fi

auth_attempt="$(state_get "04-memory-reuse" "claude_attempt_id")"
mkdir -p "$DEMO_STATE_DIR/$demo"
"$AIT_BIN" query --on attempt 'title~"auth retry"' --format table > "$DEMO_STATE_DIR/$demo/title-query.txt"
"$AIT_BIN" query --on attempt 'files_changed~"notes/auth-retry.md"' --format table > "$DEMO_STATE_DIR/$demo/file-query.txt"

state_set "$demo" "attempt_id" "$auth_attempt"
pass "captured prompt search output for attempt $auth_attempt"
