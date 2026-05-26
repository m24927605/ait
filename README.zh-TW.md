# ait

**ait 是 AI coding agent 的本機 attempt ledger。**

它會把每次 AI coding run 記下來，讓下一個 agent 可以審查、接手，或在失敗後
復原。

<p>
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a>
</p>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

你照常使用 Claude Code、Codex、Aider、Gemini CLI、Cursor CLI，或其他你已經在
用的 agent。`ait` 會包住這次執行，把 prompt、diff、review、decision 存成
repo 內 `.ait/` 底下的一筆 attempt，下一個 agent 就能接到前一次留下的脈絡。
你也可以讓另一個 agent 先審查這次修改，再決定要不要套用。只要你還沒明確
執行 `ait apply`，被 `ait` 包住的執行結果就不應該進到 root checkout。

套件名稱是 `ait-vcs`，安裝後的指令是 `ait`。

## 為什麼需要它

AI coding agent 很會改程式，但改程式旁邊的流程常常很脆弱：

- 下一個 agent 通常從零開始，因為上一個 agent 的脈絡留在已關閉的 chat 裡。
- 寫程式的 agent 往往也是唯一「審查」那段程式的 agent。
- 失敗或中斷的執行可能在 working copy 留下一堆難清的狀態。
- 上週做過的重要決定，今天很難從 shell history 或聊天紀錄找回來。

`ait` 把每次 run 當成一筆 attempt：它是一個有來源紀錄、有審查狀態、有記憶，
而且必須明確 apply 才會落地的提案。

## 誰需要它

`ait` 適合已經在真實 repo 上使用 AI coding agent 的工程師，而且你希望每次
agent 做了什麼都能留在本機。特別是這些情境：

- 你會在 Claude Code、Codex、Aider、Gemini CLI、Cursor CLI 或其他 agent CLI
  之間切換。
- 你希望高風險修改在落地前，先交給第二個 agent 審查。
- 你需要從失敗或中斷的 run 裡復原有用的工作。
- 你希望舊 prompt、decision、finding 可以從 repo 裡查回來。

## 30 秒 quickstart

不用真實 API key，也不用拿現有 repo 冒險：

```bash
pipx install ait-vcs
ait demo
```

`ait demo` 會建立一個暫存 repo，跑一段 scripted multi-agent walkthrough，
把 attempts 寫進真正的本機 SQLite ledger，並示範 review gate 擋下一個高風險
修改。清掉 demo：

```bash
ait demo --clean
```

在真實 repo 使用：

```bash
cd your-repo
ait init
ait status --all # 可選：確認 agent 指令會經過 ait
claude ...        # codex / aider / gemini / cursor 用法一樣
ait status
ait apply latest
```

需求是 Python 3.14+ 與 Git。如果系統預設 Python 太舊：

```bash
pipx install --python python3.14 ait-vcs
```

## 用起來是什麼感覺

1. 在 repo 裡跑一次 `ait init`。
2. 需要確認 wrapper 時，跑 `ait status claude-code` 或 `ait status --all`。
3. 照常使用你的 agent：`claude ...`、`codex ...`、`aider ...`。
4. `ait` 把這次執行記成 `.ait/` 底下的一筆隔離 attempt。
5. 用 `ait status` 或 `ait attempt show <attempt-id>` 看它做了什麼。
6. 需要時，叫另一個 agent 先審查。
7. 最後選擇 apply、recover、resume，或 discard。

最重要的行為是：在你執行 `ait apply` 之前，被包住的 run 不應該改動 root
checkout。Agent 的結果先是提案，不是事實。

## 核心概念

**Attempt**

一筆被 `ait` 記下來的 agent run：prompt、intent、exit status、改過的檔案、
diff、commit、trace、review state。

```bash
ait attempt list
ait attempt show <attempt-id>
```

**Repo-local ledger**

`.ait/` 放在 `.git/` 旁邊，是這個 repo 的本機 metadata。沒有 SaaS，沒有
telemetry，也不會自動同步。除非你自己複製、commit、export 或上傳，`.ait/`
裡的資料不會離開你的機器。你實際呼叫的 agent CLI 仍然會依照它自己的 provider
與網路規則運作。

**明確 apply**

被包住的 agent run 會先落在隔離 workspace。`ait apply latest` 是你決定讓這
筆 attempt 影響 root checkout 的那一步。

```bash
ait apply latest
ait recover latest
ait resume latest
```

**Cross-agent handoff**

下一個被包住的 agent 可以收到先前 attempts、accepted facts、notes，以及
`CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、
`.cursor/rules` 這類現場 memory 檔。

**對抗式審查**

一個 agent 實作，另一個 agent 在 apply 前挑戰它。這不代表程式一定正確；它
提供的是另一個 prompt、另一個 agent、另一份被記錄下來的審查結果。

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code
```

