#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="04-memory-reuse"
use_demo_workspace

run_id="$(date +%Y%m%d%H%M%S)-$$"
proof="AIT_PROOF_AUTH_RETRY=$run_id-missing_jitter"

info "running Claude Code investigation"
AIT_INTENT="Claude: investigate auth retry $run_id" \
AIT_COMMIT_MESSAGE="claude auth retry investigation" \
run_claude_code -p --permission-mode bypassPermissions \
  "Create notes/auth-retry.md with this exact line: Decision: auth retry backoff uses missing jitter. $proof. Do not run git commands."

claude_attempt="$(query_attempt_id "title~\"Claude: investigate auth retry $run_id\"")"
claude_workspace="$(attempt_workspace "$claude_attempt")"
assert_file_contains "$claude_workspace/notes/auth-retry.md" "$proof"

note_body="$(sed -n '1p' "$claude_workspace/notes/auth-retry.md")"
"$AIT_BIN" memory note add "$note_body" --topic auth-retry --source manual:demo --format json >/dev/null

info "running Codex with AIT_CONTEXT_FILE memory handoff"
AIT_INTENT="Codex: reuse auth retry investigation $run_id" \
AIT_COMMIT_MESSAGE="codex context reuse proof" \
run_codex_cli "Read AIT_CONTEXT_FILE. Copy the exact line containing $proof into context-proof.txt. Do not inspect notes/auth-retry.md directly."

codex_attempt="$(query_attempt_id "title~\"Codex: reuse auth retry investigation $run_id\"")"
state_set "$demo" "run_id" "$run_id"
state_set "$demo" "proof" "$proof"
state_set "$demo" "claude_attempt_id" "$claude_attempt"
state_set "$demo" "attempt_id" "$codex_attempt"

pass "recorded Claude attempt $claude_attempt and Codex attempt $codex_attempt"
