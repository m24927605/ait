---
title: 為什麼用 ait — ait 解決的問題
description: >-
  ait 解決的 10 個 AI coding agent 痛點深入解析：blast radius、provenance、
  失敗污染、重複調查、平行安全、apply 模糊、agent-to-agent communication、
  強迫 SaaS、對抗式審查、prompt 搜尋。
---

# 為什麼用 ait

AIT 的產品分類是 **AI coding agents 的本機 control plane**。它是包在
Claude Code、Codex、Aider、Gemini CLI、Cursor 外面的 Git-native attempt
ledger 與 review gate。

AI coding agent 跑得快，但不同 agents 之間的共同記憶、長期記憶、溝通交接
與審核紀律通常跟不上。`ait` 讓 agents 透過 repo-local memory 交接資訊：
prior attempts、accepted facts、notes、review findings 與 live memory files
會變成下一個 agent 的 handoff context。同一筆 attempt 也可以先被另一個
reviewer agent 對抗式審查，再由你決定哪些結果可以進 working tree。
下面是 ait 解決的每個問題的長版本，以及對應的解法。

想看可重跑證據，請看 [痛點 demo](demos/pain-point-demos.md)。

## 1. Blast radius 失控

**痛點：** 一句送給 Claude Code 或 Codex 的 prompt 可以改 30 個檔案、
刪整個目錄、覆蓋你正在手動編輯的內容。撤銷只能 `git stash` + `git
reset --hard`，常常順手把自己的進行中工作也炸掉。

**解法：** 每次執行落在隔離 Git worktree。Root checkout 永遠不動。
爛 attempt 直接 `ait attempt discard <id>` — 零波及。

可執行範例：[`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius)

## 2. Diff 沒有 provenance

**痛點：** 三天後你回不答：這段 diff 是哪個 prompt 產的？用了哪些
context 檔？exit 0 還是 130？Shell history 不夠。

**解法：** 每筆 attempt 把 intent、prompt、退出狀態、變更檔案、捕捉
output、產生的 commits 串成一筆可查的紀錄。`ait attempt show <id>`
一次拿全。

可執行範例：[`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance)

## 3. 失敗的執行污染 working copy

**痛點：** Agent 跑到一半 timeout，留下一堆雜亂 commits、半套修改、
未追蹤檔案。手動清不乾淨還會混入下次執行。

**解法：** 失敗 attempt 留在自己的 worktree 裡審或 `discard`。主分支
從頭到尾乾淨。

可執行範例：[`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation)

## 4. 同份調查付兩次錢

**痛點：** 上週 Claude 已經查過 auth retry 為什麼失敗。這週 Codex 又
從零開始查。一樣的 token 花兩遍。

**解法：** Repo-local memory 把過去 attempts、commits、curated notes、
accepted facts、review findings，以及即時讀取的 agent memory 檔
（`CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、
`.cursor/rules`）組成一份 `AIT_CONTEXT_FILE` 餵給下一次執行。

可執行範例：[`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse)

## 5. 平行 agent 互相覆蓋

**痛點：** 想讓 Claude 和 Codex 同時試兩種解法、再挑一個更好的 diff？
兩個都搶 working copy，互相破壞。

**解法：** 每個 attempt 自帶 worktree。可平行跑 N 個 agent，把 attempts
並排比較，再 apply 你信的那一個。

可執行範例：[`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents)

## 6. Apply 模糊

**痛點：** Agent 說「我修好了」。要不要採用 diff？直接 commit 怕髒，
事後 revert 又是磨擦。

**解法：** Apply 是顯式步驟：`ait apply latest` 或
`ait apply <attempt-id> --mode current`。你不呼叫，agent 的工作就只是提案，
不是事實。

可執行範例：[`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion)

## 7. Agents 不能互相溝通

**痛點：** Claude 跑了三輪，換 Aider 接手，前面的決策、死路、半套修補
全都不見。Codex 又重查一次同一個問題，因為有用脈絡困在另一個聊天視窗。

**解法：** Memory layer 在 handoff 當下即時讀 AIT-owned attempt history、
accepted facts、notes、review findings、`CLAUDE.md`、`AGENTS.md`、
`.claude/memory.md`、`.codex/memory.md` 與 Cursor rules。下一個 agent
— 同一個或不同 — 會收到 `AIT_CONTEXT_FILE`，接續 policy 允許的共同 repo
context，而不是從空白的私有聊天開始。

可執行範例：[`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff)

## 8. Provenance 工具強迫你上雲

**痛點：** 多數 agent provenance / observability 工具是 SaaS。需要把
prompt、diff、原始碼上傳。對很多 repo 而言不可能。

**解法：** 一切活在 `.git/` 旁的 `.ait/` 裡。Harness daemon 純本機 —
Unix socket、不對外連網。沒 telemetry、沒 SaaS、沒跨機器同步。安全敏感
的 repo 也能用。

可執行範例：[`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance)

## 9. 看起來合理的 agent 結果仍然需要被挑戰

**痛點：** Agent 產生的修改看起來可能很合理，但證據不足：沒有測試、檢查
不完整，或用很有自信的說法掩蓋了邊界條件風險。

**解法：** AIT 可以保留原本 attempt，並另外記錄一份對抗式審查。審查目標
是一筆 AIT attempt，不是鬆散 diff；審查結果會變成可查詢 evidence。當
review gate 開啟時，blocked review 可以 hold 住 `ait apply`。

```bash
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
ait apply <attempt-id> --mode current
```

可執行範例：[`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence)、[`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer)

## 10. 找舊 prompt 要 grep shell history

**痛點：** 「上個月寫的那個重構 query parser 的 prompt 在哪？」用 raw
shell history 答不出來。

**解法：** Attempts、intents、commits 用結構化 DSL 可查。可依 intent 文字、
狀態、agent、時間範圍、變更檔案等等查。

可執行範例：[`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search)

## 那又怎樣

如果上面這 10 個痛點有任何一個對你夠痛，足以讓你忍受多打一條指令
（`ait init`），那 ait 剩下的部分就只是你原本的 agent workflow 加上
一條安全帶。

```bash
pipx install ait-vcs    # 或 npm install -g ait-vcs
cd your-repo
ait init
claude ...              # codex / aider / gemini / cursor 都一樣
```

接著看 [開始使用](getting-started.md) 並挑你的
[整合方式](integrations/claude-code.md)。
