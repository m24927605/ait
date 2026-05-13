#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="01-blast-radius"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
workspace="$(attempt_workspace "$attempt")"

assert_file_exists "$DEMO_WORKSPACE/src/calculator.js"
assert_file_absent "$DEMO_WORKSPACE/docs/claude-risk.md"
assert_file_absent "$DEMO_WORKSPACE/tmp/claude-generated.txt"

assert_file_exists "$workspace/docs/claude-risk.md"
assert_file_exists "$workspace/tmp/claude-generated.txt"
assert_file_absent "$workspace/src/calculator.js"

pass "risky edit stayed in attempt workspace: $workspace"
