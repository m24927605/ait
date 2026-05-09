# AIT Risk-Based Pre-Apply Review Orchestration MVP Plan

Status: Proposed implementation plan

本文把 `docs/adversarial-code-review-design.md` 的產品與架構方向拆成可執行 phase。本文只定義設計、實作範圍、測試驗收與 review gate；不代表功能已實作。

核心原則：

- 先建立 deterministic risk scan 與 review artifact，再引入 LLM reviewer。
- Review 是 apply 前的品質/安全 gate，不取代 verifier。
- `verified_status` 只代表 Git/provenance integrity；review status 代表品質/安全判斷。
- Reviewer 使用 shared trusted baseline + role-specific retrieval，不直接共享 producer 的全部記憶與推理。
- `ait run` 預設不阻塞；只有 policy 或 command 明確要求時，review 才阻塞 apply。

## Phase Overview

| Phase | 目標 | 是否有 LLM reviewer | 使用者可見能力 |
| --- | --- | --- | --- |
| Phase 0 | 設計轉實作規格 | 否 | 文件、任務拆分、acceptance criteria |
| Phase 1 | Deterministic review skeleton | 否 | `ait review attempt latest-reviewable` 輸出風險評估 |
| Phase 2 | Review persistence、baseline snapshot、apply gate | 否 | review 成為可保存、可查詢、可 gate 的一等資料 |
| Phase 3 | Single LLM reviewer | 是 | `ait review attempt <id> --mode adversarial` |
| Phase 4 | Risk-based async orchestration | 是 | `ait run --review risk-based --apply auto` |
| Phase 5 | Multi-reviewer profiles 與 finding lifecycle 強化 | 是 | critical risk 才啟用多 reviewer consensus |

真正的 LLM reviewer 從 **Phase 3** 開始。Phase 4 才把 LLM reviewer 納入 risk-based 自動 orchestration。Phase 1-2 必須先把 target selection、risk model、review data model、baseline snapshot 與 apply gate 釘穩。

## Cross-Phase Invariants

所有 phase 都必須維持以下 invariants：

- 不污染 target attempt：review failure 不得把 target attempt 改成 `verified_status=failed`。
- 不自動信任 AI reviewer：LLM 結論必須轉成 structured findings，並附 evidence。
- 不預設同步阻塞 `ait run`：除非使用者或 repo policy 明確要求。
- 不無差別共享 memory：reviewer baseline 必須經 policy 過濾，並保存 baseline artifact。
- 不覆蓋使用者工作區：沿用現有 apply/recover/hold 安全模型。
- 所有 override 都必須留下 audit trail。
- 所有 review 結果都必須可重現：至少能追到 target attempt、target head、base ref、policy hash、baseline ref、artifact ref。

## Phase 0: Design To Spec

### Design Scope

Phase 0 把設計文件轉成可實作規格，目標是降低 Phase 1-3 的含糊空間。

要明確定義：

- `latest-reviewable` selector 的精確規則。
- deterministic risk scoring 的初版訊號與權重。
- review status 與 finding severity 的枚舉。
- review artifact 格式。
- baseline snapshot 格式。
- apply gate policy 的最低行為。
- CLI 文案與 JSON output contract。
- Phase 1-3 的測試 fixture 策略。

### Implementation Tasks

- 新增或更新 implementation plan 文件。
- 從設計文件抽出 MVP-only 範圍。
- 定義 CLI output examples。
- 定義 migration 草案，但不實作 migration。
- 定義測試矩陣。

### Test Acceptance

Phase 0 不需要程式測試，但文件驗收需滿足：

- Phase 1-5 每個 phase 都有明確 scope。
- 每個 phase 都有測試驗收條件。
- 每個 phase 都有 review gate。
- 明確寫出 Phase 3 才引入 LLM reviewer。
- 明確寫出 Phase 4 才讓 LLM reviewer 進入 risk-based 自動流程。

