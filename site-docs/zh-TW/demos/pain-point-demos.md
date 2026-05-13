---
title: 痛點 demo
description: >-
  直接用 Claude Code 與 Codex 示範 Why ait 頁面的每個痛點：blast radius、
  provenance、failed-run isolation、memory reuse、parallel agents、
  explicit promotion、hand-off context、local-only metadata、verification、
  prompt search。
---

# 痛點 demo

[為什麼用 ait](../why-ait.md) 頁面目前列了 10 個痛點。這頁直接用 Claude
Code 與 Codex 示範每一點。如果你的 talk 只需要 8 點，就用第 1-8 節。

這些範例是在 `ait init` 安裝 repo-local wrapper 後，直接執行 `claude` 與
`codex`。每個 demo terminal 都要先載入 shell hook，讓 `claude` / `codex`
走 `.ait/bin/` wrapper。

Repo 內也有同一套 demo，已拆成每個痛點一個資料夾：
[`examples/pain-point-demos`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos)。

## 一次性 setup

建立 throwaway Node.js repo：

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

初始化 AIT 並啟用 wrappers：

```bash
ait init
eval "$(ait init --shell)"

ait adapter doctor claude-code
ait adapter doctor codex

git add .
git -c user.name=Demo -c user.email=demo@example.com commit -m "initialize ait metadata"
```

每個額外 terminal session 都先跑：

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"
```

可選 helper：

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

## 1. Blast radius 被限制住

請 Claude Code 做一個故意很大的危險修改：

```bash
AIT_INTENT="Claude: broad risky edit" \
AIT_COMMIT_MESSAGE="claude broad risky edit" \
claude -p --permission-mode bypassPermissions \
  "Create docs/claude-risk.md and tmp/claude-generated.txt, then delete src/calculator.js. Do not run git commands."
```

證明 root checkout 沒被炸到：

```bash
git status --short -- src docs tmp
test -f src/calculator.js && echo "root calculator survived"

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
ait attempt show "$attempt" | python3 -m json.tool | sed -n '/"files": {/,/},/p'
git -C "$workspace" show --name-status --oneline HEAD -- src docs tmp
```

預期結果：root 的 `src/calculator.js` 還在。危險變更只存在 attempt
workspace，直到你 promote 或 discard。

## 2. Diff 有 provenance

檢查 Claude attempt：

```bash
attempt=$(latest_attempt)
ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,110p'
```

畫面上展示這些 proof points：

- `intent_id`
- `agent_id: claude-code:manual`
- `workspace_ref`
- `raw_prompt_ref`
- `raw_trace_ref`
- `files.changed`
- `commits`

這個 diff 不是孤立 patch。它連著 prompt、CLI、exit code、檔案與 commit
metadata。

## 3. 失敗或半成品留在隔離 worktree

請 Codex 做一個壞掉的測試，測試失敗後停下：

```bash
AIT_INTENT="Codex: intentionally broken test attempt" \
AIT_COMMIT_MESSAGE="codex broken test attempt" \
codex "Change test/calculator.test.js so the add test expects 999 instead of 5. Run npm test and stop after the failure; do not fix the test."
```

檢查結果：

```bash
ait attempt list --limit 1

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
git -C "$workspace" status --short
npm test --prefix "$workspace" || true

git status --short -- test/calculator.test.js
```

預期結果：壞掉的測試可在 attempt workspace 檢查。Root checkout 仍乾淨，
除非你明確 apply 或 promote。

## 4. 之前的調查可以重用

先讓 Claude 記下一個帶 proof token 的調查結果：

```bash
AIT_INTENT="Claude: investigate auth retry" \
AIT_COMMIT_MESSAGE="claude auth retry investigation" \
claude -p --permission-mode bypassPermissions \
  "Create notes/auth-retry.md with this exact line: AIT_PROOF_AUTH_RETRY=missing_jitter. Do not run git commands."
```

再讓 Codex 讀 AIT context handoff，複製相關行：

```bash
AIT_INTENT="Codex: reuse auth retry investigation AIT_PROOF_AUTH_RETRY" \
AIT_COMMIT_MESSAGE="codex context reuse proof" \
codex "Read the file path from AIT_CONTEXT_FILE. Copy any line mentioning AIT_PROOF_AUTH_RETRY into context-proof.txt. Do not search the repository first."

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
cat "$workspace/context-proof.txt"
```

預期結果：Codex 可以透過 AIT context 看到前一個 Claude attempt 的調查，
不需要從零再查一次。

## 5. 平行 agents 不互相覆蓋

開兩個 terminal session，都在同一個 repo。Session A：

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Claude: parallel approach A" \
AIT_COMMIT_MESSAGE="claude approach A" \
claude -p --permission-mode bypassPermissions \
  "Create approach.txt containing only A. Do not run git commands."
```

