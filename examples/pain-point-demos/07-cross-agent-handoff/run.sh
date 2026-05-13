#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="07-cross-agent-handoff"
use_demo_workspace
run_id="$(date +%Y%m%d%H%M%S)-$$"
proof="AIT_HANDOFF_PROOF=$run_id"
decision="Decision: keep calculator modules as ESM exports. $proof."

info "running Claude Code decision attempt"
AIT_INTENT="Claude: record calculator module decision $run_id" \
AIT_COMMIT_MESSAGE="claude calculator module decision" \
run_claude_code -p --permission-mode bypassPermissions \
  "Create AGENTS.md with this exact line: $decision Do not run git commands."

decision_attempt="$(latest_attempt_id)"
status="$(attempt_verified_status "$decision_attempt")"
if [ "$status" != "promoted" ]; then
  "$AIT_BIN" attempt promote "$decision_attempt" --to main >/dev/null
fi
"$AIT_BIN" memory import --path AGENTS.md --topic agent-memory --format json >/dev/null

info "running Codex handoff proof"
AIT_INTENT="Codex: read calculator module handoff $run_id" \
AIT_COMMIT_MESSAGE="codex handoff proof" \
codex "Read AIT_CONTEXT_FILE. Copy the exact line containing $proof into handoff-proof.txt. Do not inspect AGENTS.md directly."

codex_attempt="$(latest_attempt_id)"
state_set "$demo" "run_id" "$run_id"
state_set "$demo" "proof" "$proof"
state_set "$demo" "decision_attempt_id" "$decision_attempt"
state_set "$demo" "attempt_id" "$codex_attempt"

pass "recorded decision attempt $decision_attempt and Codex handoff attempt $codex_attempt"