### Review Gate

Phase 0 review 應確認：

- 文件沒有把 proposed design 寫成已實作。
- 文件沒有承諾所有 run 預設 review。
- 文件沒有把 review failure 混入 `verified_status`。
- 文件沒有要求 reviewer 讀取未過濾的全部 memory。
- MVP 範圍足夠小，可以在 repo 現有架構中逐步落地。

## Phase 1: Deterministic Review Skeleton

### Design Scope

Phase 1 建立 review CLI 與 deterministic risk scan，但不保存 review 到 DB，也不呼叫 LLM。

目標是先回答兩個問題：

- Review 到底審哪個 attempt？
- 這個 attempt 的風險為何？

建議第一個使用者可見命令：

```bash
ait review attempt latest-reviewable --format json
```

Text format 可作為輔助，但 Phase 1 的穩定 contract 應以 JSON 為主。

### Implementation Tasks

新增或修改：

- `src/ait/cli_parser.py`
  - 新增 `review` 子命令。
  - 新增 `ait review attempt <selector>`。
  - 支援 `--format {text,json}`。

- `src/ait/cli/review.py`
  - 新增 CLI handler。
  - 輸出 deterministic risk scan 結果。

- `src/ait/review.py`
  - 載入 target attempt。
  - 解析 selector。
  - 收集 changed files 與 commit metadata。
  - 產生 review target summary。

- `src/ait/review_policy.py`
  - 初版 risk scoring。
  - sensitive path matching。
  - 建議 review mode：`none` / `light` / `adversarial`。

`latest-reviewable` 初版定義：

- 最近一個 `verified_status=succeeded` 的 attempt。
- 有 committed changes。
- 尚未 promoted/applied。
- workspace/ref 還可讀。
- 不是 discarded。
- 尚未有 passing review，或 review 已過期。Phase 1 尚未有 persistence，因此此條可先視為「尚無 review 狀態可判斷」。

Phase 1 JSON output contract 草案：

```json
{
  "target_attempt_id": "repo:ulid",
  "verified_status": "succeeded",
  "changed_files": ["src/example.py"],
  "risk_level": "medium",
  "risk_score": 35,
  "risk_reasons": [
    {
      "code": "changed_sensitive_path",
      "message": "changed path matches configured sensitive path",
      "paths": ["src/auth.py"]
    }
  ],
  "review_required": false,
  "suggested_mode": "light"
}
```

### Test Acceptance

Unit tests:

- `latest-reviewable` 選到最近的 succeeded/unapplied/changed attempt。
- `latest-reviewable` 跳過 failed、discarded、promoted、noop attempt。
- 找不到 reviewable attempt 時回傳明確錯誤。
- risk scan 對 sensitive path 加分。
- risk scan 對 lockfile、workflow、migration、deleted tests 加分。
- risk scan 對沒有 test evidence 的 attempt 加分。
- risk scan 不需要 LLM、network、daemon。

CLI tests:

- `ait review attempt latest-reviewable --format json` 輸出可 parse JSON。
- `ait review attempt <short-id>` 可透過既有 ID resolver 或 review selector 規則解析。
- text output 第一行明確顯示審查 target attempt。
- 找不到 target 時提示 `ait attempt list --verified-status succeeded`。

Regression tests:

- `ait run` 行為不變。
- `ait apply` 行為不變。
- `verified_status` 不因 review scan 改變。

### Review Gate

Phase 1 implementation review 應確認：

- selector 語意清楚，沒有重新引入模糊的 `ait review latest`。
- risk scoring 是 deterministic，測試不依賴 LLM。
- 沒有新增 DB migration。
- 沒有阻塞既有 apply flow。
- 錯誤訊息能引導使用者找到可 review attempt。

## Phase 2: Review Persistence, Baseline Snapshot, And Apply Gate

### Design Scope

Phase 2 讓 review 成為 AIT 的一等資料，但仍不引入 LLM reviewer。

