---
title: 用 ait 在隔離 Git worktree 中跑 Aider
description: >-
  用 ait 包住 Aider，每次 session 都在獨立 Git worktree 編輯。Aider
  的 commits 落在 attempt 內，附完整 prompt 與檔案 provenance，可審
  可 promote。
---

# Aider

讓 [Aider](https://aider.chat/) 跑在 `ait` 管理的隔離 Git worktree 內，
每個 session 都記成可審核的 attempt。

## 為什麼用 ait 包 Aider

- Aider commits 進隔離 worktree — 在 promote 之前主分支保持乾淨。
- 每次 session 變成一筆 attempt，含 prompt、變更檔案、Aider 產生的
  commits。
- Repo-local memory 把過去 Aider session 留下可查。

## 設定

```bash
ait init
ait adapter setup aider
ait adapter doctor aider
```

## 在 ait 下跑 Aider

```bash
ait run --adapter aider --intent "修 auth expiry" -- aider src/auth.py
```

或設定完後直接在 repo 內呼叫 `aider`。

## 審核與 promote

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

## 相關

- [開始使用](../getting-started.md)
- [Claude Code 整合](claude-code.md)
- [Codex CLI 整合](codex.md)
