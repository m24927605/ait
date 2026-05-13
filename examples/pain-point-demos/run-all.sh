#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/setup.sh"

for demo in \
  01-blast-radius \
  02-provenance \
  03-failed-run-isolation \
  04-memory-reuse \
  05-parallel-agents \
  06-explicit-promotion \
  07-cross-agent-handoff \
  08-local-only-provenance \
  09-verification-evidence \
  10-prompt-search
do
  printf '\n==> running %s\n' "$demo"
  "$SCRIPT_DIR/$demo/run.sh"
  "$SCRIPT_DIR/$demo/verify.sh"
done

printf '\nPASS all pain-point demos completed\n'
