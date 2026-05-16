<div align="center">

# ait

### AI agent 應該在 attempt 裡動手、共享脈絡，最後才 apply

把 Claude Code、Codex、Aider、Gemini、Cursor 的每次執行變成隔離、
可追溯、可審核的 attempt；讓 agents 透過 repo-local memory 交接脈絡，
而不是困在各自的聊天視窗裡。在你明確 apply 前，結果不會進入 root checkout。

<sub>[English](README.md) · [繁體中文](README.zh-TW.md)</sub>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](#狀態)

</div>

---

AI coding agent 已經快到可以直接重構真實 repo，但預設工作流很容易讓它們把
你的 working tree 當草稿紙，也很容易忘掉另一個 agent 剛剛查到的結論。

`ait` 是包在既有 agent CLI 外面的一層 Git 工作流。你照常使用 Claude Code、
Codex、Aider、Gemini 或 Cursor；AIT 會把每次執行變成一個可審核的
attempt。Agent 在隔離 worktree 裡修改程式，AIT 記錄 prompt、狀態、變更、
commit 與 evidence；在你明確 apply 之前，主要 checkout 不會被碰到。

Claude 做過的調查可以變成 Codex 的上下文；Cursor rules 可以跟著 Aider 的
下一次修補一起進來；對高風險變更，AIT 也能加上一道對抗式 code review：讓
另一個 agent 在套用前挑戰這次 attempt，必要時擋下 `ait apply`。

```bash
pipx install ait-vcs
cd your-repo
ait init
direnv allow   # 只有被提示時才需要

claude ...
```

偏好 npm 的話：

```bash
npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

PyPI 與 npm 上的套件名稱是 `ait-vcs`，安裝後的指令是 `ait`。

<p align="center">
  <img src="site-docs/assets/ait-work-graph.png" alt="AIT Work Graph：attempts、evidence、memory、hot files 與 query filters" width="960">
</p>

<p align="center"><sub><code>ait graph --html</code> 產生的本機 HTML 報告：attempts、evidence、memory、hot files 與 query filters 集中在同一張圖裡。</sub></p>

## 核心特色

| 特色 | 說明 |
| --- | --- |
| Attempt-first 工作流 | AIT 包住你已經在用的 agent CLI，先把每次執行變成隔離 attempt，再由你決定是否 apply 到 root checkout。 |
| Worktree 隔離 | 每次執行都有自己的內部 Git worktree，失敗或高風險 attempt 不會污染目前工作目錄。 |
| Attempt provenance | prompt、intent、adapter、output、changed files、commits、trace references、status、outcome 會串成一筆紀錄。 |
| Wrapper bypass 偵測 | `ait status <adapter>` 會告訴你目前 shell 會進 AIT wrapper，還是會 silent 地直接呼叫真正的 agent binary。 |
| Live federated memory | Claude Code、Codex、Aider、Gemini、Cursor 與 shell agents 可以讀同一份即時 repo memory：AIT-owned history 加上目前的 `CLAUDE.md`、`AGENTS.md`、`.claude/`、`.codex/` 與 Cursor rules。 |
| 長期 repo memory | 有價值的 attempts、commits、notes、accepted facts、prior findings，以及明確 adopt 的 memory 可以跨 terminal、跨 session、跨週期保留下來。 |
| Agent-to-agent communication | 一個 agent 做過的調查、決策、失敗路線或 review finding，可以透過 `AIT_CONTEXT_FILE` 傳給後續另一個 agent，而不是藏在某個聊天視窗裡。 |
| 平行 agent attempts | 多個 agents 可以同時試不同做法，不會在同一個 checkout 裡互相覆蓋。 |
| 明確 apply/recover 流程 | Agent 產出的結果在 apply 前只是提案；held 或 failed work 仍可 recover，不會變成 working-copy 爛攤子。 |
| 對抗式審查 | 另一個 reviewer agent 可以挑戰 attempt；高風險 finding 可以被記錄，並用來 hold apply。 |
| Local-first metadata | AIT metadata 存在 `.git/` 旁的 `.ait/`；不需要 SaaS dashboard、不做 telemetry、不要求上傳原始碼。 |
| 可查詢歷史 | Attempts、intents、files、agents、statuses、review results、舊 prompts 都可以用 AIT 指令查，不必翻 shell history。 |

## ait 解決的問題

| 用 AI agent 寫程式的痛點 | AIT 提供的解法 | 可執行範例 |
| --- | --- | --- |
| 一個不精準的 prompt 在你發現前就改了半個 repo | 每次執行都在隔離 Git worktree 裡進行，root checkout 不會被直接修改 | [`01-blast-radius`](examples/pain-point-demos/01-blast-radius/) |
| diff 看得出改了什麼，卻看不出怎麼來的 | attempt 會串起 intent、prompt、command output、changed files 與 commits | [`02-provenance`](examples/pain-point-demos/02-provenance/) |
| 失敗或半成品污染 working copy | 失敗 attempt 保留在隔離 worktree，主 checkout 維持乾淨，可用 `ait recover latest` 查看 | [`03-failed-run-isolation`](examples/pain-point-demos/03-failed-run-isolation/) |
| 換一個 agent 接手，又從頭調查同一件事 | 共同 repo-local memory 會把過去 attempts、commits、notes、accepted facts 餵給後續執行 | [`04-memory-reuse`](examples/pain-point-demos/04-memory-reuse/) |
| Claude 和 Codex 同時跑會互相覆蓋 | 每個 attempt 都有自己的 worktree，可以平行跑多個 agent 再比較結果 | [`05-parallel-agents`](examples/pain-point-demos/05-parallel-agents/) |
| Agent 說「修好了」，但你不確定該不該採用 | `ait apply latest` 是明確動作；沒有 apply 前，agent 的成果只是提案 | [`06-explicit-promotion`](examples/pain-point-demos/06-explicit-promotion/) |
| 跨 agent hand-off 會弄丟決策與脈絡 | Live repo memory 會把目前的 agent memory files、過往 attempts、notes 與已接受決策組成同一份 context | [`07-cross-agent-handoff`](examples/pain-point-demos/07-cross-agent-handoff/) |
| provenance 工具要求把原始碼送到 SaaS | metadata 留在 repo 內的 `.ait/`；daemon 只走本機 Unix socket，沒有 telemetry | [`08-local-only-provenance`](examples/pain-point-demos/08-local-only-provenance/) |
| 寫程式的 agent 自己審自己，容易放過盲點 | 可交給另一個 reviewer agent 做對抗式審查，高風險 finding 可以擋下 apply | [`09-verification-evidence`](examples/pain-point-demos/09-verification-evidence/)、[`09-1-codex-reviewer`](examples/pain-point-demos/09-1-codex-reviewer/) |
| 想找上個月那段 prompt，只能 grep shell history | 用結構化 DSL 查 attempts、intents、commits、agent、狀態與變更檔案 | [`10-prompt-search`](examples/pain-point-demos/10-prompt-search/) |

`ait` 不是另一個 agent。它是包在你已經信任的 agents 外面的本機 attempt
工作流。

## 核心概念

AIT 的核心不是取代 Claude Code 或 Codex，而是讓它們先在 attempt 裡工作。
每次 agent 執行都會變成一筆 attempt：有自己的隔離 worktree、有 provenance、
有可查詢的 metadata，也有明確的 apply/recover 流程。

這讓 AI 產生的修改先停留在「可審核的提案」狀態。你可以比較不同 agents 的
attempts、查看它們改了哪些檔案、保留失敗結果作為 recovery 線索，最後再決定
哪一個要套用到目前 checkout。

AIT 的 memory 是 repo-local、可檢查的專案記憶，不是某個聊天視窗裡的隱藏
上下文。它會依 policy 召回過去 attempts、commits、notes、accepted facts
與 prior findings，再於 recall/run/review 當下即時 federate `CLAUDE.md`、
`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、`.cursor/rules`
等 live external sources。這些檔案仍是自己的 source of truth；AIT 不會自動
匯入。

## Agent-to-agent communication

AIT 給 agents 一條跟 Git 狀態綁在一起的本機 handoff channel：

1. 被 AIT 包住的 agent run 會形成 attempt，保留 prompt、output、changed
   files、commits、status 與 memory candidates。
2. 有用的事實、決策、失敗路線與 review findings 會留在 `.ait/`，或留在目前
   repo 的 live memory files 裡。
3. 下一次 wrapped run 會收到 `AIT_CONTEXT_FILE`：AIT 從 policy 允許的 prior
   attempts、accepted facts、notes、commits 與 live agent memory files 組出
   一份精簡 handoff。

這讓 agents 的溝通變成非同步、可檢查、可追溯。Claude 可以先調查，Codex
接著實作，Aider 做局部修補，Cursor 遵守 repo rules，另一個 reviewer agent
再挑戰結果；整個流程不依賴單一模型私有的聊天歷史。

## 使用起來像這樣

初始化一次：

```bash
ait init
direnv allow   # 只有被提示時才需要
```

確認目前 shell 真的會走進 AIT：

```bash
ait status claude-code
ait status codex
ait status --all
```

`Bypass detection: wrapped` 代表 agent 指令會解析到 repo-local AIT wrapper。
`Bypass detection: bypass_risk` 代表目前 shell 會直接呼叫真正的 agent binary，
AIT 抓不到 prompt、attempt 或失敗 evidence。重新啟用 shell integration、
執行 `direnv allow` 或 `ait repair`，再檢查一次 status。

接著照常使用你的 agent：

```bash
claude ...
codex ...
aider ...
gemini ...
cursor ...
```

Agent 執行完後，先看結果：

```bash
ait status
ait recover latest --debug   # 需要低階細節時才用
```

確認可以接受，再套用到目前 checkout：

```bash
ait apply latest
```

在 apply 之前，root checkout 保持不變。如果你的本地修改和 attempt 結果
重疊，AIT 會保守 hold，並留下 recovery handle；它不會自動 stash，也不會
覆蓋你手上的工作。

## 核心功能

| 功能 | 說明 |
| --- | --- |
| Worktree isolation | agent 的修改發生在 root checkout 之外；worktree 是 AIT 管理的內部細節 |
| Attempt provenance | command、status、output、changed files、commits 會被串成一筆紀錄 |
| Agent wrappers | repo-local 的 `claude`、`codex`、`aider`、`gemini`、`cursor` wrappers |
| Auto commit capture | 成功的修改會成為 attempt-linked commits；若 agent 已 commit，AIT 不會重複 commit |
| 共同記憶 | Claude Code、Codex 與其他 agents 可以共用同一份即時 repo-local context |
| 長期記憶 | 過去 attempts、commits、notes、accepted facts、findings 與明確 adopt 的 memory 可以跨 session 保留 |
| Adversarial review | 讓另一個 reviewer agent 主動挑戰 attempt，並保存 blocking findings |
| Review flow | 用 `apply`、`recover`、inspect、query 管理日常 attempt flow |

## 快速範例

指定 intent 與 commit message：

```bash
AIT_INTENT="Update README" \
AIT_COMMIT_MESSAGE="update README with Claude" \
claude -p --permission-mode bypassPermissions \
  "Shorten the README and improve the quickstart"
```

直接用 AIT 包住某個 command：

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
ait memory sources
ait memory search "auth adapter"
ait memory recall "billing retry"
ait memory backfill --dry-run
ait memory backfill --import
```

`ait memory sources` 與預設的 `ait memory recall` 都是 zero-touch read：
不建立 `.ait/`、不改來源檔，並即時讀取目前 repo-local agent memory。
`ait memory backfill --dry-run` 也是 zero-write preview。只有明確加上
`backfill --import` 時，AIT 才會把 advisory memory 寫進 `.ait/`；live recall
不需要 import。Global 或 repo 外部 memory 必須明確指定 `--global --path ...`。

Apply 前先跑對抗式審查：

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code \
  --review-budget standard

ait review finding list --severity high --format text
ait review report --attempt latest --format json
ait apply latest --mode current
```

修復本機 wrapper 設定：

```bash
ait repair
ait repair codex
```

## 整合

AIT 內建常見 AI coding agent 的 adapter。每個 adapter 都會包住原本的 CLI，
把執行放進隔離 worktree，並把 attempt 紀錄存在 repo 內的 `.ait/`。

`ait init` 會掃描 `$PATH` 上支援的 agent CLI 並完成設定：wrapper 放在
`.ait/bin/`，hook 設定合併到對應的 `.claude/`、`.codex/`、`.gemini/`
設定。下面範例都假設你已經跑過 `ait init`。若 agent 升級後需要重建設定，
可以執行：

```bash
ait adapter setup <name>
```

### 安全地執行 Claude Code

```bash
claude -p --permission-mode bypassPermissions "Refactor the auth module"
```

AIT 會把 prompt、變更檔案、執行狀態與 commits 記成一次 attempt。確認結果
後用 `ait apply latest` 套用；若想讓安全結果自動套用，可用
`ait run --apply auto ...`。

### 在真實 repo 裡安全地跑 Codex CLI

```bash
ait run --adapter codex --intent "Implement parser edge cases" -- codex
```

每個 Codex session 都在隔離環境裡編輯。失敗 attempt 會留下來供 recover；
只有 apply 過的 attempt 會碰到 root checkout。

### 在隔離環境中跑 Aider

```bash
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
```

Aider 產生的 commits 會被收進 attempt result，並保留 prompt、檔案與 commit
之間的對應關係。

### Gemini CLI 搭配 attempt 歷史

```bash
ait run --adapter gemini --intent "Add config validation" -- gemini
```

Gemini session 會和 Claude Code、Codex 一樣被記錄成 attempt。之後可以用
`ait memory recall` 查各 agent 嘗試過什麼。

### Cursor agent 搭配可審核 provenance

```bash
ait run --adapter cursor --intent "Migrate to new SDK" -- cursor
```

Cursor 的修改在 apply 前不會進入 root checkout。Attempt log 會保留變更檔案、
退出狀態與 commits，方便後續審核或 recover。

### 包裝其他 shell agent

```bash
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

用通用 `shell` adapter，就能替自訂 agent 或 script 加上 attempt provenance。

## 運作方式

```text
your prompt
    |
    v
agent CLI wrapped by ait
    |
    v
internal isolated workspace
    |
    v
attempt metadata + commits + memory
    |
    v
review、apply、recover 或 inspect
```

被 AIT 包住的 process 會收到：

```text
AIT_INTENT_ID
AIT_ATTEMPT_ID
AIT_WORKSPACE_REF
AIT_CONTEXT_FILE   # 啟用 context 時
```

`AIT_CONTEXT_FILE` 是一份精簡的 repo-local handoff，內容來自過去 attempts、
commits、curated notes、accepted facts、review findings，以及即時讀取的
`CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、
`.cursor/rules`。AIT 會記錄 context manifest，包含 source path、hash、
mtime、bytes used 與 policy status，但不會把外部檔案偽裝成 AIT captured
provenance。

## 安裝

推薦使用 `pipx`：

```bash
pipx install ait-vcs
ait --version
```

使用 virtual environment：

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --help
```

使用 npm wrapper：

```bash
npm install -g ait-vcs
ait --version
```

安裝指定 GitHub release：

```bash
pipx install "git+https://github.com/m24927605/ait.git@v0.55.63"
```

升級：

```bash
ait upgrade
ait --version
```

預覽升級：

```bash
ait upgrade --dry-run
```

## 常用指令

```bash
ait status
ait status claude-code
ait status codex
ait status --all
ait doctor
ait doctor --fix

ait adapter list
ait adapter doctor claude-code
ait adapter setup claude-code

ait attempt list
ait attempt show <attempt-id>
ait resume latest
ait intent show <intent-id>
ait context <intent-id>

ait memory
ait memory sources
ait memory search "auth adapter"
ait memory recall "billing retry"
ait memory backfill --dry-run
ait memory backfill --import
ait memory lint
ait memory lint --fix

ait graph
ait graph --html
```

Shell 自動啟用：

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

`ait` 目前是 `0.55.63`，仍屬 alpha quality。它適合 local dogfooding，
以及熟悉 Git workflow、願意早期試用的使用者。

Metadata 只存在單一 repo 的 `.ait/` 裡，不會跨機器同步。

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

- [Documentation site](https://m24927605.github.io/ait/) — 英文與繁體中文完整文件
- [為什麼用 ait](https://m24927605.github.io/ait/zh-TW/why-ait/) — AIT 解決的痛點
- [開始使用](https://m24927605.github.io/ait/zh-TW/getting-started/)
- [對抗式 code review](https://m24927605.github.io/ait/zh-TW/reference/adversarial-code-review/)
- [指令參考](https://m24927605.github.io/ait/zh-TW/reference/commands/)
- [Compare: naked git-worktree vs ait](https://m24927605.github.io/ait/compare/git-worktree-naked-vs-ait/)

內部設計筆記、規格與 refactor plan 請見 [`docs/`](docs/)。
