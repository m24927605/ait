# 02 - Provenance

## Pain

Three days later, a plain diff does not tell you which prompt produced it,
which agent ran, what exited, or where the captured transcript is.

## Demo

Use the attempt created in `01-blast-radius`, or create a fresh Claude attempt:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: provenance proof" \
AIT_COMMIT_MESSAGE="claude provenance proof" \
claude -p --permission-mode bypassPermissions \
  "Create docs/provenance-proof.md explaining that this file exists to prove AIT provenance. Do not run git commands."
```

## Proof

```bash
attempt=$(ait attempt list --format jsonl --limit 1 | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,120p'
```

Show these fields:

- `intent_id`
- `agent_id`
- `workspace_ref`
- `raw_prompt_ref`
- `raw_trace_ref`
- `files.changed`
- `commits`

Expected result: the diff is tied to prompt, agent, exit status, files, and
commit metadata.

