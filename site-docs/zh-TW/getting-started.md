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
pipx install "git+https://github.com/m24927605/ait.git@v0.55.59"
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

檢查目前 shell 會不會真的把 agent 指令導進 AIT：

```bash
ait status claude-code
ait status codex
ait status --all
```

`Bypass detection: wrapped` 代表指令會解析到 repo-local AIT wrapper。
`Bypass detection: bypass_risk` 代表指令會直接解析到真正的 agent binary，
等於繞過 AIT，prompt 與失敗 evidence 都不會被捕捉。重新啟用 shell
integration、執行 `direnv allow` 或 `ait repair`，再檢查一次 status。

## 第一次跑包裝過的 agent

任何支援的 agent CLI。`ait` 會偵測並記錄一筆 attempt：

```bash
claude -p --permission-mode bypassPermissions "重構 auth 模組"
```

檢查發生了什麼：

```bash
ait status
```

確認後 apply：

```bash
ait apply latest
```

Apply 之前 root checkout 完全不變。若 run 失敗或無法安全套用，使用
`ait recover latest`。如果 agent session 被關掉、你想回到保留的 worktree
續修，使用 `ait resume latest`。

## 把既有 agent memory 納入視野

既有專案如果已經有 agent memory files，先預覽 AIT 看得到什麼：

```bash
ait memory backfill --dry-run
```

Dry-run 不會寫入任何東西。要把 repo-local advisory memory 匯入 `.ait/`，
再執行：

```bash
ait memory backfill --import
```

Global 或 repo 外部 memory 會被忽略，除非你明確指定 `--global --path ...`。

## 接下來

- [安全地跑 Claude Code](integrations/claude-code.md)
- [安全地跑 Codex CLI](integrations/codex.md)
- [跑 Aider 帶 provenance](integrations/aider.md)
- [指令參考](reference/commands.md)
