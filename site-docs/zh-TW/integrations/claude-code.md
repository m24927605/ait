---
title: 用 ait 在 Git worktree 中執行 Claude Code
description: >-
  用 ait 包住 Claude Code，每次 session 都在獨立 Git worktree 編輯，並
  記錄完整 attempt provenance — prompt、檔案、狀態、commits — root
  checkout 在 promote 前完全不動。
---

# Claude Code

把 [Claude Code](https://docs.claude.com/en/docs/claude-code) 跑在隔離
的 Git worktree 裡，每個 session 變成可審核的 attempt。

## 為什麼用 ait 包 Claude Code

Claude Code 又快又強，但一個 prompt 就能改你 repo 裡很多檔案。`ait`
把這些工作隔離起來：

- Agent 編輯**獨立 worktree**而不是 root checkout。
- 每次 Claude 執行都成為一筆 **attempt** — prompt、檔案、狀態、output、
  commits 全部串起來。
- 你可以用 Git 概念**檢視、丟棄、rebase、promote** attempt。
- Repo-local memory 把過去 Claude 跑過的東西攤給下一次。

## 設定

```bash
ait init                       # 偵測 PATH 上的 `claude`，自動裝 wrapper + hook
ait adapter doctor claude-code # 可選的 sanity check
```

`ait init` 會掃 `$PATH` 上每個支援的 agent CLI 並一次裝好——對 Claude
Code 而言會安裝 repo-local 的 `claude` wrapper、把 Claude Code 的
hook 設定 merge 進 `.claude/settings.json`。如要顯式重跑（例如 Claude
Code 升級後），用 `ait adapter setup claude-code`。

## 在 ait 下跑 Claude Code

照常使用 Claude Code：

```bash
claude -p --permission-mode bypassPermissions \
  "縮短 README，改善 quickstart"
```

或顯式包：

```bash
ait run --adapter claude-code --intent "重構 query parser" -- claude
```

用環境變數設定明確的 intent 與 commit 訊息：

```bash
AIT_INTENT="更新 README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "縮短 README，改善 quickstart"
```

## 審核與 promote

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

Diff OK 就 promote：

```bash
ait attempt promote <attempt-id> --to main
```

不 OK 就丟掉：

```bash
ait attempt discard <attempt-id>
```

## 相關

- [開始使用](../getting-started.md)
- [Codex CLI 整合](codex.md)
- [Aider 整合](aider.md)
