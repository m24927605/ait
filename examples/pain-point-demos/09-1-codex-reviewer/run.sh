#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=../lib/demo.sh
. "$DEMO_ROOT/lib/demo.sh"

demo="09-1-codex-reviewer"
use_demo_workspace

info "enabling required review gate for apply"
python3 <<'PY'
from __future__ import annotations

import json
from pathlib import Path

path = Path(".ait/config.json")
data = json.loads(path.read_text(encoding="utf-8"))
review = data.setdefault("review", {})
review["auto_apply_requires_review"] = True
review["allow_override"] = False
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
git add -f .ait/config.json
if ! git diff --cached --quiet; then
  git -c user.name=Demo -c user.email=demo@example.com commit -m "require review before apply"
fi

info "running Claude Code implementation attempt"
AIT_INTENT="Claude: unsafe divide implementation for Codex review" \
AIT_COMMIT_MESSAGE="claude unsafe divide implementation" \
run_claude_code -p --permission-mode bypassPermissions \
  "Create src/divide.js exporting divide(a, b). Implement it as a / b without special zero-division handling. Do not add tests. Do not run npm test or any test command. Do not run git commands."

attempt="$(query_attempt_id 'title~"Claude: unsafe divide implementation for Codex review"')"
state_set "$demo" "attempt_id" "$attempt"

info "running Codex adversarial reviewer through AIT"
"$AIT_BIN" review attempt "$attempt" \
  --mode adversarial \
  --review-adapter "command:$SCRIPT_DIR/codex_reviewer.sh" \
  --review-budget standard \
  --json > "$DEMO_STATE_DIR/$demo/codex-adversarial-review.json"

pass "recorded Claude implementation and Codex adversarial review for attempt $attempt"
