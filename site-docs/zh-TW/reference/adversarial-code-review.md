---
title: 對抗式 code review
description: >-
  如何用 Claude Code 或自訂 reviewer adapter 對 AIT attempt 執行對抗式
  code review、檢查 findings，並在套用 AI 產生的變更前使用 review evidence。
---

# 對抗式 code review

Adversarial review 是針對已完成 AIT attempt 的第二道 reviewer agent。Reviewer
不會編輯 target attempt worktree。AIT 會給 reviewer 一份 structured brief、
捕捉輸出、解析 findings，並把 review evidence 存在 `.ait/`。

這跟手動叫另一個 agent「幫我看一下 diff」不一樣：

- review target 是一個 AIT attempt，不是鬆散的 working tree
- reviewer 會收到一致的 structured baseline、risk reasons、diff evidence、
  transcript evidence，以及必須遵守的 JSON schema
- findings 會被保存，而且可查詢
- high 與 critical findings 可以成為 blocking review evidence

## 快速開始

先跑 deterministic risk scan：

```bash
ait review attempt latest-reviewable --mode light
```

用 Claude Code 當 adversarial reviewer：

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code \
  --review-budget standard
```

檢查 findings，並產出可攜式報告：

```bash
ait review finding list --status open
ait review report --attempt latest --format markdown --output docs/reviews/latest.md
```

如果某個 finding 是 false positive，或你決定接受風險，要記錄理由：

```bash
ait review finding update <finding-id> --status false_positive --reason "not reachable"
ait review finding update <finding-id> --status accepted_risk --reason "accepted for demo"
```

## 什麼時候該用

當 AI 變更出錯的成本高於多跑一道 review 的成本時，就適合用 adversarial
review：

- auth、billing、payments、security、deployment、CI、migration、dependency
  相關變更
- 大 diff，或跨多個 subsystem 的變更
- test evidence 缺失或偏弱的 attempt
- 套用或 promote 重要 AI-generated result 之前
- 比較 Claude Code 與 Codex 針對同一任務產生的不同 attempts 時

低風險修改通常用 `light` mode 就夠，因為它是本機、deterministic、速度快。

## Reviewer 會看到什麼

AIT 會從 attempt record 與 repo-local context 建出 reviewer brief。Brief
可以包含：

- target attempt metadata、changed files、diff excerpts
- run 過程中捕捉到的 prompt 與 transcript references
- 可用時的 structured test、build、lint evidence
- `light` mode 算出的 deterministic risk reasons
- policy 允許的 trusted repo-local memory facts
- 與相同區域相關的 prior failed attempts 與 prior review findings
- reviewer 必須回傳的 JSON schema

Candidate、stale、superseded 或 policy-blocked memory 只會是 advisory，
或被排除；不會被當成 trusted baseline。

## Claude Code reviewer path

內建 `claude-code` review adapter 會呼叫本機 CLI：

```bash
claude -p
```

AIT 透過 stdin 傳入 brief，在 target attempt worktree 外執行 reviewer，並從
子行程環境移除 `ANTHROPIC_API_KEY`。這避免 silent fallback 到 provider API
credits。如果本機 Claude Code 沒有安裝或尚未登入，review 會 fail closed。

檢查本機 auth path：

```bash
ait adapter doctor claude-code --json
```

本機 CLI mode 的預期結果會顯示 `will_use_api_key: false` 與
`will_fallback_to_credits: false`。

## 自訂 reviewer adapter

本機實驗可以使用 command-style adapter：

```bash
ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter 'command:python scripts/review_attempt.py'
```

該 command 會從 stdin 收到 reviewer brief，並必須輸出符合 schema 的
structured JSON。也可以透過 repository policy 設定 named review adapter。

## Risk-based run policy

`risk-based` 是 run policy。它讓 AIT 依 risk assessment 決定該不該 review、
該跑 `light`，或升級到 `adversarial`：

```bash
ait run \
  --review risk-based \
  --review-adapter claude-code \
  --adapter claude-code -- claude
```

目前 policy：

- `low`：不 review
- `medium`：`light`
- `high` 或 `critical`：`adversarial`

Queued reviews 可以這樣檢查與處理：

```bash
ait review status
ait review worker --once
```

## Demo flow

如果觀眾已經熟悉 Claude Code 與 Codex，可以這樣 demo：

1. 用 Claude Code 跑一個 task，再用 Codex 跑另一個 task，每個都是獨立 AIT
   attempt。
2. 用 `ait attempt list` 比較 attempts，畫面不會塞滿長 ID。
3. 跑 `ait review attempt latest-reviewable --mode light` 展示 deterministic
   risk reasons。
4. 跑 `ait review attempt latest-reviewable --mode adversarial
   --review-adapter claude-code` 展示真正的 reviewer adapter。
5. 展示 `ait review finding list --status open` 與 `ait review report`。
6. Review evidence 可接受後，才 apply 或 promote。

重點是：AIT 不是「另一層 prompt wrapper」。它把 agent work 與 reviewer work
都變成和 Git attempts 綁定的 durable、reviewable records。

## 邊界

Adversarial review 仍然是 LLM-assisted review。它不能取代測試、人類判斷，
也不能取代 domain-specific verification。AIT 會給 reviewer 更好的 context，
並記錄結果，但 clean review 不代表形式化證明變更一定正確。

AIT 本身不會把 code 上傳到 SaaS。你選擇的 reviewer adapter 才決定 reviewer
model 在哪裡執行。
