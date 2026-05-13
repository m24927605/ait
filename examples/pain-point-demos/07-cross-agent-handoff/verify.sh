#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="07-cross-agent-handoff"
use_demo_workspace
proof="$(state_get "$demo" "proof")"
decision_attempt="$(state_get "$demo" "decision_attempt_id")"
codex_attempt="$(require_demo_attempt "$demo")"
codex_workspace="$(attempt_workspace "$codex_attempt")"

[ "$(attempt_verified_status "$decision_attempt")" = "promoted" ] || fail "decision attempt is not promoted"
assert_file_contains "$DEMO_WORKSPACE/AGENTS.md" "$proof"
assert_file_contains "$codex_workspace/handoff-proof.txt" "$proof"

pass "Codex received Claude's promoted decision through AIT context"
