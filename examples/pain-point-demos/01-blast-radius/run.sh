#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="01-blast-radius"
use_demo_workspace

info "running Claude Code risky broad edit in an isolated attempt"
AIT_INTENT="Claude: broad risky edit" \
AIT_COMMIT_MESSAGE="claude broad risky edit" \
claude -p --permission-mode bypassPermissions \
  "Create docs/claude-risk.md and tmp/claude-generated.txt, then delete src/calculator.js. Do not run git commands."

attempt="$(latest_attempt_id)"
[ -n "$attempt" ] || fail "could not determine latest attempt"
state_set "$demo" "attempt_id" "$attempt"
pass "recorded attempt $attempt"
