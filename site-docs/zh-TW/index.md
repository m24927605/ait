---
title: ait — AI agent 的可審核 attempts
description: >-
  ait 把 Claude Code、Codex、Aider、Gemini CLI、Cursor 的每次執行變成
  隔離、可審核的 attempt，保留 provenance、repo-local memory、跨 agent
  handoff、對抗式審查與明確 apply/recover 流程。開源、零依賴、no SaaS、
  no telemetry。
---

# ait

**AI agent 應該在 attempt 裡動手，不是直接碰你的 working tree。**

`ait` 包住你已經在用的 agent CLI——Claude Code、Codex、Aider、Gemini
CLI、Cursor——把每次執行變成一筆**可審核的 attempt**。Agent 編輯獨立
的 Git worktree，`ait` 紀錄發生過什麼，你的 root checkout 在你親手
apply 之前不會被動到。AIT 會把 prompt、diff、commits、repo-local memory
與 review evidence 留在一起，讓你先比較、再決定哪些結果可以落地。對高風險
變更，AIT 也能在 apply 前執行對抗式審查。

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
| Attempt-first 工作流 | 包住你已經在用的 agent CLI，先把每次執行變成隔離 attempt，再由你決定是否 apply 到 root checkout。 |
| Worktree 隔離 | 每次執行都有自己的內部 Git worktree，失敗或高風險 attempt 不會污染目前 workspace。 |
| Attempt provenance | prompt、intent、adapter、output、changed files、commits、trace references、status、outcome 會串成一筆紀錄。 |
| 跨 agent 共同記憶 | Claude Code、Codex、Aider、Gemini、Cursor 與 shell agents 可以共用同一份 repo-local context。 |
| 長期 repo memory | attempts、commits、notes、匯入的 `CLAUDE.md` / `AGENTS.md`、accepted facts、prior findings 可以跨 session 保留。 |
| 跨 agent handoff | 一個 agent 的調查或決策，可以透過 AIT 傳給後續另一個 agent。 |
| 平行 agent attempts | 多個 agents 可以同時試不同做法，不會在同一個 checkout 裡互相覆蓋。 |
| 明確 apply/recover 流程 | Agent 產出的結果在 apply 前只是提案；held 或 failed work 仍可 recover。 |
| 對抗式審查 | 另一個 reviewer agent 可以挑戰 attempt、記錄 findings，並對高風險結果 hold apply。 |
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
| 跨 agent hand-off 會弄丟之前所有的決策 | 長期記憶可保存 `CLAUDE.md`、`AGENTS.md`、過往 attempts、notes 與已接受決策 | [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) |
| provenance 工具要求把原始碼送到 SaaS | metadata 留在 repo 內的 `.ait/`；daemon 只走本機 Unix socket，沒有 telemetry | [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance) |
| 實作 agent 自己審自己，容易放過盲點 | 可交給另一個 reviewer agent 做對抗式審查，高風險 finding 可以擋下 apply | [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence)、[`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) |
| 想找上個月那段 prompt，只能 grep shell history | 用結構化 DSL 查 attempts、intents、commits、agent、狀態與變更檔案 | [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search) |

完整深入的解析請看 [為什麼用 ait](why-ait.md)。
每個痛點的可重跑證據請看 [痛點 demo](demos/pain-point-demos.md)。

`ait` **不是**另一個 agent。它是包在你信任的 agents 外面的本機 attempt
工作流。

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

Repo-local memory 只在同一個 repository 的 `.ait/` 內共享。AIT 會記錄
attempts、commits、notes、匯入的 agent memory files、accepted memory facts
以及 prior findings，之後只把 policy 允許的 context 召回給未來執行。
這是可檢查的專案記憶，不是某個聊天視窗裡的隱藏上下文。

對抗式審查的細節請看 [對抗式 code review](reference/adversarial-code-review.md)：reviewer adapter、findings、report，以及 review-gated apply。

## 狀態

`ait` 仍屬 alpha quality，適合本機 dogfooding 與熟悉 Git 工作流的早期
使用者。Metadata 是 repo-local 的（存在 `.ait/`），不會跨機器同步。

## 專案連結

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI 套件](https://pypi.org/project/ait-vcs/)
- [npm 套件](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