目標：

- 保存 deterministic review result。
- 保存 baseline snapshot artifact。
- 引入 review freshness 概念。
- 引入 human override audit trail。
- 讓 `ait apply` 可以讀 review gate policy。

此階段的 review finding 可以只來自 deterministic checks，不需要 LLM。

### Implementation Tasks

新增或修改：

- `src/ait/db/schema.py`
  - 新增 `attempt_reviews`。
  - 新增 `attempt_review_findings`。
  - 新增 `attempt_review_overrides` 或等價 audit table。

- `src/ait/db/repositories.py` / core repositories
  - 新增 create/get/list review API。
  - 新增 create/list finding API。
  - 新增 override API。

- `src/ait/review_baseline.py`
  - 建立 reviewer baseline。
  - 只收 trusted source。
  - 保存 `baseline_ref`。

- `src/ait/review.py`
  - Phase 1 risk result 寫入 DB。
  - 產生 `artifact_ref`。
  - 計算 `policy_hash` 與 `baseline_policy_hash`。

- `src/ait/landing.py`
  - 在 repo policy 要求 review gate 時，apply 前讀 review status。
  - missing/running/blocked/failed review 走 hold。
  - explicit override 可 bypass gate，但必須寫 audit trail。

- `src/ait/policy.py`
  - 加入 review policy 的讀取與 defaults。

- `src/ait/report/*` / `src/ait/run_report.py`
  - 顯示 latest review status、risk level、finding count、baseline ref。

Review status 初版：

- `queued`
- `running`
- `passed`
- `blocked`
- `warning`
- `failed`
- `overridden`

Finding lifecycle 初版：

- `open`
- `acknowledged`
- `fixed`
- `false_positive`
- `accepted_risk`
- `superseded`

### Test Acceptance

DB/migration tests:

- 舊 DB migration 後可讀寫 review tables。
- `attempt_reviews.target_attempt_id` 正確關聯 attempt。
- `attempt_reviews.review_attempt_id` 可 nullable。
- findings 可多筆關聯到同一 review。
- override 不修改原始 review/finding，只新增 audit record。

Baseline tests:

- baseline artifact 會寫入 `.ait/` 下可追蹤位置。
- baseline 不包含 candidate memory 作為 trusted fact。
- baseline 不包含 policy-blocked facts。
- baseline 可把 producer transcript 標成 evidence/advisory。
- baseline output 包含來源摘要與 policy hash。

Apply gate tests:

- policy 未要求 review 時，`ait apply` 行為維持既有邏輯。
- policy 要求 review 且 review missing 時，apply hold。
- policy 要求 review 且 review blocked 時，apply hold。
- policy 要求 review 且 review passed 時，apply 依既有安全條件繼續。
- override 後 apply 可繼續，但 status/report 顯示 overridden。

Report tests:

- status/report 顯示 risk level。
- status/report 顯示 review status。
- status/report 顯示 blocking reason。
- status/report 顯示 baseline ref。

Regression tests:

- verifier 不受 review status 影響。
- outcome classification 不被 review failure 誤改為 Git failure。
- recover flow 不因 review persistence 失效。

### Review Gate

Phase 2 implementation review 應確認：

- schema 沒有把 review status 塞進 attempts 的 `verified_status`。
- baseline source allow/block policy 有測試。
- apply gate 只在 policy 要求時阻塞。
- override 有 audit trail，不偽裝成 passed。
- report 顯示足夠資訊讓使用者知道為什麼被 hold。

## Phase 3: Single LLM Reviewer

### Design Scope

Phase 3 才引入第一個真正 LLM reviewer。

目標：

- 使用 Phase 2 的 target、risk、baseline、artifact、DB 與 gate。
- 產生 reviewer brief。
- 透過 adapter 執行 reviewer agent。
- 解析 structured findings。
- high/critical finding 可以 block apply。

