#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="06-explicit-promotion"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
status="$(attempt_verified_status "$attempt")"

[ "$status" = "promoted" ] || fail "expected attempt to be promoted, got $status"
assert_file_exact "$DEMO_WORKSPACE/approach.txt" "A"

pass "main changed only after explicit promotion"
