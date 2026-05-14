#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="09-1-codex-reviewer"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
workspace="$(attempt_workspace "$attempt")"
review_json="$DEMO_STATE_DIR/$demo/codex-adversarial-review.json"

assert_file_exists "$workspace/src/divide.js"
assert_file_contains "$review_json" "\"mode\": \"adversarial\""
assert_file_contains "$review_json" "\"reviewer_adapter\""
assert_file_contains "$review_json" "codex_reviewer.sh"
assert_file_contains "$review_json" "\"status\": \"blocked\""
assert_file_contains "$review_json" "\"blocking\": true"
"$AIT_BIN" review finding list --severity high --format text | grep -Fq "divide" ||
  fail "expected high severity Codex finding for divide"

if "$AIT_BIN" apply "$attempt" --mode current --json > "$DEMO_STATE_DIR/$demo/apply-blocked.json"; then
  fail "expected apply to be held by the review gate"
fi
assert_file_contains "$DEMO_STATE_DIR/$demo/apply-blocked.json" "\"status\": \"held\""
assert_file_contains "$DEMO_STATE_DIR/$demo/apply-blocked.json" "review gate"

pass "Codex adversarial reviewer blocked the Claude implementation"
