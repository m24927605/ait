#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="10-prompt-search"
use_demo_workspace
attempt="$(require_demo_attempt "$demo")"
raw_prompt_ref="$(attempt_raw_prompt_ref "$attempt")"

query_by_title="$(query_attempt_id 'title~"auth retry"')"
[ -n "$query_by_title" ] || fail "query by title returned no attempt"

assert_file_contains "$DEMO_STATE_DIR/$demo/title-query.txt" "auth retry"
assert_file_contains "$DEMO_STATE_DIR/$demo/file-query.txt" "notes/auth-retry.md"
[ -n "$raw_prompt_ref" ] || fail "attempt has no raw prompt or trace reference"

pass "AIT query recovered old prompt metadata and touched files"
