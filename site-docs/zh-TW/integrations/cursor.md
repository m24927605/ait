---
title: 用 ait 跑 Cursor agent 帶可審核的 Git provenance
description: >-
  用 ait 包住 Cursor CLI agent，每次執行都在獨立 Git worktree 編輯，
  並產出含檔案、狀態、commits 的 attempt log 供審核。
---

# Cursor

讓 [Cursor](https://cursor.sh/) CLI agent 跑在 `ait` 管理的隔離 Git
worktree 內，每次 agent 執行都記成可審核的 attempt。

## 為什麼用 ait 包 Cursor agent

- Cursor 編輯被限制在 attempt worktree 內。
- 每次執行產生 attempt log：prompt、變更檔案、退出狀態、commits。
- Promote 是顯式的 — root checkout 不會被靜默修改。

## 設定

```bash
ait init
ait adapter setup cursor
ait adapter doctor cursor
```

## 在 ait 下跑 Cursor

```bash
ait run --adapter cursor --intent "遷移到新 SDK" -- cursor
```

或設定完後直接呼叫包裝過的 `cursor` 指令。

## 審核與 promote

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

## 相關

- [開始使用](../getting-started.md)
- [Claude Code 整合](claude-code.md)
- [Gemini CLI 整合](gemini.md)
