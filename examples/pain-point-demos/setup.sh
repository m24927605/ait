#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/demo.sh
. "$SCRIPT_DIR/lib/demo.sh"

for demo_dir in "$SCRIPT_DIR"/[0-9][0-9]-*; do
  [ -d "$demo_dir" ] || continue
  initialize_demo_workspace "$demo_dir/workspace" "$demo_dir/.state"
done

pass "all demo workspaces are ready under examples/pain-point-demos/*/workspace"
