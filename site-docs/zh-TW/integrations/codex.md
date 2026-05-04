---
title: 用 Git worktree 隔離安全地跑 Codex CLI
description: >-
  用 ait 包住 OpenAI Codex CLI，每次 session 都在隔離 Git worktree 編輯，
  prompt、output、commits 都記成可審核 attempt。
---

# Codex CLI

把 [Codex CLI](https://github.com/openai/codex) 用 `ait` 包起來，每次
session 都在獨立 Git worktree 跑、含完整 provenance。

## 為什麼用 ait 包 Codex

- Codex 變更被限制在 attempt worktree — promote 前 root checkout 不動。
- 失敗的 session 留下供檢視，不會悄悄消失。
- 連續 Codex 執行會餵 ait repo-local memory，下一次 session 會記得
  之前試過什麼。

## 設定

```bash
ait init
ait adapter setup codex
ait adapter doctor codex
```

## 在 ait 下跑 Codex

設定完後直接呼叫即可：

```bash
codex
```

或用 intent 顯式包：

```bash
ait run --adapter codex --intent "實作 parser edge cases" -- codex
```

## 修復與重整

如果 wrapper 漂掉了（例如 Codex 升版後）：

```bash
ait repair codex
```

## 審核 attempts

```bash
ait attempt list
ait attempt show <attempt-id>
ait memory recall "parser edge cases"
```

## 相關

- [開始使用](../getting-started.md)
- [Claude Code 整合](claude-code.md)
- [Aider 整合](aider.md)
