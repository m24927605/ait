#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="09-verification-evidence"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
workspace="$(attempt_workspace "$attempt")"
tests_run="$(attempt_observed_tests_run "$attempt")"
review_json="$DEMO_STATE_DIR/$demo/light-review.json"
adversarial_json="$DEMO_STATE_DIR/$demo/adversarial-review.json"
mkdir -p "$(dirname "$review_json")"

assert_file_exists "$workspace/src/multiply.js"
[ "$tests_run" = "0" ] || fail "expected zero observed tests, got $tests_run"

"$AIT_BIN" review attempt "$attempt" --mode light --json > "$review_json"
assert_file_contains "$review_json" "test"
assert_file_contains "$adversarial_json" "\"mode\": \"adversarial\""
assert_file_contains "$adversarial_json" "\"status\": \"blocked\""
assert_file_contains "$adversarial_json" "\"blocking\": true"
"$AIT_BIN" review finding list --severity high --format text | grep -Fq "Potential regression" ||
  fail "expected high severity adversarial finding"

pass "AIT captured blocking adversarial review finding"
