---
title: ait — AI coding agent 的 Git 工作層
description: >-
  ait 把 Claude Code、Codex、Aider、Gemini CLI、Cursor 包進 Git worktree
  隔離層，記錄 attempt provenance、跨 session repo-local 記憶與摘要、跨
  agent 脈絡傳遞，並用顯式 promote 讓 root checkout 永遠由你決定。
  開源、零依賴、跑在 Git 之上。
---

# ait

**為 AI coding agent 設計的 Git 工作層 — worktree 隔離、attempt
provenance、跨 session 記憶、可審核 promote。**

`ait` 包住你已經在用的 agent CLI——Claude Code、Codex、Aider、Gemini
CLI、Cursor——把每次執行變成一筆**可審核的 attempt**。Agent 編輯獨立
的 Git worktree，`ait` 紀錄發生過什麼，你的 root checkout 在你親手
promote 之前不會被動到。

```bash
pipx install ait-vcs    # 或用 npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

PyPI 與 npm 上的套件名是 `ait-vcs`，安裝後的指令是 `ait`。

## 為什麼用 ait

| 用 AI agent 寫 code 的痛點 | ait 提供的解法 |
| --- | --- |
| 一個爛 prompt 在你發現前就改了半個 repo | 每次執行都落在隔離的 Git worktree — root checkout 永遠不動 |
| diff 沒有 provenance — 不知道是哪個 prompt 產的 | Attempt 把 intent、command output、files、commits 串成一筆紀錄 |
| 失敗或半成品的執行污染了 working copy | 爛 attempt 留在 worktree 裡，`ait attempt discard` 一鍵清掉 |
| 下一個 agent 又重做你已經花 token 買過的調查 | Repo-local memory 把過去 attempts、commits 餵給下一次執行 |
| 兩個 agent 跑同一件事會互相覆蓋 | 每個 attempt 自帶 worktree — 可平行跑 N 個 agent |
| Agent 說「修好了」，但真的修好了嗎？ | 顯式 `ait attempt promote` — 不主動採納，主分支永遠由你決定 |
| 跨 agent hand-off 會弄丟之前所有的決策 | Memory layer 自動匯入 `CLAUDE.md`、`AGENTS.md`、過往 attempts |
| Provenance 工具強迫你把 code 上傳到 SaaS | Metadata 就在 `.git/` 旁的 `.ait/` — 純本機、無 telemetry、無 daemon |
| 「上個月寫過的那個 prompt 在哪？」→ grep shell history | 用結構化 DSL 直接查 attempts、intents、commits |

完整深入的解析請看 [為什麼用 ait](why-ait.md)。

`ait` **不是**另一個 agent。它是包在你信任的 agents 外面的 Git
工作層。

## 支援的 agent

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [其他 shell agent](integrations/shell.md)

## 狀態

`ait` 仍屬 alpha quality，適合本機 dogfooding 與熟悉 Git 工作流的早期
使用者。Metadata 是 repo-local 的（存在 `.ait/`），不會跨機器同步。

## 專案連結

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI 套件](https://pypi.org/project/ait-vcs/)
- [npm 套件](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
