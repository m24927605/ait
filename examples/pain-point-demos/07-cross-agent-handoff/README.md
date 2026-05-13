# 07 - Cross-Agent Handoff

## Pain

Claude makes a decision, then Codex takes over without seeing that context.

## Demo

Have Claude record a decision and promote it:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: record calculator module decision" \
AIT_COMMIT_MESSAGE="claude calculator module decision" \
claude -p --permission-mode bypassPermissions \
  "Create AGENTS.md with this exact line: Decision: keep calculator modules as ESM exports. Do not run git commands."

decision_attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
ait attempt promote "$decision_attempt" --to main
```

Then have Codex prove the handoff:

```bash
AIT_INTENT="Codex: read calculator module handoff" \
AIT_COMMIT_MESSAGE="codex handoff proof" \
codex "Read AIT_CONTEXT_FILE and copy the line mentioning calculator modules as ESM exports into handoff-proof.txt."
```

## Proof

```bash
attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
workspace=$(ait attempt show "$attempt" | python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])')
cat "$workspace/handoff-proof.txt"
```

Expected result: Codex receives context created by Claude through AIT's
repo-local handoff.

