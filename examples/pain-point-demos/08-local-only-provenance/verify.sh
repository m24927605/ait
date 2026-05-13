#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="08-local-only-provenance"
use_demo_workspace
status_json="$DEMO_STATE_DIR/$demo/status.json"
ait_files="$DEMO_STATE_DIR/$demo/ait-files.txt"

assert_file_exists "$DEMO_WORKSPACE/.ait/state.sqlite3"
assert_file_contains "$status_json" "\"adapter\""
assert_file_contains "$status_json" "\"ait_health\""
assert_file_contains "$ait_files" ".ait/state.sqlite3"

pass "AIT provenance and status are stored in repo-local files"
