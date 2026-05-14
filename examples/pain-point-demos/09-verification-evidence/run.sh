#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="09-verification-evidence"
use_demo_workspace

info "running Claude Code change that leaves reviewable risk"
AIT_INTENT="Claude: risky multiply change without test evidence" \
AIT_COMMIT_MESSAGE="claude risky multiply without tests" \
run_claude_code -p --permission-mode bypassPermissions \
  "Create src/multiply.js exporting multiply(a, b). Do not add tests. Do not run npm test or any test command. Do not run git commands."

attempt="$(query_attempt_id 'title~"Claude: risky multiply change without test evidence"')"
state_set "$demo" "attempt_id" "$attempt"

info "running adversarial AIT review"
"$AIT_BIN" review attempt "$attempt" \
  --mode adversarial \
  --review-adapter fake:high \
  --review-budget standard \
  --json > "$DEMO_STATE_DIR/$demo/adversarial-review.json"

pass "recorded adversarially reviewed attempt $attempt"
