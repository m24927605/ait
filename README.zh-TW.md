<div align="center">

# ait

### 給 AI coding agents 使用的 Git-native 安全工作流

讓 Claude Code、Codex、Aider、Gemini、Cursor 在隔離的 Git worktree
中執行，並保留可追溯的 commits、可 review 的 attempts，以及 repo-local
memory。

<sub>[English](README.md) · [繁體中文](README.zh-TW.md)</sub>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#狀態)

</div>

---

AI agents 很快，但 Git history、review discipline、handoff context
通常跟不上。

`ait` 會包住你已經在用的 agent CLI，並把每次執行變成一個可 review
的 attempt。Agent 會在隔離的 worktree 裡改檔，`ait` 會記錄發生了什麼；
在你明確 promote 之前，主要 checkout 不會被碰到。

```bash
pipx install ait-vcs
cd your-repo
ait init
direnv allow   # 只有被提示時才需要

claude ...
```

偏好 npm？

```bash
npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

PyPI 與 npm 上的套件名稱是 `ait-vcs`，安裝後的指令是 `ait`。

## ait 解決的問題

| 用 AI agent 寫 code 的痛點 | ait 提供的解法 |
| --- | --- |
| 一個爛 prompt 在你發現前就改了半個 repo | 每次執行都落在隔離的 Git worktree — root checkout 永遠不動 |
| diff 沒有 provenance — 不知道是哪個 prompt 產的 | Attempt 把 intent、command output、files、commits 串成一筆紀錄 |
| 失敗或半成品的執行污染了 working copy | 爛 attempt 留在 worktree 裡，`ait attempt discard` 一鍵清掉 |
| 下一個 agent 又重做你已經花 token 買過的調查 | Repo-local memory 把過去 attempts、commits 餵給下一次執行 |
| 兩個 agent 跑同一件事會互相覆蓋 | 每個 attempt 自帶 worktree — 可平行跑 N 個 agent |
| Agent 說「修好了」，但真的修好了嗎？ | 顯式 `ait attempt promote` — 不主動採納，主分支永遠由你決定 |
| 跨 agent hand-off 會弄丟之前所有的決策 | Memory layer 自動匯入 `CLAUDE.md`、`AGENTS.md`、過往 attempts |
| Provenance 工具強迫你把 code 上傳到 SaaS | Metadata 就在 `.git/` 旁的 `.ait/` — daemon 純本機 Unix socket、不對外連網、無 telemetry |
| 「上個月寫過的那個 prompt 在哪？」→ grep shell history | 用結構化 DSL 直接查 attempts、intents、commits |

`ait` 不是另一個 agent。它是包在你信任的 agents 外面的 Git 工作層。

## 使用起來像這樣

初始化一次：

```bash
ait init
direnv allow   # 只有被提示時才需要
```

接著照常使用你的 agent：

```bash
claude ...
codex ...
aider ...
gemini ...
cursor ...
```

Agent 成功執行後，查看 attempt：

```bash
ait status
ait attempt show <attempt-id>
```

確認沒問題後再 promote：

```bash
ait attempt promote <attempt-id> --to main
```

在 promote 之前，你的 root checkout 會保持不變。

## 核心功能

| 功能 | 說明 |
| --- | --- |
| Worktree isolation | Agent 的修改會發生在 root checkout 之外 |
| Attempt provenance | commands、status、output、changed files、commits 會被串在一起 |
| Agent wrappers | repo-local 的 `claude`、`codex`、`aider`、`gemini`、`cursor` wrappers |
| Auto commit capture | 成功的修改會變成 attempt-linked commits；若 agent 已 commit，ait 不會重複 commit |
| Local memory | 過去的 attempts、commits、notes、imported agent memory 會提供給後續 runs |
| Review flow | 用 Git 概念 inspect、promote、discard、rebase、query attempts |

## 快速範例

明確指定 intent 與 commit message：

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "Shorten the README and improve the quickstart"
```

直接包住某個 command：

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

使用 repo-local memory：

```bash
ait memory
ait memory search "auth adapter"
ait memory recall "billing retry"
```

修復本機 wrapper 設定：

```bash
ait repair
ait repair codex
```

## 整合（Integrations）

`ait` 為主流 AI coding agent 提供 first-class adapter，把每次執行都包進
獨立的 Git worktree，並把過程記錄在 `.ait/`。

