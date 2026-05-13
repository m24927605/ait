#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="05-parallel-agents"
use_demo_workspace
claude_attempt="$(state_get "$demo" "claude_attempt_id")"
codex_attempt="$(state_get "$demo" "codex_attempt_id")"
claude_workspace="$(attempt_workspace "$claude_attempt")"
codex_workspace="$(attempt_workspace "$codex_attempt")"

assert_file_exact "$claude_workspace/approach.txt" "A"
assert_file_exact "$codex_workspace/approach.txt" "B"

if [ -e "$DEMO_WORKSPACE/approach.txt" ]; then
  info "main already has approach.txt, likely because 06-explicit-promotion ran"
else
  pass "parallel attempts did not write into main"
fi

pass "Claude and Codex outputs are isolated in separate worktrees"
