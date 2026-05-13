#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="02-provenance"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
workspace="$(attempt_workspace "$attempt")"
raw_prompt_ref="$(attempt_raw_prompt_ref "$attempt")"

assert_file_contains "$workspace/notes/provenance-proof.md" "AIT_PROVENANCE_PROOF=claude_prompt_recorded"
[ -n "$raw_prompt_ref" ] || fail "attempt has no raw prompt or trace reference"

row_attempt="$(query_attempt_id 'title~"Claude: provenance proof"')"
[ "$row_attempt" = "$attempt" ] || fail "query by intent did not recover attempt $attempt"

pass "attempt records changed file, intent, and prompt/trace reference"
