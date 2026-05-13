#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="04-memory-reuse"
use_demo_workspace
proof="$(state_get "$demo" "proof")"
claude_attempt="$(state_get "$demo" "claude_attempt_id")"
codex_attempt="$(require_demo_attempt "$demo")"
claude_workspace="$(attempt_workspace "$claude_attempt")"
codex_workspace="$(attempt_workspace "$codex_attempt")"

assert_file_contains "$claude_workspace/notes/auth-retry.md" "$proof"
assert_file_contains "$codex_workspace/context-proof.txt" "$proof"

pass "Codex reused Claude's finding through AIT repo memory"
