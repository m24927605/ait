#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="10-prompt-search"
use_demo_workspace

run_id="$(date +%Y%m%d%H%M%S)-$$"
proof="AIT_PROMPT_SEARCH_PROOF=$run_id"

info "creating searchable Claude Code auth retry attempt in this demo workspace"
AIT_INTENT="Claude: searchable auth retry prompt $run_id" \
AIT_COMMIT_MESSAGE="claude searchable auth retry prompt" \
run_claude_code -p --permission-mode bypassPermissions \
  "Create notes/auth-retry.md with this exact line: Decision: auth retry prompt search proof. $proof. Do not run git commands."

auth_attempt="$(query_attempt_id "title~\"Claude: searchable auth retry prompt $run_id\"")"
[ -n "$auth_attempt" ] || fail "could not find searchable auth retry attempt"
mkdir -p "$DEMO_STATE_DIR/$demo"
"$AIT_BIN" query --on attempt 'title~"auth retry"' --format table > "$DEMO_STATE_DIR/$demo/title-query.txt"
{
  "$AIT_BIN" query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
  "$AIT_BIN" attempt show "$auth_attempt"
} > "$DEMO_STATE_DIR/$demo/file-query.txt"

state_set "$demo" "attempt_id" "$auth_attempt"
pass "captured prompt search output for attempt $auth_attempt"
