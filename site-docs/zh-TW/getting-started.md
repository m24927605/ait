---
title: 開始使用 ait
description: >-
  安裝 ait、試跑 demo、初始化 repo、第一次跑 AI coding agent，然後檢查、
  apply 或 recover 這筆 attempt。
---

# 開始使用

`ait` 還是 alpha，而且是 local-first。Metadata 會留在你機器上的 `.ait/`。

這頁只走一條最短路徑：先跑 demo，再初始化 repo，跑一次 agent，檢查 attempt，
最後 apply 或 recover。

## 1. 先跑 demo

不用 API key。不需要現有 repo。也不會真的呼叫 agent。

```bash
pipx install ait-vcs
ait demo
```

Demo 會建立暫存 repo，記錄幾筆 attempts，並示範 review gate 擋下一個高風險
修改。所有東西都在本機。

清掉 demo 目錄：

```bash
ait demo --clean
```

## 2. 安裝成日常指令

建議使用 pipx：

```bash
pipx install ait-vcs
ait --version
```

套件名稱是 `ait-vcs`，指令是 `ait`。需求：Python 3.14+ 與 Git。

如果系統預設 Python 太舊：

```bash
pipx install --python python3.14 ait-vcs
```

其他安裝方式：

```bash
# virtualenv
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs

# npm wrapper
npm install -g ait-vcs

# 固定 GitHub tag
pipx install "git+https://github.com/m24927605/ait.git@v1.4.1"
```

## 3. 初始化 repo

在專案裡執行：

```bash
cd your-repo
ait init
```

`ait init` 會在 `.git/` 旁建立 `.ait/`，並替找到的 agent CLI 安裝 repo-local
wrapper。

如果被提示，允許 shell integration：

```bash
direnv allow
```

確認 agent 指令會經過 `ait`：

```bash
ait status claude-code
ait status codex
ait status --all
```

`wrapped` 代表指令會解析到 repo-local `ait` wrapper。`bypass_risk` 代表目前
shell 還是會直接呼叫真正的 agent binary，所以 `ait` 抓不到這次 run。這時請
執行 `direnv allow`、重開 shell，或跑 `ait repair`，再檢查一次。

## 4. 跑一次 agent

照常使用 agent：

```bash
claude -p "Add a short note to README.md saying we tried ait"
```

被包住的 run 會被記成隔離 attempt。在你 apply 之前，root checkout 不應該被
改動。

## 5. 檢查 attempt

```bash
ait status
ait attempt list
ait attempt show <attempt-id>
```

`ait attempt show` 會顯示這筆 attempt 的 prompt、改過的檔案、output、commit
與 review state。

## 6. Apply 或 recover

如果結果可以接受：

```bash
ait apply latest
```

如果 run 失敗、中斷，或你想手動檢查：

```bash
ait recover latest
ait resume latest
```

在 `ait apply` 之前，agent 的工作只是提案，不是事實。

## 接下來

讓另一個 agent 審查：

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high
```

找回以前的決定：

```bash
ait memory recall "retry budget"
```

使用其他 agent：

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [任意 shell agent](integrations/shell.md)
