#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="05-parallel-agents"
use_demo_workspace
run_id="$(date +%Y%m%d%H%M%S)-$$"

info "starting Claude Code and Codex in parallel attempts"
(
  use_demo_workspace
  AIT_INTENT="Claude: parallel approach A $run_id" \
  AIT_COMMIT_MESSAGE="claude approach A" \
  claude -p --permission-mode bypassPermissions \
    "Create approach.txt containing only A. Do not run git commands."
) &
claude_pid=$!

(
  use_demo_workspace
  AIT_INTENT="Codex: parallel approach B $run_id" \
  AIT_COMMIT_MESSAGE="codex approach B" \
  codex "Create approach.txt containing only B. Do not run git commands."
) &
codex_pid=$!

claude_rc=0
codex_rc=0
wait "$claude_pid" || claude_rc=$?
wait "$codex_pid" || codex_rc=$?
[ "$claude_rc" -eq 0 ] || fail "Claude parallel attempt failed with exit code $claude_rc"
[ "$codex_rc" -eq 0 ] || fail "Codex parallel attempt failed with exit code $codex_rc"

claude_attempt="$(query_attempt_id "title~\"Claude: parallel approach A $run_id\"")"
codex_attempt="$(query_attempt_id "title~\"Codex: parallel approach B $run_id\"")"
[ -n "$claude_attempt" ] || fail "could not find Claude parallel attempt"
[ -n "$codex_attempt" ] || fail "could not find Codex parallel attempt"

state_set "$demo" "run_id" "$run_id"
state_set "$demo" "claude_attempt_id" "$claude_attempt"
state_set "$demo" "codex_attempt_id" "$codex_attempt"
state_set "$demo" "attempt_id" "$claude_attempt"

pass "recorded parallel attempts: $claude_attempt and $codex_attempt"
