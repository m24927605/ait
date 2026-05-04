---
title: 開始使用 ait
description: >-
  在現有 Git repo 安裝 ait、初始化、第一次跑 AI coding agent，並把
  整段執行記成 attempt provenance。
---

# 開始使用

## 系統需求

- Python 3.14 或更新
- Git
- SQLite（Python 標準庫內建）
- Node.js 18+（只在用 npm 安裝時需要）

## 安裝

建議（pipx）：

```bash
pipx install ait-vcs
ait --version
```

虛擬環境：

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --help
```

npm wrapper：

```bash
npm install -g ait-vcs
ait --version
```

固定 GitHub tag：

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.38"
```

## 初始化 repository

任何 Git repository 內：

```bash
cd your-repo
ait init
direnv allow   # 只在被提示時才需要
```

`ait init` 會在 `.git/` 旁建立 `.ait/` 目錄。所有 AI metadata 都留在這
資料夾，不會跨機器同步。

## 第一次跑包裝過的 agent

任何支援的 agent CLI。`ait` 會偵測並記錄一筆 attempt：

```bash
claude -p --permission-mode bypassPermissions "重構 auth 模組"
```

檢查發生了什麼：

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

確認後 promote：

```bash
ait attempt promote <attempt-id> --to main
```

Promote 之前 root checkout 完全不變。

## 接下來

- [在 worktree 裡跑 Claude Code](integrations/claude-code.md)
- [安全地跑 Codex CLI](integrations/codex.md)
- [跑 Aider 帶 provenance](integrations/aider.md)
- [指令參考](reference/commands.md)
