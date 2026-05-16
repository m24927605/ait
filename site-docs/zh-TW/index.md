---
title: ait — AI coding agents 的本機 control plane
description: >-
  ait 是給 Claude Code、Codex、Aider、Gemini CLI、Cursor 使用的本機
  control plane 與 Git-native attempt ledger：repo-local memory、跨 agent
  handoff、對抗式審查，以及明確 apply/recover。開源、零依賴、no SaaS、
  no telemetry。
---

# ait

**AI coding agents 的本機 control plane。Git-native attempt ledger、
repo-local memory、跨 agent handoff 與 review gate。**

`ait` 包住你已經在用的 agent CLI——Claude Code、Codex、Aider、Gemini
CLI、Cursor——把每次執行變成一筆**可審核的 attempt**。Agent 編輯獨立
的 Git worktree，`ait` 紀錄發生過什麼；同時提供共同 repo-local memory、
長期 attempt history、可檢查的 handoff channel，以及 apply 前的對抗式審查。
你的 root checkout 在你親手 apply 之前不會被動到。

更硬的產品分類是：**AI coding agents 的本機 control plane**。AIT 不只是
worktree manager，不只是 memory layer，不只是 review bot，也不是 SaaS
provenance dashboard。這些都是同一個 local attempt ledger 的不同面向：
agent 在 attempt 裡工作，memory 來自可追溯 evidence，review finding 可以
擋住 apply，而 Git 仍是 source of truth。
若要看類別邊界，請看 AIT 對比
[GUI-first agent managers、worktree managers、memory layers、review bots 與
provenance tools](compare/agent-managers-memory-review-vs-ait.md)。

```text
Claude 先調查 -> AIT 記錄 attempt 與 accepted context
Codex 透過 AIT_CONTEXT_FILE 接手實作
Reviewer agent 挑戰結果
證據足夠時，你才執行 ait apply
```

最該先注意的四個特色：

- **共同 repo memory。** Claude Code、Codex、Aider、Gemini、Cursor 與 shell
  agents 可以讀同一份 policy 允許的專案脈絡。
- **長期記憶。** 有用的 attempts、commits、notes、accepted facts 與 findings
  可以跨 terminal、跨 session、跨週期保留下來。
- **Agent-to-agent communication。** 一個 agent 的調查、決策、失敗路線或
  review finding，可以透過 `AIT_CONTEXT_FILE` 傳給下一個 agent。
- **對抗式審查。** 另一個 reviewer agent 可以挑戰 attempt、留下 evidence，
  讓你在 apply 前有獨立判斷依據。