使用者可見命令：

```bash
ait review attempt <attempt-id> --mode adversarial
ait review attempt latest-reviewable --mode adversarial
```

此階段可以支援同步 review。Async orchestration 留到 Phase 4。

### Implementation Tasks

新增或修改：

- `src/ait/review.py`
  - 產生 reviewer brief。
  - 執行 reviewer command 或 adapter。
  - 讀取 reviewer output。
  - 解析 structured JSON findings。
  - 寫入 `attempt_review_findings`。

- `src/ait/adapters.py` 或相關 adapter helper
  - 定義 reviewer adapter invocation 方式。
  - 避免 reviewer 改 target attempt。

- `src/ait/review_baseline.py`
  - 根據 budget/profile 產生不同 reviewer context。

- `src/ait/cli_parser.py`
  - `ait review attempt ... --mode adversarial`
  - `--review-adapter`
  - `--review-budget`
  - `--profile`

- `src/ait/cli/review.py`
  - 顯示 reviewer run summary。
  - 顯示 finding summary。

Structured finding contract 草案：

```json
{
  "summary": "review summary",
  "findings": [
    {
      "severity": "high",
      "blocking": true,
      "path": "src/auth.py",
      "line": 42,
      "title": "Authorization bypass",
      "body": "The new branch returns success before checking ownership.",
      "evidence": "diff hunk or trace reference",
      "suggested_test": "add test for cross-tenant access",
      "confidence": "medium"
    }
  ]
}
```

LLM reviewer prompt 必須明確要求：

- 只回 structured JSON 或明確 fenced JSON。
- findings 必須有 path/hunk/reason。
- 不得把 producer 自述當 trusted fact。
- 沒有 evidence 時要標記 missing evidence。
- high/critical 才 blocking。

### Test Acceptance

Parser tests:

- valid reviewer JSON 可解析成 findings。
- fenced JSON 可解析。
- malformed JSON 使 review status = `failed`，不得 crash。
- unknown severity 會降級或標記 parse error。
- missing path/hunk/reason 的 high finding 不能直接放行。

Prompt/brief tests:

- reviewer brief 包含 target attempt id。
- reviewer brief 包含 changed files。
- reviewer brief 包含 baseline ref。
- reviewer brief 把 producer transcript 標為 evidence/advisory。
- reviewer brief 不包含 policy-blocked trusted facts。

LLM invocation tests:

- 用 fake reviewer adapter 回傳 deterministic JSON。
- high/critical blocking finding 使 review status = `blocked`。
- medium/low findings 使 review status = `warning` 或 `passed_with_warnings` 等價狀態。
- no findings 使 review status = `passed`。
- reviewer command failure 使 review status = `failed`，不污染 target attempt。

Apply gate tests:

- high blocking finding 阻止 auto apply。
- malformed reviewer output 在 required gate 下阻止 auto apply。
- override 可 bypass 但保留 audit trail。

Regression tests:

- `ait run` 不指定 review 時不呼叫 reviewer。
- `ait apply` 未啟用 review policy 時不要求 LLM review。
- reviewer attempt 或 artifact 失敗不改 target `verified_status`。

### Review Gate

Phase 3 implementation review 應確認：

- LLM reviewer 是 opt-in，不是預設同步流程。
- Reviewer output parser 對壞輸出 fail closed。
- Reviewer 不直接修改 target attempt workspace。
- Reviewer prompt 清楚分離 trusted baseline 與 advisory evidence。
- Findings 都有可審計 evidence，不只是模型主觀評語。
- Secret/redaction 與 memory policy 沒有被繞過。

## Phase 4: Risk-Based Async Orchestration

### Design Scope

Phase 4 把 Phase 3 的 LLM reviewer 納入 risk-based 自動 orchestration。

目標：

