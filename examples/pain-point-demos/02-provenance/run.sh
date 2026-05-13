#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="02-provenance"
use_demo_workspace

info "running Claude Code provenance proof"
AIT_INTENT="Claude: provenance proof" \
AIT_COMMIT_MESSAGE="claude provenance proof" \
claude -p --permission-mode bypassPermissions \
  "Create notes/provenance-proof.md with this exact line: AIT_PROVENANCE_PROOF=claude_prompt_recorded. Do not run git commands."

attempt="$(latest_attempt_id)"
[ -n "$attempt" ] || fail "could not determine latest attempt"
state_set "$demo" "attempt_id" "$attempt"
pass "recorded attempt $attempt"