```bash
pipx install ait-vcs    # 或用 npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

PyPI 與 npm 上的套件名是 `ait-vcs`，安裝後的指令是 `ait`。

![AIT Work Graph：attempts、evidence、memory、hot files 與 query filters](../assets/ait-work-graph.png)

_`ait graph --html` 產生的本機 HTML 報告：attempts、evidence、memory、hot files 與 query filters 集中在同一張圖裡。_

## 核心特色

| 特色 | 說明 |
| --- | --- |
| Git-native attempt ledger | 每次 agent run 都會成為可查詢 attempt，串起 intent、prompt、context、output、files、commits、memory 與 review evidence。 |
| Live federated memory | Claude Code、Codex、Aider、Gemini、Cursor 與 shell agents 可以共用同一份即時 repo memory：AIT-owned history 加上目前的 `CLAUDE.md`、`AGENTS.md`、`.claude/`、`.codex/` 與 Cursor rules。 |
| 長期 repo memory | attempts、commits、notes、accepted facts、prior findings，以及明確 adopt 的 memory 可以跨 session 保留。 |
| Agent-to-agent communication | 一個 agent 的調查、決策、失敗路線或 review finding，可以透過 `AIT_CONTEXT_FILE` 傳給後續另一個 agent。 |
| 對抗式審查 | 另一個 reviewer agent 可以挑戰 attempt、記錄 findings，並對高風險結果 hold apply。 |
| Attempt-first 工作流 | 包住你已經在用的 agent CLI，先把每次執行變成隔離 attempt，再由你決定是否 apply 到 root checkout。 |
| Attempt provenance | prompt、intent、adapter、output、changed files、commits、trace references、status、outcome 會串成一筆紀錄。 |
| Worktree 隔離 | 每次執行都有自己的內部 Git worktree，失敗或高風險 attempt 不會污染目前 workspace。 |
| 平行 agent attempts | 多個 agents 可以同時試不同做法，不會在同一個 checkout 裡互相覆蓋。 |
| 明確 apply/recover 流程 | Agent 產出的結果在 apply 前只是提案；held 或 failed work 仍可 recover。 |
| Wrapper bypass 偵測 | `ait status <adapter>` 會告訴你目前 shell 會進 AIT wrapper，還是會 silent 地直接呼叫真正的 agent binary。 |
| Local-first metadata | metadata 存在 `.ait/`；不需要 SaaS dashboard、不做 telemetry、不要求上傳原始碼。 |
| 可查詢歷史 | attempts、intents、files、agents、statuses、review results、舊 prompts 都可以用 AIT 指令查。 |

## 為什麼用 ait

| 用 AI agent 寫程式的痛點 | ait 提供的解法 | 可執行範例 |
| --- | --- | --- |
| 一個不精準的 prompt 在你發現前就改了半個 repo | 每次執行都在隔離 Git worktree 裡進行，root checkout 不會被直接修改 | [`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius) |
| diff 看得出改了什麼，卻看不出怎麼來的 | attempt 會串起 intent、command output、changed files 與 commits | [`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance) |
| 失敗或半成品污染 working copy | 失敗 attempt 保留在隔離 worktree，主 checkout 維持乾淨，可用 `ait recover latest` 查看 | [`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation) |
| 換一個 agent 接手，又從頭調查同一件事 | 共同 repo-local memory 會把過去 attempts、commits、notes、accepted facts 餵給後續執行 | [`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse) |
| Claude 和 Codex 同時跑會互相覆蓋 | 每個 attempt 都有自己的 worktree，可以平行跑多個 agent 再比較結果 | [`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents) |
| Agent 說「修好了」，但你不確定該不該採用 | `ait apply latest` 是明確動作；沒有 apply 前，agent 的成果只是提案 | [`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion) |
| 跨 agent hand-off 會弄丟之前所有的決策 | Live repo memory 會把目前的 agent memory files、過往 attempts、notes 與已接受決策組成同一份 context | [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) |
| provenance 工具要求把原始碼送到 SaaS | metadata 留在 repo 內的 `.ait/`；daemon 只走本機 Unix socket，沒有 telemetry | [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance) |
| 實作 agent 自己審自己，容易放過盲點 | 可交給另一個 reviewer agent 做對抗式審查，高風險 finding 可以擋下 apply | [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence)、[`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) |
| 想找上個月那段 prompt，只能 grep shell history | 用結構化 DSL 查 attempts、intents、commits、agent、狀態與變更檔案 | [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search) |

完整深入的解析請看 [為什麼用 ait](why-ait.md)。
每個痛點的可重跑證據請看 [痛點 demo](demos/pain-point-demos.md)。

`ait` **不是**另一個 agent。它是包在你信任的 agents 外面的本機 attempt
工作流。

## Agents 如何互相溝通

AIT 的溝通是非同步、可檢查的。每個 wrapped run 都會形成 attempt，保留
prompt、output、changed files、commits、status 與 memory candidates。
後續 run 會收到 `AIT_CONTEXT_FILE`：AIT 從 policy 允許的 attempts、
accepted facts、notes、commits、review findings，以及 live memory files
組出精簡 handoff，例如 `CLAUDE.md`、`AGENTS.md`、`.claude/memory.md`、
`.codex/memory.md`、`.cursor/rules`。

這不是隱藏聊天紀錄，不是外部 vector database，也不是 `CLAUDE.md`
generator；它是 attempt-derived、evidence-backed repo memory：可以檢查、
搜尋、審查，也能依 Git 狀態決定保留或丟棄。

