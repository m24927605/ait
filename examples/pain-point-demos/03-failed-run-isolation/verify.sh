#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="03-failed-run-isolation"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
workspace="$(attempt_workspace "$attempt")"

assert_file_contains "$workspace/test/calculator.test.js" "999"
assert_file_not_contains "$DEMO_WORKSPACE/test/calculator.test.js" "999"
assert_file_contains "$DEMO_WORKSPACE/test/calculator.test.js" "5"

set +e
npm test --prefix "$workspace" >/tmp/ait-pain-demo-03-npm-test.log 2>&1
test_rc=$?
set -e
[ "$test_rc" -ne 0 ] || fail "expected npm test to fail in attempt workspace"

pass "failed test stayed isolated from main workspace"
