# 03 - Failed-Run Isolation

## Pain

An agent can leave partial edits or failing tests in the working copy.

## Demo

Ask Codex to create a failing test and stop:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Codex: intentionally broken test attempt" \
AIT_COMMIT_MESSAGE="codex broken test attempt" \
codex "Change test/calculator.test.js so the add test expects 999 instead of 5. Run npm test and stop after the failure; do not fix the test."
```

## Proof

```bash
ait attempt list --limit 1

attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
workspace=$(ait attempt show "$attempt" | python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])')
npm test --prefix "$workspace" || true

git status --short -- test/calculator.test.js
```

Expected result: the broken test is inspectable in the attempt workspace; the
root checkout remains clean until you apply or promote.