- `ait run --review risk-based --apply auto`。
- low risk 不阻塞。
- medium risk 走 light review。
- high risk 走 adversarial review。
- critical risk 可要求 adversarial review 通過後才 auto apply。
- review 可 queue/background 執行。

使用者可見命令：

```bash
ait run --review risk-based --apply auto -- ...
ait review status
```

### Implementation Tasks

新增或修改：

- `src/ait/review_queue.py` 或 daemon integration
  - queue review jobs。
  - track queued/running/completed/failed。
  - 確保 background failure 不污染 target attempt。

- `src/ait/cli/run.py`
  - run 成功後依 risk policy queue review。
  - 若 `--apply auto` 且 gate 需要 review，等待或 hold。

- `src/ait/cli/review.py`
  - `ait review status`。
  - 顯示 queued/running review。

- `src/ait/policy.py`
  - review default mode。
  - auto apply requires review。
  - sensitive paths。
  - required profiles。

- `src/ait/run_report.py`
  - 將 queued/running review 狀態寫入 report。

Apply-time behavior：

```text
review not required -> continue existing apply checks
review queued/running and required -> hold with clear message
review failed and required -> hold
review blocked -> hold
review passed -> continue existing apply checks
review overridden -> continue existing apply checks and report override
```

### Test Acceptance

Queue tests:

- high-risk run 會 queue review。
- low-risk run 不 queue LLM review。
- queued review 可被 status 查到。
- review completion 更新 DB status。
- duplicate queue request 不重複建立相同 required review。

Run/apply tests:

- `ait run --review risk-based --apply never` 不阻塞 run。
- `ait run --review risk-based --apply auto` 在 required review 未完成時 hold，而不是默默 apply。
- required review passed 後 auto apply 依既有安全條件繼續。
- required review blocked 後 auto apply hold。

Policy tests:

- sensitive path 觸發 high risk。
- critical risk 可要求 profile review。
- policy invalid values fallback 到 safe defaults。
- policy hash 改變使舊 review stale。

Status/report tests:

- `ait review status` 顯示 queued/running/completed。
- report 顯示 review queued reason。
- report 顯示 apply hold 是因為 review gate。

Performance tests:

- low-risk `ait run` 無 LLM invocation。
- risk scan 在合理時間內完成。
- async review 不讓 run command 一直等待，除非 apply gate 明確要求。

### Review Gate

Phase 4 implementation review 應確認：

- risk-based orchestration 沒有讓所有 run 預設等 LLM。
- auto apply 在 required review 未完成時 fail closed/hold。
- async queue 有去重與狀態恢復策略。
- status/report 能清楚解釋等待或 hold 的原因。
- policy defaults 保守但不破壞既有使用流程。

## Phase 5: Multi-Reviewer Profiles And Finding Lifecycle Refinement

### Design Scope

Phase 5 只針對 critical risk 引入 multi-reviewer profiles 與更完整 finding lifecycle。

目標：

- security/regression/maintainability/release profiles。
- critical risk 才啟用 multi-reviewer。
- disagreement 進入 needs-human-review，而不是自動放行。
- finding lifecycle 可被更新、查詢、報告。

使用者可見命令：

```bash
ait review attempt latest-reviewable --mode multi --profile security --profile regression
ait review finding update <finding-id> --status false_positive --reason "not reachable"
```

### Implementation Tasks

新增或修改：

- `src/ait/review.py`
  - 支援多 profile review。
  - 合併 findings。
  - 判斷 consensus/disagreement。

- `src/ait/review_policy.py`
  - required profiles by path。
  - consensus gate。
  - disagreement handling。

- `src/ait/cli/review.py`
  - finding lifecycle update。
  - list findings。

- `src/ait/query/*`
  - 支援 review/finding 查詢欄位，或先提供 review-specific list 命令。

- `src/ait/report/*`
  - 顯示 profile result、consensus、open findings、accepted risk。

Consensus 初版：