Session B 同時跑：

```bash
cd ~/lab/ait-pain-demo
eval "$(ait init --shell)"

AIT_INTENT="Codex: parallel approach B" \
AIT_COMMIT_MESSAGE="codex approach B" \
codex "Create approach.txt containing only B. Do not run git commands."
```

比較 attempts：

```bash
ait attempt list --limit 6
git status --short -- approach.txt
```

預期結果：兩個 agents 都能寫 `approach.txt`，因為每個 attempt 都有自己的
worktree。Root checkout 在你 promote 前仍沒有 `approach.txt`。

## 6. Promote 是顯式動作

只 promote Claude 的 approach：

```bash
chosen=$(
  ait query --on attempt 'title~"parallel approach A"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt promote "$chosen" --to main
cat approach.txt
git log --oneline -1
```

在 `promote` 之前，agent 結果只是提案；`promote` 之後才進入 `main`。

## 7. 跨 agent hand-off 保留脈絡

讓 Claude 寫下專案決策並 promote：

```bash
AIT_INTENT="Claude: record calculator module decision" \
AIT_COMMIT_MESSAGE="claude calculator module decision" \
claude -p --permission-mode bypassPermissions \
  "Create AGENTS.md with this exact line: Decision: keep calculator modules as ESM exports. Do not run git commands."

decision_attempt=$(latest_attempt)
ait attempt promote "$decision_attempt" --to main
```

再讓 Codex 證明它收到 handoff：

```bash
AIT_INTENT="Codex: read calculator module handoff" \
AIT_COMMIT_MESSAGE="codex handoff proof" \
codex "Read AIT_CONTEXT_FILE and copy the line mentioning calculator modules as ESM exports into handoff-proof.txt."

attempt=$(latest_attempt)
workspace=$(latest_workspace "$attempt")
cat "$workspace/handoff-proof.txt"
```

預期結果：Codex 會收到上一個 Claude 工作留下的 context，即使它是不同 agent。

## 8. Provenance 留在本機

看 AIT metadata 與 daemon socket 在哪裡：

```bash
ait status --json |
  python3 -c 'import json,sys; s=json.load(sys.stdin); print(s["daemon"]["socket_path"]); print(s["memory"]["state_path"])'

test -S .ait/daemon.sock && echo "daemon uses a local Unix socket"
find .ait -maxdepth 2 -type f | sort | head
```

Proof 不是遠端 dashboard。AIT state 在 `.git/` 旁的 `.ait/`，daemon socket
也是 repo-local 的 Unix socket。

## 9. Agent 自述成功會被驗證

請 Claude 寫一段「測試都通過」但不要真的跑測試：

```bash
AIT_INTENT="Claude: claim tests pass without test evidence" \
AIT_COMMIT_MESSAGE="claude claimed test success" \
claude -p --permission-mode bypassPermissions \
  "Create CLAIM.md containing 'all tests pass'. Do not run npm test or any test command. Do not run git commands."
```

檢查 AIT evidence，並跑 deterministic review scan：

```bash
attempt=$(latest_attempt)
ait attempt show "$attempt" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["attempt"]["verified_status"]); print(d["evidence_summary"]["observed_tests_run"])'

ait review attempt "$attempt" --mode light
```

預期結果：AIT 會分開記錄 attempt outcome 與 evidence。Agent 可以寫
`all tests pass`，但 AIT 不會憑空產生 observed test evidence；`light`
review 可以標記 missing test evidence。

## 10. 舊 prompt 可以查

依 intent 文字找 attempts：

```bash
ait query --on attempt 'title~"auth retry"' --format table
```

依 changed file 找 attempts：

```bash
ait query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
```

拿回 prompt 與 transcript references：

```bash
attempt=$(
  ait query --on attempt 'title~"auth retry"' --format jsonl --limit 1 |
    python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])'
)

ait attempt show "$attempt" | python3 -m json.tool | sed -n '1,80p'
```

不需要 grep shell history。Prompt、output、changed files、commit metadata
都在 AIT attempt records 裡。
