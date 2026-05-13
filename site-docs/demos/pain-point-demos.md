---
title: Pain-point demos
description: >-
  Claude Code and Codex demos for each problem on the Why ait page: blast
  radius, provenance, failed-run isolation, memory reuse, parallel agents,
  explicit promotion, hand-off context, local-only metadata, verification, and
  prompt search.
---

# Pain-point demos

The [Why ait](../why-ait.md) page currently lists ten pain points. This page
gives a Claude Code and Codex demo for each one. If your talk only needs eight
points, use sections 1-8.

These examples use the direct CLIs (`claude` and `codex`) after `ait init`
installs repo-local wrappers. In every terminal session used for the demo, run
the shell hook first so `claude` and `codex` resolve through `.ait/bin/`.

The repository also contains an executable suite for these demos under
[`examples/pain-point-demos`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos):
run `./setup.sh`, then run each folder's `./run.sh` and `./verify.sh`.

## Setup once

Create a throwaway Node.js repo:

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
```

Initialize AIT and activate the wrappers:

```bash
ait init
eval "$(ait init --shell)"

ait adapter doctor claude-code
ait adapter doctor codex

git add .
git -c user.name=Demo -c user.email=demo@example.com commit -m "initialize ait metadata"
```

In each additional terminal session:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"
```

Optional helpers:

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

## 1. Blast radius is contained

Ask Claude Code to make a deliberately broad edit:

```bash
AIT_INTENT="Claude: broad risky edit" \
AIT_COMMIT_MESSAGE="claude broad risky edit" \
claude -p --permission-mode bypassPermissions \
  "Create docs/claude-risk.md and tmp/claude-generated.txt, then delete src/calculator.js. Do not run git commands."
```

Prove the root checkout did not take the damage:

```bash
git status --short -- src docs tmp
test -f src/calculator.js && echo "root calculator survived"

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
ait attempt show "$attempt" | python3 -m json.tool | sed -n '/"files": {/,/},/p'
git -C "$workspace" show --name-status --oneline HEAD -- src docs tmp
```

Expected result: root `src/calculator.js` still exists. The risky files live
inside the attempt workspace until you promote or discard that attempt.

## 2. The diff has provenance

Inspect the Claude attempt:

```bash
attempt=$(latest_attempt)
ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,110p'
```

Proof points to show on screen:

- `intent_id`
- `agent_id: claude-code:manual`
- `workspace_ref`
- `raw_prompt_ref`
- `raw_trace_ref`
- `files.changed`
- `commits`

The diff is not just a patch. It is connected to the prompt, CLI, exit code,
files, and commit metadata.

## 3. Failed or partial runs stay isolated

Ask Codex to make a broken change and stop after the failing test:

```bash
AIT_INTENT="Codex: intentionally broken test attempt" \
AIT_COMMIT_MESSAGE="codex broken test attempt" \
codex "Change test/calculator.test.js so the add test expects 999 instead of 5. Run npm test and stop after the failure; do not fix the test."
```

Then inspect:

```bash
ait attempt list --limit 1

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
git -C "$workspace" status --short
npm test --prefix "$workspace" || true

git status --short -- test/calculator.test.js
```

Expected result: the broken test is inspectable in the attempt workspace. The
root checkout is still clean unless you explicitly apply or promote.

## 4. Prior investigation is reused

Have Claude record an investigation result with a unique proof token:

```bash
AIT_INTENT="Claude: investigate auth retry" \
AIT_COMMIT_MESSAGE="claude auth retry investigation" \
claude -p --permission-mode bypassPermissions \
  "Create notes/auth-retry.md with this exact line: AIT_PROOF_AUTH_RETRY=missing_jitter. Do not run git commands."
```

Have Codex read AIT's context handoff and copy the relevant line:

```bash
AIT_INTENT="Codex: reuse auth retry investigation AIT_PROOF_AUTH_RETRY" \
AIT_COMMIT_MESSAGE="codex context reuse proof" \
codex "Read the file path from AIT_CONTEXT_FILE. Copy any line mentioning AIT_PROOF_AUTH_RETRY into context-proof.txt. Do not search the repository first."

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
cat "$workspace/context-proof.txt"
```