**Memory recall**

當舊決定又變重要時，可以搜尋過去 attempts 與 repo memory：

```bash
ait memory recall "retry budget"
```

## 常見 workflow

**記錄一次正常 agent run**

```bash
ait init
claude -p "Refactor the auth retry logic"
ait status
ait attempt list
ait attempt show <attempt-id>
```

**用另一個 agent 審查**

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter codex

ait review finding list --severity high
```

**接回中斷或被 hold 的 run**

```bash
ait recover latest
ait resume latest
```

**找回以前的決定**

```bash
ait memory recall "why retry budget is three"
ait query --on attempt 'title~"retry"'
```

**比較多個 attempts**

```bash
ait attempt list
ait attempt show <attempt-id>
ait graph --html
```

## 跟 Cursor、Aider、Claude Code、Codex、Cline 差在哪

`ait` 不是另一個 coding agent。它是包在你現有 agent 外面的本機 workflow
layer。

| 工具 | 主要工作 | `ait` 補上的事 |
| --- | --- | --- |
| Cursor / Cline | IDE 裡的 agent 體驗。 | CLI 優先的 attempt ledger；不只在編輯器裡，也能跨多個 agent CLI 使用。 |
| Claude Code / Codex / Gemini CLI | 讀程式、改程式、跑指令的 coding agent。 | 隔離執行、來源紀錄、跨 agent 交接、審查紀錄、memory recall，以及明確的 apply/recover。 |
| Aider | 和模型一起 pair programming，讓模型直接編輯與 commit。 | 在這些修改外面加上一層 repo-local attempt 邊界，並可在 apply 前交給另一個 agent 審查。 |
| 單純 Git worktree | 用多個目錄隔離平行工作。 | 額外記錄 prompt、trace、attempt metadata、review findings、memory handoff，並提供日常 apply/recover 指令。 |

簡短說：你的 agent 負責寫程式；`ait` 負責記住發生了什麼，並讓結果在落地前可
審查、可復原。

## 什麼情境下不該用 ait

如果你需要的是下面這些，`ait` 不適合：

- IDE plugin 或 autocomplete engine。
- Hosted dashboard、team sync service，或跨機器共享的 ledger。
- 已 production hardening、長期 storage contract 穩定的系統。
- 證明 AI reviewer 一定找得到所有缺陷。
- 取代 Claude Code、Codex、Aider、Cursor、Cline 或 Git 的工具。

`ait` 最適合已經在用 agent CLI 的工程師：你想要本機 provenance、比較安全的
apply、跨 agent handoff，以及讓第二個 agent 先審一次。

## 安裝

建議使用 pipx：

```bash
pipx install ait-vcs
ait --version
```

npm wrapper：

```bash
npm install -g ait-vcs
ait --version
```

專案虛擬環境：

```bash
python3.14 -m venv .venv
.venv/bin/pip install ait-vcs
.venv/bin/ait --version
```

固定 GitHub release：

```bash
pipx install "git+https://github.com/m24927605/ait.git@v1.4.1"
```

升級：

```bash
ait upgrade
ait upgrade --dry-run
```

需求：Python 3.14+、Git、Python 標準庫內建的 SQLite。npm 套件需要 Node.js
18+，並會在 `ait` 指令背後安裝 Python package。

## 目前狀態與限制

`ait` 還是 alpha software。

- Local-first：metadata 存在單一 repo、單一機器的 `.ait/` 底下。
- 沒有 telemetry、沒有 SaaS dashboard、沒有自動 push、沒有自動 merge。
- Browser/HTML report 是本機產物；真正會改狀態的動作仍然走 CLI。
- Metadata export/import 目前是 dry-run planning path，不是同步功能。
- 對抗式審查是一道額外安全檢查，不是正確性證明。
- Memory recall 很有用，但最後仍由你判斷哪段脈絡該採用。

## 文件與範例

- [Documentation site](https://m24927605.github.io/ait/)
- [開始使用](https://m24927605.github.io/ait/zh-TW/getting-started/)
- [指令參考](https://m24927605.github.io/ait/zh-TW/reference/commands/)
- [對抗式 code review](https://m24927605.github.io/ait/zh-TW/reference/adversarial-code-review/)
- [痛點 demos](https://m24927605.github.io/ait/zh-TW/demos/pain-point-demos/)
- [Review benchmark dogfood report](docs/review-benchmark-dogfood-report.md)
- [Examples](examples/)
- [CHANGELOG](CHANGELOG.md)
- [PyPI](https://pypi.org/project/ait-vcs/) · [npm](https://www.npmjs.com/package/ait-vcs)

MIT licensed.
