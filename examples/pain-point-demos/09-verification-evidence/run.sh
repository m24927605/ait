#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="09-verification-evidence"
use_demo_workspace

info "running Claude Code change with no test command"
AIT_INTENT="Claude: claim tests pass without test evidence" \
AIT_COMMIT_MESSAGE="claude claimed test success" \
claude -p --permission-mode bypassPermissions \
  "Create src/multiply.js exporting multiply(a, b). Say tests should pass, but do not run npm test or any test command. Do not run git commands."

attempt="$(latest_attempt_id)"
state_set "$demo" "attempt_id" "$attempt"
pass "recorded attempt $attempt"
