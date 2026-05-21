<div align="center">

# ait

### 一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來。

每一次 agent run 都是 `.ait/` 裡的 attempt：prompt、diff、審查結果、上一輪決定都查得到。

<sub>[English](README.md) · [繁體中文](README.zh-TW.md)</sub>

[![PyPI](https://img.shields.io/pypi/v/ait-vcs?label=PyPI)](https://pypi.org/project/ait-vcs/)
[![npm](https://img.shields.io/npm/v/ait-vcs?label=npm)](https://www.npmjs.com/package/ait-vcs)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

<p align="center">
  <img src="docs/assets/hero-cross-agent-handoff.gif" alt="Claude 把決定寫進 AGENTS.md，Codex 在沒讀過 AGENTS.md 的情況下把同一段 proof 字串寫進 handoff-proof.txt——handoff 經過 AIT" width="880">
</p>

<p align="center"><sub>Claude 收尾、Codex 接手，同一個 repo 兩個 agent 的 attempt 都留得下來。</sub></p>

---

多 agent 寫 code 真正卡住的，不是模型不夠強，而是：上一個 agent 學到的東西沒人接，寫程式的 agent 也是審自己的 agent，上禮拜定下來的決定關掉 chat tab 就不見了。

`ait` 把每一次 agent run 變成 `.ait/` 裡可查的 attempt——prompt、diff、findings、上一輪決定，CLI 一行就翻得出來。三件事，依序：多 agent 之間能交接、寫的人不能同時審自己、長期決定不會跟著 chat tab 一起消失。

```bash
pipx install ait-vcs      # 或: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor 用法一樣
ait status
ait apply latest
```

需要 Python 3.14+。

PyPI 與 npm 上的套件名稱是 `ait-vcs`，安裝後的指令是 `ait`。

---

## 三個痛點

順序固定：多 agent 交接 → 對抗式審查 → 共同 + 長期記憶。

### 痛點 1：同一個 repo，每個 agent 都從零開始（多 agent 之間能交接）

**場景。** 昨天 Claude 追了一整晚 billing-retry 的 429。今天早上 Codex 打開同一個 repo，從頭再查一次。中間沒有任何交接。

**AIT 怎麼化解。** 每一次被包住的 agent run 都會在 `.ait/` 裡留下一筆 attempt。下一次跑 agent——Codex、Aider、Gemini、Cursor，任何能被 `ait run --adapter <name>` ([`src/ait/cli/run.py`](src/ait/cli/run.py)) 包住的 CLI——都會收到一份 `AIT_CONTEXT_FILE`，內容由 [`src/ait/context_manifest.py`](src/ait/context_manifest.py) 從過去 attempts 與 notes 組出來：prompt、diff、findings、決定。非同步、有 evidence。要看交接軌跡：

```bash
ait query --on attempt 'agent.agent_id="codex:main"'
```

**證據。** [`examples/pain-point-demos/07-cross-agent-handoff/`](examples/pain-point-demos/07-cross-agent-handoff/) — Codex 透過 `AIT_CONTEXT_FILE` 直接接到上一個 agent 的脈絡。

### 痛點 2：寫程式的 agent 就是審自己的那個 agent（對抗式審查）

**場景。** Codex 跑完，回一句「所有測試都過了」。寫的 agent 跟審的 agent 是同一個模型、同一個 chat、同一個 prompt。

**AIT 怎麼化解。** 換一個 agent、換一個 prompt，對 attempt 的 diff 跑一次審查。實作在 [`src/ait/cli/review.py`](src/ait/cli/review.py)：

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code
```

審查的 agent 看不到實作 agent 的 chat。Findings 是可查詢的 row：

```bash
ait query --on attempt 'review.status="blocked"'
ait review finding list --severity high --format text
```

高嚴重度的 finding 會擋住 `ait apply`。

**證據。** [`examples/pain-point-demos/09-1-codex-reviewer/`](examples/pain-point-demos/09-1-codex-reviewer/) — Claude 寫，Codex 審，blocking finding 在 apply 前就被記下來。

### 痛點 3：上禮拜的決定關進 chat tab，再也撈不回來（共同 + 長期記憶）

**場景。** 三週前你把 retry budget 訂在三次。Chat tab 已經關了。今天的 agent 提議改回五次。

**AIT 怎麼化解。** `.ait/` 留住每一次 attempt——prompt、intent、output、檔案、commit、findings——同時也讀現場的 `CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、`.cursor/rules`。要召回，CLI 一行：

```bash
ait memory recall "retry budget"
```

實作在 [`src/ait/memory/recall.py`](src/ait/memory/recall.py)。`ait memory recall <query>` 在過去 attempts、accepted facts、notes 裡搜尋——抓不抓得到由你判斷。本機、單機，跨所有被包住的 agent 共用。

**證據。** [`examples/pain-point-demos/04-memory-reuse/`](examples/pain-point-demos/04-memory-reuse/) — 上一輪的決定透過 `ait memory recall` 送到下一個 agent 手上。

---

## 跟你現在在用的工具差在哪

AIT 包在你已經在用的 agent CLI 外面。它不是 Cursor 的競品、不是 Aider 的替代品、也不是 IDE plugin。

| 工具 | 它做的事 | AIT 補上的事 |
|---|---|---|
| **Aider** | 行內編輯加 auto-commit loop，單一模型，每個 run 一份 chat。 | 對同一個 attempt 跑另一個 reviewer agent（`ait review attempt --mode adversarial`、[`src/ait/cli/review.py`](src/ait/cli/review.py)）。Aider 的 commit 會落在 AIT attempt 內；apply 仍是明確動作。多 agent 之間的交接走 `AIT_CONTEXT_FILE`（[`src/ait/context_manifest.py`](src/ait/context_manifest.py)）。 |
| **Cursor** | IDE 內建的 agent、編輯器內 diff review、agent mode 平行任務。 | CLI 為主的 attempt ledger，跨非 Cursor agent 都通（`ait attempt list`、`src/ait/cli/attempt.py`）。沒有 SaaS 來回；`.ait/` 留在本機，daemon 只走 Unix socket（`src/ait/daemon_transport.py`）。 |
| **Cline** | VSCode extension，包 Claude/OpenAI 在編輯器內做 agentic edit。 | 包的是你已經在用的 agent CLI，不需要編輯器（`ait run --adapter claude-code`、[`src/ait/cli/run.py`](src/ait/cli/run.py)）。Findings 與 prompt 是可查詢的 row（`ait query`、`src/ait/query/`）。 |
| **Continue.dev** | IDE 自動補全、chat、model routing、rule files。 | 可審查的 attempt，不是 keystroke 級的自動補全（`ait apply` / `ait recover`）。Review gate：`ait review finding list --severity high`。 |

AIT 不做的事：

- 沒有 IDE plugin。只有 CLI。
- 沒有自動補全。Attempt 為單位，不是 keystroke 為單位。
- 沒有跨機器同步。`.ait/` 是單一 repo、單一機器。
- 沒有發出 benchmark 數字證明 reviewer 抓得到 implementer 漏掉的 bug。Dogfood report 在 [`docs/aitbench-dogfood-report.md`](docs/aitbench-dogfood-report.md)；品質宣稱不做。

---

## 日常用起來像這樣

初始化一次：

```bash
ait init
direnv allow   # 只有被提示時才需要
```

確認目前 shell 真的會走進 AIT wrapper：

```bash
ait status claude-code
ait status --all
```

`wrapped` 代表 agent 指令會解析到 repo-local wrapper。`bypass_risk` 代表會直接呼叫真正的 agent binary，AIT 抓不到 prompt 或 diff。重新啟用 shell integration、跑 `direnv allow`、或 `ait repair`，再查一次。

接著照常使用你的 agent：

```bash
claude ...
codex ...
aider src/auth.py
gemini ...
cursor ...
```

agent 跑完之後：

```bash
ait status
ait recover latest --debug   # 需要低階細節再用
ait apply latest             # 確認可以接受才 apply
```

在你執行 `ait apply` 之前，root checkout 不會動。本地修改和 attempt 結果重疊時，AIT 會保守 hold 並留下 recovery handle；不會自動 stash，也不會覆蓋你手上的工作。

---

## 安裝

```bash
pipx install ait-vcs
ait --version
```

npm 路線：

```bash
npm install -g ait-vcs
ait --version
```

指定 GitHub release：

```bash
pipx install "git+https://github.com/m24927605/ait.git@v1.0.0"
```

升級：

```bash
ait upgrade
ait upgrade --dry-run   # 只看計畫
```

需求：Python 3.14+、Git、stdlib SQLite；走 npm 時還需要 Node.js 18+。

---

## 常用指令

```bash
ait status
ait doctor
ait doctor --fix

ait adapter list
ait adapter setup claude-code

ait attempt list
ait attempt show <attempt-id>

ait memory
ait memory sources --format json
ait memory recall "billing retry"
ait memory search "auth adapter"

ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait review finding list --severity high --format text

ait query --on attempt 'agent.agent_id="codex:main"'
ait graph
ait graph --html
```

Shell 啟用：

```bash
ait shell show --shell zsh
ait shell install --shell zsh
```

完整列表在 [指令參考](https://m24927605.github.io/ait/zh-TW/reference/commands/)。

---

## 狀態

alpha

alpha quality，每天在真實 repo 上 dogfood，metadata 單機限定。

Metadata 只存在單一 repo 的 `.ait/`，不跨機器同步。沒有 SaaS dashboard、沒有 telemetry、沒有自動 push 或自動 merge。Browser console 仍是 read-only；apply、recover、discard 的真實動作仍走既有 CLI path。Metadata export/import 只支援 dry-run planning。`.ait/policy.json` validation fail closed，並已被 apply、review、console preflight、context trust filtering 實際使用。

---

## 文件

- [Documentation site](https://m24927605.github.io/ait/) — 英文與繁體中文完整文件
- [為什麼用 ait](https://m24927605.github.io/ait/zh-TW/why-ait/)
- [開始使用](https://m24927605.github.io/ait/zh-TW/getting-started/)
- [對抗式 code review](https://m24927605.github.io/ait/zh-TW/reference/adversarial-code-review/)
- [指令參考](https://m24927605.github.io/ait/zh-TW/reference/commands/)
- [CHANGELOG](CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)

內部設計筆記、規格、refactor plan 都放在 [`docs/`](docs/)。
