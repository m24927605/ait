# 04 - Memory Reuse

## Pain

Claude investigates a problem, then Codex starts from scratch and repeats the
same investigation.

## Demo

Have Claude write an investigation note with a proof token:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: investigate auth retry" \
AIT_COMMIT_MESSAGE="claude auth retry investigation" \
claude -p --permission-mode bypassPermissions \
  "Create notes/auth-retry.md with this exact line: AIT_PROOF_AUTH_RETRY=missing_jitter. Do not run git commands."
```

Then have Codex read AIT's context handoff:

```bash
AIT_INTENT="Codex: reuse auth retry investigation AIT_PROOF_AUTH_RETRY" \
AIT_COMMIT_MESSAGE="codex context reuse proof" \
codex "Read the file path from AIT_CONTEXT_FILE. Copy any line mentioning AIT_PROOF_AUTH_RETRY into context-proof.txt. Do not search the repository first."
```

## Proof

```bash
attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
workspace=$(ait attempt show "$attempt" | python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])')
cat "$workspace/context-proof.txt"
```

Expected result: Codex can see the prior Claude investigation through
`AIT_CONTEXT_FILE`.

