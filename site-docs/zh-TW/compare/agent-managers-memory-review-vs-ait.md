---
title: ait 對比 agent managers、memory layers 與 review bots
description: >-
  ait 與 GUI-first agent managers、worktree managers、memory layers、review
  bots、provenance tools 的產品邊界：AIT 是 AI coding agents 的本機
  control plane 與 Git-native attempt ledger。
---

# ait 對比 agent managers、memory layers 與 review bots

ait 是 **AI coding agents 的本機 control plane**。產品核心不是單一
worktree、memory file、review comment 或 graph report，而是 attempt
ledger：一次 agent run 會變成可審核的 attempt，串起 prompt、context、
files、commits、memory evidence、review findings，以及明確的
apply/recover 決策。

所以 AIT 會跟好幾種工具重疊，但它不只是其中一種。這頁是邊界圖。

## 類別邊界

| 類別 | 使用者主要想解的問題 | AIT 重疊處 | AIT 不同處 |
| --- | --- | --- | --- |
| GUI-first agent managers | 視覺化 task board、桌面工作流、queueing、廣義 agent orchestration。 | `ait graph --html` 會顯示 attempts、evidence、memory、hot files、review state；`ait console --read-only` 會基於 versioned `ait.work_graph` contract 產生 loopback-only local console；`ait console action ... --dry-run` 會記錄 preflight/journal plans。 | AIT 目前仍是 CLI-first。Browser mutation UI 與 action execution 尚未啟用。 |
| Worktree managers | 隔離平行修改、管理 branch/worktree 清理。 | 每個 wrapped run 都會有隔離 Git worktree，並有 apply、recover、discard 等 attempt lifecycle verbs。 | Worktree 只是實作細節。AIT 還記錄 prompt provenance、context、memory、review evidence 與 outcome。 |
| Memory layers | 跨 session、跨 agent 重用專案脈絡。 | Live federated memory 會合併 AIT-owned attempts、notes、accepted facts、review findings，以及目前 repo 內的 `CLAUDE.md`、`AGENTS.md`、`.claude/`、`.codex/`、Cursor rules。 | AIT memory 是 attempt-derived、evidence-backed。它不是隱藏聊天記憶、不是 vector database 產品，也不是自動 prompt stuffing。 |
| Review bots | 在 merge/apply 前挑戰程式碼並留下 findings。 | `ait review` 可以跑 deterministic light checks，或交給 adversarial reviewer adapter。高風險 findings 可以 hold attempt；deterministic benchmark fixture 目前有 10 cases。Explicit `--dogfood` real reviewer benchmark run 會記錄 adapter metadata。 | AIT review 是本機、attempt-aware。公開文件目前不宣稱已經有 benchmark-proven defect detection；real Claude/Codex dogfood artifacts 仍需要補。 |
| Provenance / audit tools | 回答 AI 變更由誰、什麼 prompt、什麼 evidence 產生。 | Attempt 會把 intent、prompt、adapter、output、files、commits、status、memory、review evidence 串在 `.ait/`。 | AIT 是 repo-local 與 Git-native。不需要 SaaS dashboard、telemetry 或上傳原始碼。 |

## 快速判斷

| 你主要需要的是... | 比較適合 |
| --- | --- |
| 用視覺化桌面 board 驅動所有 agent 工作 | GUI-first agent manager，未來可視情況把 AIT 放在底層 |
| 一次性的手動 branch/worktree 隔離 | 原生 `git worktree` 或小腳本 |
| Cloud evaluation / observability platform | LLM observability tooling |
| 現有 CLI agents 外面的 repo-local memory、attempt provenance、cross-agent handoff 與 review gate | AIT |

當你已經同時使用多個 coding agents，或失去 prompt、context、review evidence、
failed attempt 的成本很高時，AIT 最有價值。

## 目前狀態

| 面向 | 目前已實作 | 目前不能宣稱 |
| --- | --- | --- |
| Attempt ledger | Wrapped runs、attempt records、worktree isolation、apply/recover flow。 | AIT 可以取代 Git review 或人的判斷。 |
| Shared memory | Live federated recall 會讀 AIT-owned records 與 repo-local memory files。 | Memory 是通用 vector database、隱藏聊天同步，或永遠可信的 context。 |
| Graph/data model | `ait graph --html` 產生靜態本機報告；`ait graph --format json` 帶有 `schema: ait.work_graph` 與 `schema_version`；`ait console --read-only` 會把同一份資料 render 成本機 daily console；`ait console action ... --dry-run` 會記錄 preflight 與 journal entries。 | AIT 已經有 browser mutation actions、console action execution 或完整 GUI-first desktop console。 |
| Review gate | 已有 light deterministic review、adversarial reviewer workflow、10-case fixture、benchmark fake CI path，以及 Claude/Codex real dogfood artifacts；目前 real artifacts 是 unavailable 或 failed。 | Adversarial review 已經在真實專案上有 benchmark-proven quality。 |
| Team adoption | Metadata 存在 repo 內 `.ait/`；no SaaS、no telemetry；`.ait/policy.json` validation 會 fail closed，且 runtime-enforced 於 apply、review、console action preflight、context trust filtering。Metadata export/import dry-run plans 已存在。 | Cross-machine metadata sync、non-dry-run import 或面向一般非技術團隊的成熟度。 |

## Roadmap 邊界

下一個產品步驟仍是 repo-local daily console 的 mutation hardening。Read-only
surface 已存在，CLI action dry-run layer 也已有 preflight checks 與
append-only journal。Browser action controls 與 execution 必須等
[`docs/console-mutation-recovery-design.md`](https://github.com/m24927605/ait/blob/main/docs/console-mutation-recovery-design.md)
定義的 execution、retry、rollback、recovery tests 完成後才加入。公開文案應把 `ait graph --html` 稱為靜態報告，把
`ait graph --format json` 稱為 data contract，把 `ait console --read-only`
稱為 read-only console。

下一個 review 步驟是跑出 real reviewer dogfood artifacts。更強的
review-quality claim 需要 repeated Claude Code / Codex local reviewer reports、
false-positive reporting、latency/cost data 與 fixture hashes，並依照
[`docs/review-benchmark-real-dogfood-design.md`](https://github.com/m24927605/ait/blob/main/docs/review-benchmark-real-dogfood-design.md)
產出。在那之前，公開文案應把 adversarial review 描述為額外 safety pass，而不是已證明的保證。

## Comparison Claims 的 Release Gate

任何新的公開比較宣稱都應通過這個 gate：

- 宣稱能對應到已實作 command、file，或明確標示的 roadmap item。
- 不暗示已完成 GUI daily console 或 mutation surface。
- 沒有 real reviewer dogfood report 與足夠量測資料前，不宣稱 benchmark-proven review quality。
- 維持 local-only metadata、no telemetry、Git as source of truth。
- 當其他類別更適合時，要明確說出 tradeoff。

## Code Review Standard

Comparison page 的修改應被當成產品宣稱審查，而不是只看文筆。Reviewer 應確認
每句話都有目前程式碼、測試或明確 roadmap 支撐；類別邊界是否具體；以及頁面
沒有把目前的 AIT 包裝成 GUI product、cloud memory layer 或已完成的
review-quality benchmark。

→ Worktree-specific tradeoffs 請看
[Naked git-worktree vs ait](https://m24927605.github.io/ait/compare/git-worktree-naked-vs-ait/)。
