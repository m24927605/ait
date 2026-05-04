---
title: 用 ait 在跨 session 帶 attempt 歷史地跑 Gemini CLI
description: >-
  用 ait 包住 Gemini CLI，每次 session 都在獨立 Git worktree 編輯，
  並記成可審核 attempt，跨執行有 repo-local memory。
---

# Gemini CLI

讓 [Gemini CLI](https://github.com/google-gemini/gemini-cli) 跑在 `ait`
管理的隔離 Git worktree 內，每個 session 記成可審核的 attempt。

## 為什麼用 ait 包 Gemini CLI

- 每次 Gemini session 編輯 attempt worktree，不是 root checkout。
- Sessions 日後可用 `ait memory recall` 查。
- 你只 promote 想要的 attempts。

## 設定

```bash
ait init
ait adapter setup gemini
ait adapter doctor gemini
```

## 在 ait 下跑 Gemini

```bash
ait run --adapter gemini --intent "加 config 驗證" -- gemini
```

或設定完後直接在 repo 內呼叫 `gemini`。

## 審核 attempts

```bash
ait attempt list
ait attempt show <attempt-id>
```

## 相關

- [開始使用](../getting-started.md)
- [Claude Code 整合](claude-code.md)
- [Cursor 整合](cursor.md)
