# 10 - Prompt Search

## Pain

Finding an old prompt through raw shell history is unreliable.

## Demo

Use the attempts created by `04-memory-reuse`, then query by intent text:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

ait query --on attempt 'title~"auth retry"' --format table
```

Query by changed file:

```bash
ait query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
```

## Proof

Recover prompt and transcript references:

```bash
attempt=$(
  ait query --on attempt 'title~"auth retry"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,90p'
```

Expected result: prompt, output, changed files, and commit metadata are in
AIT's attempt records.

