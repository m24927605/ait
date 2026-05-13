# 01 - Blast Radius

## Pain

A single Claude Code or Codex prompt can rewrite many files or delete files you
still need.

## Demo

Ask Claude Code to make a deliberately risky edit:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: broad risky edit" \
AIT_COMMIT_MESSAGE="claude broad risky edit" \
claude -p --permission-mode bypassPermissions \
  "Create docs/claude-risk.md and tmp/claude-generated.txt, then delete src/calculator.js. Do not run git commands."
```

## Proof

```bash
git status --short -- src docs tmp
test -f src/calculator.js && echo "root calculator survived"

attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
workspace=$(ait attempt show "$attempt" | python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])')
ait attempt show "$attempt" | python3 -m json.tool | sed -n '/"files": {/,/},/p'
git -C "$workspace" show --name-status --oneline HEAD -- src docs tmp
```

Expected result: the root checkout still has `src/calculator.js`; the risky
change is isolated in the attempt workspace.

