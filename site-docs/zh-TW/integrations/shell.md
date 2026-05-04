---
title: 用 Git worktree 隔離包裝任意 shell agent
description: >-
  用 ait 通用 shell adapter 為任何自訂 AI agent、自動化腳本或 CLI 工具
  提供 Git worktree 隔離與 attempt provenance。
---

# Shell agents

`shell` adapter 包**任何**指令——自訂 agent、自動化腳本、一次性工具
——讓工作發生在 attempt worktree 內含完整 provenance。

## 何時用 shell adapter

- 你有個自訂 AI agent，還沒被列為 first-class adapter。
- 想把 fixture 重生 script 或一次性自動化記成 attempt。
- 想對任意指令套用同樣的審核 + promote 流程。

## 在 ait 下跑任何指令

```bash
ait run --adapter shell --intent "重生 fixtures" -- \
  python scripts/regenerate_fixtures.py
```

`--` 之後就是要跑的指令。`ait` 紀錄 prompt（intent）、退出狀態、變更
檔案、指令產生的 commits。

## 審核 attempts

```bash
ait attempt list
ait attempt show <attempt-id>
```

## 相關

- [開始使用](../getting-started.md)
- [Claude Code 整合](claude-code.md)
