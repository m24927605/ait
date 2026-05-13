# 06 - Explicit Promotion

## Pain

An agent says it is done, but accepting the result should be a separate human
decision.

## Demo

Use the two attempts from `05-parallel-agents`, then promote only Claude's
approach:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

chosen=$(
  ait query --on attempt 'title~"parallel approach A"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt promote "$chosen" --to main
```

## Proof

```bash
cat approach.txt
git log --oneline -1
ait attempt list --limit 6
```

Expected result: before promotion, the result was a proposal. After promotion,
`approach.txt` appears in `main`.

