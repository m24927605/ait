---
title: 對抗式 code review
description: >-
  如何用 Claude Code 或自訂 reviewer adapter 對 AIT attempt 執行對抗式
  code review、檢查 findings，並在套用 AI 產生的變更前使用 review evidence。
---

# 對抗式 code review

對抗式 review 是讓 AIT 從「比較安全地跑 agent」變成「AI engineering
control plane」的關鍵能力。

一個 agent 實作，另一個 reviewer agent 挑戰結果。AIT 記錄審查結論，並且
可以在 blocked attempt 進入目前 checkout 前擋下 apply。

Reviewer 不會編輯 target attempt worktree。AIT 會給 reviewer 一份
structured brief、捕捉輸出、解析 findings，並把 review evidence 存在
`.ait/`。

這跟手動叫另一個 agent「幫我看一下 diff」不一樣：

- review target 是一個 AIT attempt，不是鬆散的 working tree
- reviewer 會收到一致的 structured baseline、risk reasons、diff evidence、
  transcript evidence，以及必須遵守的 JSON schema
- findings 會被保存，而且可查詢
- high 與 critical findings 可以成為 blocking review evidence
- 開啟 review-gated apply 後，blocked attempt 會在套用前被 hold

## 為什麼 review 品質會變好

對抗式 review 會提升 AI code review 品質，因為它同時改變了 reviewer 的
角色與輸入資訊。

- **角色分離：** 寫程式的 agent 不再自己審自己。另一個 reviewer agent
  會被要求挑戰這次 attempt。
- **任務更尖銳：** reviewer 不是被要求給泛泛建議，而是要找出這個 attempt
  為什麼不應該被接受。
- **脈絡更完整：** reviewer 會看到 attempt metadata、changed files、diff
  evidence、test evidence、transcript references、risk reasons，以及本機
  baseline context。
- **輸出可結構化：** finding 會變成含 severity、path、body、confidence、
  `blocking` 的紀錄。
- **結果有後果：** review gate 開啟後，blocked review 可以 hold 住
  `ait apply`。

所以它不是另一段聊天回覆，而是可查詢、可產 report、可執行 gate 的 workflow
evidence。

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

如果要讓 CLI apply 必須先看到 clear latest review，請在 `.ait/policy.json`
設定 review gate：

```json
{
  "schema": "ait.team_policy",
  "schema_version": 1,
  "apply": {
    "require_review_clearance": true
  }
}
```

接著嘗試套用 blocked attempt：

```bash
ait apply <attempt-id> --mode current
```

預期結果：

```text
AIT held the result because this repo requires review before apply.
Status: held
Reason: review gate: required review is blocked
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
- apply 重要 AI-generated result 之前
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

## 如何量化 review 品質

AIT 不應該在沒有證據時聲稱 adversarial review 一定比較好。現在已實作的是
可量測的 substrate：

- deterministic `light` review，用低成本方式做 risk classification
- high-risk attempt 可升級給另一個 LLM reviewer adapter
- finding 有 severity、confidence、path、status 與 blocking state
- review status 與 finding history 可查詢
- policy 要求時，review-gated apply 可以擋下 blocked attempt

仍然缺的是 repeated successful real-reviewer data：reviewer 找到多少
implementer 漏掉的 bug、false positive rate、latency、token cost、哪些 risk
patterns 最有效，以及何時 deterministic review 就夠、何時值得付出 LLM
reviewer 成本。在這些數據公開前，請把 adversarial review 視為額外安全檢查，
不是正確性證明。

目前 baseline report 放在 repo 內的
[`docs/review-benchmark-dogfood-report.md`](https://github.com/m24927605/ait/blob/main/docs/review-benchmark-dogfood-report.md)。
它記錄 deterministic fake-reviewer metrics、本機 Claude Code/Codex dogfood
artifacts，以及在做出更強公開品質宣稱前必須達成的驗收門檻。目前修復後的
real dogfood artifacts 已可完成；它們證明 AIT 會誠實呼叫、解析與記錄本機
reviewer，但仍只是本機 dogfood evidence，不是 review 品質證明。

## Demo flow

如果觀眾已經熟悉 Claude Code 與 Codex，可以這樣 demo：

1. 用 Claude Code 當實作者。
2. 用 Codex 當對抗式 reviewer，執行 `ait review attempt --mode adversarial
   --review-adapter codex`。
3. 展示 `ait query --on attempt 'review.status="blocked"' --format table`。
4. 展示 `ait review finding list --severity high --format text`。
5. 展示 `ait review report --attempt <attempt-id> --format json`。
6. 執行 `ait apply <attempt-id> --mode current`，讓觀眾看到 review gate hold
   住 blocked attempt。

重點是：AIT 不是「另一層 prompt wrapper」。它把 agent work 與 reviewer work
都變成和 Git attempts 綁定的 durable、reviewable records，並且讓這些
evidence 影響程式能不能落地。

## 邊界

Adversarial review 仍然是 LLM-assisted review。它不能取代測試、人類判斷，
也不能取代 domain-specific verification。AIT 會給 reviewer 更好的 context，
並記錄結果，但 clean review 不代表形式化證明變更一定正確。

AIT 本身不會把 code 上傳到 SaaS。你選擇的 reviewer adapter 才決定 reviewer
model 在哪裡執行。
