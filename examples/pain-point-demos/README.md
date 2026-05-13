# AIT Pain-Point Demos

This directory contains one demo folder for each pain point on the
`why-ait` page. The demos use Claude Code and Codex directly through AIT's
repo-local wrappers.

## Folder Map

1. `01-blast-radius`
2. `02-provenance`
3. `03-failed-run-isolation`
4. `04-memory-reuse`
5. `05-parallel-agents`
6. `06-explicit-promotion`
7. `07-cross-agent-handoff`
8. `08-local-only-provenance`
9. `09-verification-evidence`
10. `10-prompt-search`

## Shared Setup

Run this once before any demo:

```bash
rm -rf ~/lab/ait-pain-demo
mkdir -p ~/lab/ait-pain-demo
cd ~/lab/ait-pain-demo

git init -b main
mkdir -p src test

cat > package.json <<'JSON'
{"scripts":{"test":"node --test"},"type":"module"}
JSON

cat > src/calculator.js <<'JS'
export function add(a, b) {
  return a + b;
}
JS

cat > test/calculator.test.js <<'JS'
import test from 'node:test';
import assert from 'node:assert/strict';
import { add } from '../src/calculator.js';

test('add', () => {
  assert.equal(add(2, 3), 5);
});
JS

npm test
git add .
git -c user.name=Demo -c user.email=demo@example.com commit -m "seed demo app"

ait init
eval "$(ait init --shell)"

ait adapter doctor claude-code
ait adapter doctor codex

git add .
git -c user.name=Demo -c user.email=demo@example.com commit -m "initialize ait metadata"
```

In every additional terminal:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"
```

Optional helper functions:

```bash
latest_attempt() {
  ait attempt list --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
}

latest_workspace() {
  ait attempt show "$1" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["attempt"]["workspace_ref"])'
}
```

