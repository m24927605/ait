# 09 - Verification Evidence

## Pain

An agent can write "all tests pass" without actually running tests.

## Demo

Ask Claude to claim success but not run tests:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: claim tests pass without test evidence" \
AIT_COMMIT_MESSAGE="claude claimed test success" \
claude -p --permission-mode bypassPermissions \
  "Create CLAIM.md containing 'all tests pass'. Do not run npm test or any test command. Do not run git commands."
```

## Proof

```bash
attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')

ait attempt show "$attempt" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["attempt"]["verified_status"]); print(d["evidence_summary"]["observed_tests_run"])'

ait review attempt "$attempt" --mode light
```

Expected result: AIT records outcome and evidence separately. The agent can
claim tests passed, but AIT does not invent observed test evidence.

