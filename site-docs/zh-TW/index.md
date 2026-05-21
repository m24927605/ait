---
title: ait — 一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來
description: >-
  ait 包住 Claude Code、Codex、Aider、Gemini CLI、Cursor：一個 agent 把
  決定傳給下一個 agent；另一個 agent 用不同 prompt 審 diff；過去的 attempt
  與決定可以從 CLI 查得到。
---

# 一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來。

每一次 agent run 都是 `.ait/` 裡的 attempt：prompt、diff、審查結果、上一輪
決定都查得到。

`ait` 把你已經在用的 agent CLI 包起來。下一個 agent 開檔案就讀得到前一個
agent 留下的決定。另一個 reviewer agent 用不同 prompt 對著 attempt 的 diff
跑審查。Memory 是 `.ait/` 加上即時讀到的 `CLAUDE.md` / `AGENTS.md`，可以
用 CLI 搜。

```bash
pipx install ait-vcs      # 或: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor 用法一樣
ait status
ait apply latest
```

需要 Python 3.14+。系統 Python 較舊時，請改用
`pipx install --python python3.14 ait-vcs`。

PyPI 與 npm 的套件名是 `ait-vcs`，指令是 `ait`。

## AIT 在你已經用的工具上多做什麼

| 工具 | 它做的事 | AIT 補的部分 |
| --- | --- | --- |
| **Aider** | In-process 編輯加自動 commit，單一 model、單一 chat。 | 用另一個 reviewer agent 對同一個 attempt 做審查（`ait review attempt --mode adversarial`，`src/ait/cli/review.py`）。Aider 的 commit 落在 attempt 裡，apply 仍是明確動作。下一個 agent 透過 handoff 檔案（`src/ait/context_manifest.py`）收到前一個 agent 的決定。 |
| **Cursor** | IDE 內嵌 agent、編輯器內 diff 審查、agent 模式可平行任務。 | CLI 優先的 attempt 記錄，涵蓋非 Cursor 的 agent（`ait attempt list`，`src/ait/cli/attempt.py`）。資料不離開你的機器；daemon 走本機 Unix socket（`src/ait/daemon_transport.py`）。 |
| **Cline** | VSCode extension，包 Claude / OpenAI 做編輯器內 agentic 編輯。 | 包住你本來在用的 agent CLI，不需要編輯器（`ait run --adapter claude-code`，`src/ait/cli/run.py`）。Prompt 與 finding 都是可查詢的列（`ait query`，`src/ait/query/`）。 |
| **Continue.dev** | IDE autocomplete 加 chat，含 model routing 與規則檔。 | 是可審查的 attempt，不是 autocomplete。Apply 是明確動作（`ait apply` / `ait recover`）。Review gate 可以擋下 apply（`ait review finding list --severity high`）。 |
| **不適合 AIT 的情境** | 你要 IDE plugin、autocomplete、跨機器同步，或穩定的 production 工具。 | AIT 只有 CLI、以 attempt 為單位、單機、alpha。Console 是 read-only；`.ait/` 不會跨機器同步。 |

## 三個主軸

### 一個 agent 把工作交給下一個

昨天 Claude 追了一個 billing-retry 429 的 bug。今天 Codex 打開同一個 repo。
沒有 AIT 時 Codex 從零開始；有 AIT 時，下一個 run——Claude、Codex、Aider、
Gemini、Cursor，只要是用 `ait run --adapter <name>`（`src/ait/cli/run.py`）
包起來的——會收到 handoff 檔案，內容由先前的 attempt 與 note 組成。Handoff
是非同步、單向、有證據的：prompt、diff、finding、decision。

證據：[`examples/pain-point-demos/07-cross-agent-handoff/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff)

### 另一個 agent 審 diff

Codex 跑完說「all tests pass」。寫程式的 agent 和審查的 agent 是同一個
model、同一段對話、同一份 prompt。AIT 用不同 prompt、另一個 agent 來審：

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

Reviewer 看不到 implementer 的對話。Finding 是可查的列（`ait query --on
attempt 'review.status="blocked"'`）；高嚴重度的 finding 會擋下 `ait apply`。

證據：[`examples/pain-point-demos/09-1-codex-reviewer/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer)

### Repo 記得過去的決定

三週前你把 retry budget 訂在 3 次，那個 chat tab 早就關了。今天有 agent
提議 5 次。`.ait/` 留著每一個 attempt——prompt、intent、output、檔案、
commit、finding——並即時讀取 `CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、
`.codex/memory.md`、`.cursor/rules`。Recall 是一個 CLI 查詢：

```bash
ait memory recall "retry budget"
```

`src/ait/memory/recall.py` 會搜過去的 attempt、accepted fact 與 note，由你
判斷哪一筆是這次需要的。

證據：[`examples/pain-point-demos/04-memory-reuse/`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse)

## 用一週之後的樣子

![AIT Work Graph：attempts、evidence、memory、hot files 與 query filters](../assets/ait-work-graph.png)

_`ait graph --html` 產生的本機 HTML 報告：attempts、evidence、memory、
hot files、query filters 都在同一張圖。_

## 狀態

Alpha。每天在真實 repo 上 dogfood。Metadata 只留在這台機器上，存在 `.ait/`。
沒有跨機器同步、沒有 SaaS、沒有 telemetry。詳細邊界看
[為什麼用 ait](why-ait.md) 的「不適合 AIT 的情境」。

## 專案連結

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI 套件](https://pypi.org/project/ait-vcs/)
- [npm 套件](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
