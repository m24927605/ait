---
title: 為什麼用 ait — ait 解決的問題
description: >-
  ait 解決的 10 個 AI coding agent 痛點深入解析：blast radius、provenance、
  失敗污染、重複調查、平行安全、promote 模糊、跨 agent 脈絡、強迫 SaaS、
  自述驗證、prompt 搜尋。
---

# 為什麼用 ait

AI coding agent 跑得快。Git history、審核紀律、跨 session 的 hand-off
脈絡跟不上。`ait` 用一層薄的 Git-native 設計把這個落差補起來。下面是
ait 解決的每個問題的長版本，以及對應的解法。

## 1. Blast radius 失控

**痛點：** 一句送給 Claude Code 或 Codex 的 prompt 可以改 30 個檔案、
刪整個目錄、覆蓋你正在手動編輯的內容。撤銷只能 `git stash` + `git
reset --hard`，常常順手把自己的進行中工作也炸掉。

**解法：** 每次執行落在隔離 Git worktree。Root checkout 永遠不動。
爛 attempt 直接 `ait attempt discard <id>` — 零波及。

## 2. Diff 沒有 provenance

**痛點：** 三天後你回不答：這段 diff 是哪個 prompt 產的？用了哪些
context 檔？exit 0 還是 130？Shell history 不夠。

**解法：** 每筆 attempt 把 intent、prompt、退出狀態、變更檔案、捕捉
output、產生的 commits 串成一筆可查的紀錄。`ait attempt show <id>`
一次拿全。

## 3. 失敗的執行污染 working copy

**痛點：** Agent 跑到一半 timeout，留下一堆雜亂 commits、半套修改、
未追蹤檔案。手動清不乾淨還會混入下次執行。

**解法：** 失敗 attempt 留在自己的 worktree 裡審或 `discard`。主分支
從頭到尾乾淨。

## 4. 同份調查付兩次錢

**痛點：** 上週 Claude 已經查過 auth retry 為什麼失敗。這週 Codex 又
從零開始查。一樣的 token 花兩遍。

**解法：** Repo-local memory 把過去 attempts、commits、agent memory 檔
（`CLAUDE.md`、`AGENTS.md`）摘要成一份 `AIT_CONTEXT_FILE` 餵給下一次
執行。

## 5. 平行 agent 互相覆蓋

**痛點：** 想讓 Claude 和 Codex 同時試兩種解法、再挑一個更好的 diff？
兩個都搶 working copy，互相破壞。

**解法：** 每個 attempt 自帶 worktree。可平行跑 N 個 agent，比 attempts
側邊側邊比，promote 你信的那一個。

## 6. Promote 模糊

**痛點：** Agent 說「我修好了」。要不要採用 diff？直接 commit 怕髒，
事後 revert 又是磨擦。

**解法：** Promotion 是顯式動詞：`ait attempt promote <id> --to main`。
你不呼叫，agent 的工作就只是提案，不是事實。

## 7. 跨 agent hand-off 弄丟脈絡

**痛點：** Claude 跑了三輪，換 Aider 接手，前面的決策、死路、半套修補
全都不見。

**解法：** Memory layer 自動匯入 `CLAUDE.md`、`AGENTS.md` 與過去 attempts，
下一個 agent — 同一個或不同 — 接續共同的歷史。

## 8. Provenance 工具強迫你上雲

**痛點：** 多數 agent provenance / observability 工具是 SaaS。需要把
prompt、diff、原始碼上傳。對很多 repo 而言不可能。

**解法：** 一切活在 `.git/` 旁的 `.ait/` 裡。Harness daemon 純本機 —
Unix socket、不對外連網。沒 telemetry、沒 SaaS、沒跨機器同步。安全敏感
的 repo 也能用。

## 9. 自述的成功不可驗證

**痛點：** Agent 聲稱「all tests pass」。有時真的跑了。有時 cherry-pick
某個 suite。有時根本沒跑。

**解法：** Verifier 依實際退出狀態、檔案變更、commit 結果決定
`succeeded` / `promoted` / `failed`，不依 agent 自述。

## 10. 找舊 prompt 要 grep shell history

**痛點：** 「上個月寫的那個重構 query parser 的 prompt 在哪？」用 raw
shell history 答不出來。

**解法：** Attempts、intents、commits 用結構化 DSL 可查。可依 intent 文字、
狀態、agent、時間範圍、變更檔案等等查。

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
