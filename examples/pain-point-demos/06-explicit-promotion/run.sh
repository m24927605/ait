#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="06-explicit-promotion"
use_demo_workspace

run_id="$(date +%Y%m%d%H%M%S)-$$"

info "creating two candidate attempts in this demo workspace"
(
  use_demo_workspace
  AIT_INTENT="Claude: explicit promotion candidate A $run_id" \
  AIT_COMMIT_MESSAGE="claude promotion candidate A" \
  run_claude_code -p --permission-mode bypassPermissions \
    "Create approach.txt containing only A. Do not run git commands."
) &
claude_pid=$!

(
  use_demo_workspace
  AIT_INTENT="Codex: explicit promotion candidate B $run_id" \
  AIT_COMMIT_MESSAGE="codex promotion candidate B" \
  run_codex_cli "Create approach.txt containing only B. Do not run git commands."
) &
codex_pid=$!

claude_rc=0
codex_rc=0
wait "$claude_pid" || claude_rc=$?
wait "$codex_pid" || codex_rc=$?
[ "$claude_rc" -eq 0 ] || fail "Claude candidate attempt failed with exit code $claude_rc"
[ "$codex_rc" -eq 0 ] || fail "Codex candidate attempt failed with exit code $codex_rc"

chosen="$(query_attempt_id "title~\"Claude: explicit promotion candidate A $run_id\"")"
[ -n "$chosen" ] || fail "could not find Claude promotion candidate"

info "promoting only Claude attempt $chosen to main"
"$AIT_BIN" attempt promote "$chosen" --to main >/dev/null

state_set "$demo" "attempt_id" "$chosen"
pass "chosen attempt is promoted: $chosen"
