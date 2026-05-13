#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="08-local-only-provenance"
use_demo_workspace
mkdir -p "$DEMO_STATE_DIR/$demo"

info "capturing repo-local AIT status"
"$AIT_BIN" status --all --json > "$DEMO_STATE_DIR/$demo/status.json"
find "$DEMO_WORKSPACE/.ait" -maxdepth 2 -type f | sort > "$DEMO_STATE_DIR/$demo/ait-files.txt"

state_set "$demo" "attempt_id" "local-only"
pass "captured local metadata inventory"