## 支援的 agent

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [其他 shell agent](integrations/shell.md)

## Review 與 memory 邊界

`ait review attempt --mode light` 是 deterministic risk scan。它會檢查
變更檔案數、敏感路徑、dependency 或 lockfile、generated/binary 檔案、
以及是否缺少 test evidence。它不會呼叫 LLM，也不會產生逐行 finding。

需要真正的 reviewer adapter 時，用 `adversarial` mode：

```bash
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
```

內建 `claude-code` reviewer 會呼叫本機 `claude -p` CLI，並從該子行程
環境移除 `ANTHROPIC_API_KEY`。AIT 不會 silent fallback 到 provider API
credits；你的機器上必須已安裝 Claude Code 並完成本機登入。

Repo-local memory 是同一個 repository 內的 live federated view。AIT 會在
`.ait/` 記錄 attempts、commits、notes、accepted memory facts、prior findings
與 review findings，並在 recall/run/review 當下即時讀取目前的 `CLAUDE.md`、
`AGENTS.md`、`.claude/memory.md`、`.codex/memory.md`、`.cursor/rules`。
這是可檢查的專案記憶，不是某個聊天視窗裡的隱藏上下文。

既有專案中途導入 AIT 時，先跑 `ait memory sources` 或 `ait memory recall`。
兩者預設都是 zero-touch read：不建立 `.ait/`，也不改來源檔。
`ait memory backfill --dry-run` 仍是 zero-write preview。只有明確加上
`backfill --import` 時，AIT 才會把 advisory memory 寫進 `.ait/`。

對抗式審查的細節請看 [對抗式 code review](reference/adversarial-code-review.md)：reviewer adapter、findings、report，以及 review-gated apply。

## 狀態

`ait` 仍屬 alpha quality，適合本機 dogfooding、power users，以及熟悉 Git
workflow、偏 infra-minded 的早期使用者。Metadata 是 repo-local 的（存在
`.ait/`），不會跨機器同步。

AIT 的視覺模型已開始可用：`ait graph --html` 仍是本機靜態報告，
`ait console --read-only` 則會用同一份 attempt graph、evidence、memory、
hot files 與 review results 產生或 loopback-only serve 一個 read-only daily
console。CLI action dry-run layer 目前可以記錄 apply/recover/discard 的
preflight 與 append-only journal，但 browser mutation UI 與 action execution
尚未啟用；真實 apply/recover/discard 仍必須走既有 CLI/domain paths。

Team-readiness hardening 仍是 local-only：`.ait/policy.json` validation 會
fail closed，且目前已被 apply、review、console action preflight 與 context
trust filtering 實際使用。Metadata export/import 目前只輸出 dry-run plans。
仍然沒有 cross-machine sync、SaaS dashboard、telemetry、自動 push 或自動
merge。

## 產品解法方向

| 目前限制 | 解法 |
| --- | --- |
| 類別容易被分散理解成好幾種工具 | 主定位固定為本機 control plane 與 Git-native attempt ledger；memory、review、provenance、apply/recover 都是 ledger 的不同面向。 |
| CLI-first 體驗會輸給視覺化 agent managers | Console 先維持 read-only；在 browser mutation UI 前，先硬化 apply/recover/discard dry-run preflight 與 journal。 |
| Alpha quality 限制一般團隊 adoption | 先服務 local power users 與 infra-minded engineers；先提供 dry-run metadata export/import 與 fail-closed policy validation，再談更廣的 sync。 |
| Memory 容易被誤解成 prompt stuffing | 堅持 attempt-derived、evidence-backed、可檢查、與 Git 狀態綁定的 memory。 |
| Review gate 效果需要量化 | 10-case benchmark fixture 與修復後的 Claude/Codex dogfood artifacts 已存在。持續發布誠實 repeated runs，直到 recall、false positives、latency、token cost，以及 deterministic review 與 LLM review 的取捨足夠穩定，才能做品質宣稱。 |

## 專案連結

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI 套件](https://pypi.org/project/ait-vcs/)
- [npm 套件](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