Expected result: Codex can see the prior Claude attempt through AIT context
instead of rediscovering the same fact from scratch.

## 5. Parallel agents do not stomp each other

Open two terminal sessions in the same repo. In session A:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: parallel approach A" \
AIT_COMMIT_MESSAGE="claude approach A" \
claude -p --permission-mode bypassPermissions \
  "Create approach.txt containing only A. Do not run git commands."
```

In session B at the same time:

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Codex: parallel approach B" \
AIT_COMMIT_MESSAGE="codex approach B" \
codex "Create approach.txt containing only B. Do not run git commands."
```

Compare attempts:

```bash
ait attempt list --limit 6
git status --short -- approach.txt
```

Expected result: both agents can write `approach.txt` because each attempt has
its own worktree. The root checkout still has no `approach.txt`.

## 6. Promotion is explicit

Promote the Claude approach only:

```bash
chosen=$(
  ait query --on attempt 'title~"parallel approach A"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt promote "$chosen" --to main
cat approach.txt
git log --oneline -1
```

Before `promote`, the agent result was a proposal. After `promote`, it becomes
part of `main`.

## 7. Cross-agent hand-off keeps context

Have Claude write a project decision and promote it:

```bash
AIT_INTENT="Claude: record calculator module decision" \
AIT_COMMIT_MESSAGE="claude calculator module decision" \
claude -p --permission-mode bypassPermissions \
  "Create AGENTS.md with this exact line: Decision: keep calculator modules as ESM exports. Do not run git commands."

decision_attempt=$(latest_attempt)
ait attempt promote "$decision_attempt" --to main
```

Then have Codex prove the handoff:

```bash
AIT_INTENT="Codex: read calculator module handoff" \
AIT_COMMIT_MESSAGE="codex handoff proof" \
codex "Read AIT_CONTEXT_FILE and copy the line mentioning calculator modules as ESM exports into handoff-proof.txt."

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
cat "$workspace/handoff-proof.txt"
```

Expected result: Codex receives the context created by the previous Claude
work, even though it is a different agent.

## 8. Provenance stays local

Show where AIT stores metadata and how the daemon communicates:

```bash
ait status --json |
  python3 -c 'import json,sys; s=json.load(sys.stdin); print(s["daemon"]["socket_path"]); print(s["memory"]["state_path"])'

test -S .ait/daemon.sock && echo "daemon uses a local Unix socket"
find .ait -maxdepth 2 -type f | sort | head
```

The proof is not a remote dashboard. The state is under `.ait/` beside
`.git/`, and the daemon socket is local to the repo.

## 9. Self-reported success is checked

Ask Claude to claim success without running tests:

```bash
AIT_INTENT="Claude: claim tests pass without test evidence" \
AIT_COMMIT_MESSAGE="claude claimed test success" \
claude -p --permission-mode bypassPermissions \
  "Create CLAIM.md containing 'all tests pass'. Do not run npm test or any test command. Do not run git commands."
```

Inspect AIT evidence and run the deterministic review scan:

```bash
attempt=$(latest_attempt)
ait attempt show "$attempt" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["attempt"]["verified_status"]); print(d["evidence_summary"]["observed_tests_run"])'

ait review attempt "$attempt" --mode light
```

Expected result: AIT records the attempt outcome and evidence separately. The
agent can write "all tests pass", but AIT does not invent observed test
evidence; `light` review can flag missing test evidence.

## 10. Old prompts are queryable

Find attempts by intent text:

```bash
ait query --on attempt 'title~"auth retry"' --format table
```

Find attempts by changed file:

```bash
ait query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
```

Recover prompt and transcript references:

```bash
attempt=$(
  ait query --on attempt 'title~"auth retry"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,80p'
```

You do not need shell history. The prompt, output, changed files, and commit
metadata are in AIT's attempt records.
