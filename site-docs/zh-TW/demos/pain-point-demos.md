---
title: 痛點 demo
description: >-
  與 examples/pain-point-demos 對齊的 Claude Code / Codex 可執行 demo：
  每個痛點一個資料夾，每個資料夾都有自己的 workspace、run script 與 AIT
  驗證流程。
---

# 痛點 demo

可執行 demo 放在
[`examples/pain-point-demos`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos)。
每個編號資料夾都有自己的 Node.js demo project，位置固定在該資料夾的
`workspace/`，所以 demo 會改到哪些檔案，使用者可以直接在同一個痛點資料夾裡看到。

Shell scripts 只負責建立場景。真正講解時，證據應該來自 AIT 指令輸出：
`ait query`、`ait attempt show`、`ait memory list`、`ait review status`、
`ait review report`、`ait apply`。

## 前置需求

- `ait` 在 `PATH` 上
- `git`
- Node.js 與 `npm`
- `python3`
- Claude Code CLI 已安裝並登入
- Codex CLI 已安裝並登入

## 建立所有 demo workspace

```bash
cd examples/pain-point-demos
./setup.sh
```

這會建立或重置每個資料夾自己的 demo 專案：

```text
examples/pain-point-demos/01-blast-radius/workspace/
examples/pain-point-demos/02-provenance/workspace/
...
examples/pain-point-demos/10-prompt-search/workspace/
```

## 執行單一 demo

```bash
cd examples/pain-point-demos/01-blast-radius
./run.sh
cd workspace
```

接著照該資料夾 README 的 AIT 驗證流程講解。不要用 script 內部 state 或臨時
filesystem 檢查來當 demo 證據；請用 AIT metadata 與 AIT CLI output 講。

## 執行全部 demo

```bash
cd examples/pain-point-demos
./run-all.sh
```

`run-all.sh` 會重置每個 workspace，然後依序跑完整套場景。

## 資料夾對照

| 資料夾 | 痛點 | 示範重點 |
| --- | --- | --- |
| [`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius) | 變更範圍隔離 | Claude Code 做高風險大範圍修改，但 AIT 把結果留在隔離 attempt worktree。 |
| [`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance) | 來源可追溯 | AIT 記錄 intent、agent、changed files、prompt/trace references 與 attempt metadata。 |
| [`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation) | 失敗結果隔離 | Codex 故意改壞測試；失敗結果可查，但不污染主 workspace。 |
| [`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse) | 調查結果重用 | Claude 記錄調查結論，Codex 之後透過 AIT context/memory 取得。 |
| [`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents) | 平行 agents | Claude Code 與 Codex 都修改 `approach.txt`，但各自在不同 attempt worktree。 |
| [`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion) | 明確 apply | 多個 candidate attempts 可以同時存在，只有選中的結果會被接受進目前 branch。 |
| [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) | 跨 agent handoff | Claude 的決策被接受後成為 repo memory，Codex 後續可以讀到。 |
| [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance) | 本機可查 provenance | AIT metadata 可以在本機用 AIT 指令查，不需要雲端 dashboard。 |
| [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence) | 對抗式審查 | Claude 的高風險結果被 AIT adversarial review 挑戰，並被記錄為 blocked。 |
| [`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) | Claude 實作，Codex 審查 | Claude Code 寫出 unsafe `divide`，Codex 審查後擋下，review gate 會 hold `ait apply`。 |
| [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search) | Prompt 搜尋 | AIT query 可以用 intent 文字或 changed file 找回舊 attempt。 |

## AIT 驗證流程

每個 case README 都有精確指令。常見模式是：

```bash
ait query --on attempt '<selector>' --format table
ait attempt show <attempt-id>
```

memory 相關 case：

```bash
ait memory list --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
```

對抗式審查 case：

```bash
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
ait review report --attempt <attempt-id> --format json
```

`09-1-codex-reviewer` 的 apply gate 證據：

```bash
ait config show --format json
ait apply <attempt-id> --mode current
```

預期結果：

```text
AIT held the result because this repo requires review before apply.
Status: held
Reason: review gate: required review is blocked
```

## Demo 講法

用 scripts 建立場景，接著切回 AIT 指令講證據。觀眾應該帶走的重點是：
AIT 會把 agent 工作變成隔離、可查、可審核的 Git attempt，而不是要大家相信
terminal scrollback。