- any critical/high blocking finding -> block。
- all required profiles passed -> pass。
- required profile failed/missing -> hold。
- reviewer disagreement on high/critical severity -> needs human review。
- override 可 bypass，但必須標記 accepted risk。

### Test Acceptance

Profile tests:

- auth path 觸發 security + regression。
- migration path 觸發 regression + release。
- workflow path 觸發 security。
- low-risk path 不觸發 multi-reviewer。

Consensus tests:

- 任一 high blocking finding 使 review blocked。
- required profile missing 使 gate hold。
- conflicting reviewer conclusions 使 status 進入 needs-human-review 或等價 blocked 狀態。
- all required profiles passed 後 gate passed。

Finding lifecycle tests:

- finding 可從 open -> acknowledged。
- finding 可標 false_positive，但不刪除原始 finding。
- finding 可標 accepted_risk，並要求 reason。
- superseded review 會讓舊 finding 顯示 superseded 或 stale。

Query/report tests:

- 可列出 open high findings。
- 可列出 overridden reviews。
- report 顯示 profile-level result。

Regression tests:

- multi-reviewer 不會在 non-critical risk 預設啟用。
- lifecycle update 不改 target attempt。
- accepted risk 不偽裝成 passed review。

### Review Gate

Phase 5 implementation review 應確認：

- multi-reviewer 只用於 high-value/critical paths，不造成普遍 review fatigue。
- consensus 規則 fail closed。
- lifecycle 不會刪除審計歷史。
- false positive/accepted risk 都需要 reason。
- query/report 足以支援後續人工審查。

## Phase Exit Criteria

每個 phase 完成前，都應符合：

- 文件更新：若 CLI、policy、schema 或 status 語意改變，相關 docs 必須同步。
- Test coverage：新增功能至少有 unit + CLI 或 integration coverage。
- Backward compatibility：既有 `ait run`、`ait apply`、`ait recover` 不因未啟用 review 而行為改變。
- Failure mode：錯誤情況應 hold 或 fail closed，不應 silent apply。
- Auditability：review、baseline、override、finding 都能追到 artifact 或 DB record。

## Suggested Implementation Order

建議實作順序：

1. Phase 1 selector 與 risk scan。
2. Phase 1 CLI JSON/text output。
3. Phase 2 DB schema 與 repositories。
4. Phase 2 baseline snapshot artifact。
5. Phase 2 apply gate policy。
6. Phase 3 fake reviewer adapter 與 parser。
7. Phase 3 real single LLM reviewer invocation。
8. Phase 4 risk-based queue 與 run integration。
9. Phase 5 multi-reviewer profiles。
10. Phase 5 finding lifecycle/query/report refinement。

這個順序刻意把 LLM reviewer 放在 parser、artifact、baseline、gate 之後，避免先做出一個看起來能 review、但無法審計、無法 gate、無法測試的功能。

## First Implementation Slice

最小可合併 vertical slice 建議是 Phase 1 的一半：

```bash
ait review attempt latest-reviewable --format json
```

只需輸出：

- `target_attempt_id`
- `verified_status`
- `changed_files`
- `risk_level`
- `risk_score`
- `risk_reasons`
- `review_required`
- `suggested_mode`

此 slice 不做 DB、不做 baseline、不做 apply gate、不做 LLM。它的價值是先驗證 CLI 語意、selector 語意與 deterministic risk model。

## Review Checklist For Future PRs

每個實作 PR 都應回答：

- 這個 PR 是否改變既有 `ait run/apply/recover` 預設行為？
- 是否有任何 review failure 被寫入 `verified_status`？
- 是否有任何未審核 memory 被當成 trusted baseline？
- 是否有 reviewer output 被直接信任而未結構化解析？
- 是否有 override 沒有 audit trail？
- 是否有 apply gate 在錯誤時 silent allow？
- 是否有新增 CLI selector 語意不清？
- 是否有測試證明未啟用 review 時既有流程不變？