### 在 Git worktree 中執行 Claude Code

```bash
ait adapter setup claude-code
claude -p --permission-mode bypassPermissions "Refactor the auth module"
```

`ait` 會把 prompt、變更檔案、執行狀態與 commits 紀錄為一次 attempt。確認
diff 後再用 `ait attempt promote <id> --to main` 推上主線。

### 安全地在真實 repo 跑 Codex CLI

```bash
ait adapter setup codex
ait run --adapter codex --intent "Implement parser edge cases" -- codex
```

每個 Codex session 都在隔離 worktree 裡編輯。失敗的 attempt 會留下供
檢查；只有 promote 過的 attempt 會碰到 root checkout。

### 在隔離 worktree 中跑 Aider

```bash
ait adapter setup aider
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
```

Aider 的 commits 落在 attempt worktree 內，附帶完整的 prompt、檔案、
commit 對應關係。

### Gemini CLI 搭配 attempt 歷史

```bash
ait adapter setup gemini
ait run --adapter gemini --intent "Add config validation" -- gemini
```

Gemini 的 session 與 Claude Code、Codex 一樣會被記錄成 attempt。日後可
用 `ait memory recall` 查找各 agent 嘗試過什麼。

### Cursor agent 帶可審核的 provenance

```bash
ait adapter setup cursor
ait run --adapter cursor --intent "Migrate to new SDK" -- cursor
```

Cursor 的編輯被限制在 attempt worktree 內。Attempt log 保留變更檔案、
退出狀態與 commits，方便審核與 promote。

### 包裝其他 shell agent

```bash
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

使用通用 `shell` adapter 即可為任何自訂 agent 或 script 加上 attempt
provenance。

## 運作方式

```text
your prompt
    |
    v
agent CLI wrapped by ait
    |
    v
isolated attempt worktree
    |
    v
attempt metadata + commits + memory
    |
    v
review, promote, discard, or rebase
```

被包住的 process 會收到：

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
AIT_CONTEXT_FILE   # 啟用 context 時
```

`AIT_CONTEXT_FILE` 會包含精簡的 repo-local handoff，內容來自過去的
attempts、commits、curated notes，以及匯入的 agent memory files，例如
`CLAUDE.md` 和 `AGENTS.md`。

## 安裝

推薦方式：

```bash
pipx install ait-vcs
ait --version
```

Virtual environment：

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

指定 GitHub release：

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.36"
```

升級：

```bash
ait upgrade
ait --version
```

預覽升級指令：

```bash
ait upgrade --dry-run
```

## 常用指令

```bash
ait status
ait status --all
ait doctor
ait doctor --fix

ait adapter list
ait adapter doctor claude-code
ait adapter setup claude-code

ait attempt list
ait attempt show <attempt-id>
ait intent show <intent-id>
ait context <intent-id>

ait memory
ait memory search "auth adapter"
ait memory lint
ait memory lint --fix

ait graph
ait graph --html
```

Shell auto-activation：

```bash
ait shell show --shell zsh
ait shell install --shell zsh
ait shell uninstall --shell zsh
```

## 系統需求

- Python 3.14+
- Git
- Python standard library 內建的 SQLite
- 透過 npm 安裝時才需要 Node.js 18+

## 狀態

`ait` 目前是 `0.55.36`，仍屬 alpha quality。它適合 local dogfooding，
以及熟悉 Git workflow、願意早期試用的使用者。

Metadata 只會存在單一 repo 的 `.ait/` 底下，不會跨機器同步。

## 開發

設定開發環境：

```bash
python3.14 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install pytest
```

驗證：

```bash
.venv/bin/pytest -q
.venv/bin/ait --version
.venv/bin/ait --help
```

發布前：

```bash
git status --short
.venv/bin/pytest -q
```

`pyproject.toml`、Git tag、README 中的版本號應保持一致。

## 文件

- [Getting started](docs/getting-started.md)
- [Claude Code run worktree workflow](docs/claude-code-run-worktree.md)
- [Claude Code hook smoke test](docs/claude-code-live-smoke.md)
- [Long-term memory design](docs/long-term-memory-design.md)
- [Long-term memory acceptance](docs/long-term-memory-acceptance.md)
- [Repo brain design](docs/repo-brain-design.md)
- [Repo brain acceptance](docs/repo-brain-acceptance.md)
- [Release checklist](docs/release-checklist.md)
