# 08 - Local-Only Provenance

## Pain

Many provenance tools require uploading prompts, diffs, or source to a SaaS.

## Demo

Show where AIT stores state:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

ait status --json |
  python3 -c 'import json,sys; s=json.load(sys.stdin); print(s["daemon"]["socket_path"]); print(s["memory"]["state_path"])'
```

## Proof

```bash
test -S .ait/daemon.sock && echo "daemon uses a local Unix socket"
find .ait -maxdepth 2 -type f | sort | head
```

Expected result: metadata is under `.ait/` next to `.git/`, and the harness
daemon uses a local Unix socket.

