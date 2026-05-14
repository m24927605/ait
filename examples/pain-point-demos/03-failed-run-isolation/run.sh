#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="03-failed-run-isolation"
use_demo_workspace

info "running Codex attempt that intentionally leaves a failing test"
set +e
AIT_INTENT="Codex: intentionally broken test attempt" \
AIT_COMMIT_MESSAGE="codex broken test attempt" \
run_codex_cli "Change test/calculator.test.js so the add test expects 999 instead of 5. Run npm test and stop after the failure; do not fix the test."
rc=$?
set -e

attempt="$(query_attempt_id 'title~"Codex: intentionally broken test attempt"')"
[ -n "$attempt" ] || fail "could not determine latest attempt"
state_set "$demo" "attempt_id" "$attempt"
state_set "$demo" "agent_exit_code" "$rc"

if [ "$rc" -ne 0 ]; then
  info "Codex wrapper returned $rc as expected for a failed attempt"
fi
pass "recorded failed-run attempt $attempt"
