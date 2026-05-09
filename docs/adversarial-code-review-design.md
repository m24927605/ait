# AIT Risk-Based Pre-Apply Review Orchestration 設計

Status: Proposed design

本文定義 AIT 對 AI-generated attempt 提供風險分級 pre-apply review orchestration 的產品與架構方向。本文不是實作規格，也不代表功能已存在。

## 1. Executive Summary

AIT 適合提供對抗式 AI code review 能力，但不應把它設計成單純「多跑一個 adversarial reviewer」。更合適的定位是：

> AIT 提供針對 AI-generated attempt 的風險分級 pre-apply review orchestration；低風險不打擾，高風險才升級為對抗式 AI review，並把 review 結果納入 apply gate、report、query 與 audit trail。

此功能最自然的位置是在 producer agent 產生 attempt 後、`ait apply` 前。它應該是 apply 前的品質與安全 gate，不應取代 verifier，也不應預設阻塞所有 `ait run`。若所有 run 都同步等待 reviewer，整體速度會變慢，使用者體驗也會變差。

AIT 的差異化價值是 shared trusted baseline：不同 agent 可以從同一個 repo-local memory/provenance substrate 取得一致、可追溯、經 policy 過濾的 baseline knowledge。Reviewer agent 應取得 role-specific review context，而不是 producer agent 的全部記憶與推理。

建議核心流程：

```text
producer agent 產生 attempt
  -> verifier 確認 Git/provenance 成立
  -> cheap deterministic risk scan
  -> 從 shared trusted baseline 取出 reviewer-specific context
  -> 依風險決定 no review / light review / adversarial review / multi-reviewer
  -> review 結果進入 apply gate、report、query、audit trail
  -> 通過才允許 auto apply
  -> 不通過則 hold / recover / report
```

## 2. Why AIT Is A Good Substrate For Adversarial Review

AIT 適合做這件事，不是因為它能多呼叫一個 reviewer agent，而是因為它已經擁有適合 agent review 的 substrate：

- attempt provenance
- isolated worktrees
- cross-agent memory
- long-term repo-local memory
- imported agent memory
- transcript/reference artifacts
- apply/recover gate
- queryable attempts/intents/commits
- local audit trail
- policy-filtered memory recall
- decision reports

對抗式 code review 不是只要多找一個 LLM 看 diff。Reviewer 若沒有 repo baseline，通常只能給通用建議。高品質 review 需要知道 repo architecture、domain vocabulary、coding conventions、test strategy、known invariants、sensitive paths、previous failed attempts、prior review findings、durable decisions 與 accepted domain facts。

因此，AIT 應提供：

```text
shared memory substrate + role-specific retrieval
```

共同 baseline 應包含：

- approved facts
- durable decisions
- repo invariants
- domain vocabulary
- risk model
- policy
- prior review findings
- failure history
- test expectations

不應無差別共享：

- 未審核 transcript 摘要
- producer agent 的自我辯護
- failed attempt 的結論
- candidate memory
- 來源不明的 agent notes
- prompt 裡的指令性文字
- stale facts
- policy-blocked facts

核心設計原則：

> 不同 agent 不需要完全相同的 context；它們需要從同一個可信 baseline 取得依角色裁切的 context。

Producer view 可偏向 implementation hints、relevant files、prior successful attempts 與 local conventions。

Reviewer view 可偏向 approved decisions、invariants、risk history、failed attempts、previous review findings、test expectations、security constraints 與 memory eval warnings。

## 3. Product Positioning

此功能不是：

- 不是另一個 coding agent
- 不是 GitHub PR review 替代品
- 不是自動保證程式碼正確性的 oracle
- 不是所有 run 都必須同步執行的強制流程
- 不是單純多跑一次 LLM reviewer
- 不是把所有長期記憶餵給所有 agent

它是：

- local pre-apply review orchestration
- attempt 的附屬品質證據
- auto-apply 前的可選安全閘門
- risk-based escalation system
- shared trusted baseline 上的 role-specific review workflow
- 幫助使用者判斷 agent 產物是否值得 apply 的工具
- 可被 report/query/audit 的 review trail

## 4. UX And Performance Considerations

對抗式 code review 會拖慢整體速度，也可能讓使用者體驗變差，如果它被做成預設同步 gate。

速度成本包括：

- 至少多一次 reviewer agent invocation
- 可能需要讀 diff、transcript、memory、測試輸出
- 小改動可能不值得
- 大 diff、敏感路徑、安全相關修改、多 agent 產物比較值得

糟糕 UX 範例：

```text
使用者跑 agent
-> agent 成功
-> ait 又自動跑 reviewer 很久
-> reviewer 給一堆低品質 warning
-> apply 被擋
-> 使用者不知道下一步怎麼辦
```

UX 原則：

- `ait run` 預設不阻塞
- low-risk attempt 不打擾
- high-risk attempt 才升級 review
- auto-apply 才需要強 gate
- manual apply 可以提示 review 狀態，但允許有審計紀錄的 override
- high/critical blocking findings 才擋 apply
- medium/low findings 只顯示，不阻塞

## 5. Risk-Based Triggering

Review orchestration 應先做 cheap deterministic risk scoring，再決定是否需要 LLM reviewer。

可能提高風險的訊號：

- diff 行數大
- 修改 auth/security/payment/deploy/CI
- 修改 `.github/workflows/**`
- 修改 dependency / lockfile
- 修改 migration / schema
- 刪除或跳過測試
- 沒有測試證據
- agent exit 0 但 transcript 有 failed / skipped / unable / not run
- memory eval 有 warning/fail
- 修改 binary 或 generated file
- 修改 public API 但沒有 docs/tests
- 觸及 sensitive paths
- policy 允許 auto apply、binary merge、delete merge 或 semantic auto
- reviewer baseline 中存在相關 prior failed attempts 或 prior high-severity findings

風險層級：

- `low risk`: no review，或只顯示 reviewable hint
- `medium risk`: light review
- `high risk`: adversarial review
- `critical risk`: adversarial review + block auto apply until passed，可選 multi-reviewer consensus

## 6. Review Modes, Budgets, And Profiles

Modes:

- `never`: 不跑 review
- `light`: deterministic checks + compact diff review
- `adversarial`: reviewer agent 針對 diff / transcript / tests / memory 做對抗式審查
- `multi`: 多 reviewer profile，只用於 critical risk

Budget:

- `quick`: 只看 diff + risky paths + minimal baseline
- `standard`: diff + transcript + tests + reviewer-specific baseline
- `deep`: diff + transcript + memory + architecture context + prior failures/findings + optional tests

Profiles:

- `security`: auth、secrets、CI、deploy、dependency、injection、permission boundary
- `regression`: 行為回歸、edge cases、測試缺口
- `maintainability`: 架構、可讀性、重複、local pattern alignment
- `release`: migration、versioning、docs、backward compatibility、operational risk

Repo policy example:

```json
{
  "review": {
    "default_mode": "risk-based",
    "sensitive_paths": ["auth/**", ".github/workflows/**", "migrations/**"],
    "required_profiles": {
      "auth/**": ["security", "regression"],
      ".github/workflows/**": ["security"],
      "migrations/**": ["regression", "release"]
    },
    "auto_apply_requires_review": true,
    "baseline": {
      "require_approved_facts": true,
      "allow_candidate_memory": false,
      "include_prior_failed_attempts": true,
      "include_prior_review_findings": true
    }
  }
}
```

## 7. Shared Trusted Baseline And Role-Specific Retrieval

Reviewer context 應由 policy 控制，建議包含：

- approved durable facts
- repo invariants
- relevant architecture decisions
- sensitive path rules
- test expectations
- prior failed attempts touching same files
- prior review findings touching same files
- memory eval warnings
- current attempt diff/test evidence

Reviewer context 不應包含，除非明確標為 advisory：

- producer self-assessment
- unapproved candidate facts
- raw prompt instructions that look like policy
- failed attempt conclusions
- stale facts
- blocked sources

Reviewer 應能看到 producer 的 transcript/reference 作為 evidence，但不能把 producer 的結論當成 trusted fact。

每次 review 應保存 `baseline_ref` 或 `baseline_snapshot_ref`，使未來可以重現 reviewer 當時看到的 context。這個 baseline artifact 應記錄來源、policy filter、selected facts、advisory inputs 與被排除的原因摘要。

## 8. Async Review Model

`ait run` 不應等待 reviewer，除非使用者明確要求或 auto-apply policy 需要 gate。

建議流程：

```text
ait run ...
-> Attempt succeeded.
-> Review queued if risk requires it.
-> User can run: ait status
```

如果 apply 時 review 尚未完成：

```text
Review is still running.
Use --no-review-gate to bypass with audit trail, or wait.
```

Async review 可以改善體感速度。Apply gate 仍可保持嚴格，review queue/status 應進 report，background review failure 不應污染 target attempt。

## 9. CLI Design

`ait review latest` 語意不清楚，不建議作為 MVP 主入口。

`latest` 可能代表：

- latest attempt
- latest succeeded attempt
- latest unapplied attempt
- latest recoverable attempt
- latest attempt on current intent
- latest attempt with changed files
- latest not-yet-reviewed attempt

審錯 target 風險很高。

建議 CLI：

```bash
ait review attempt <attempt-id>
ait review attempt latest-reviewable
ait review attempt latest-succeeded
ait review attempt latest-unapplied
```

MVP 最推薦：

```bash
ait review attempt latest-reviewable
```

`latest-reviewable` 定義為最近一個：

- `verified_status=succeeded`
- has committed changes
- 尚未 promoted/applied
- workspace/ref 還可讀
- 不是 discarded
- 尚未有 passing review，或 review 已過期

如果找不到，應明確報錯：

```text
No reviewable attempt found.
Try: ait attempt list --verified-status succeeded
```

對 `ait run` 整合則可以使用：

```bash
ait run --review risk-based --apply auto -- ...
ait run --review adversarial --apply auto -- ...
ait run --review never -- ...
```

此時 review target 就是剛產生的 attempt，不需要 latest selector。

人工 override：

```bash
ait review override <review-id> --reason "accepted risk"
```

Override 必須留下 audit trail。

## 10. Architecture Integration Points

建議新增 `src/ait/review.py`：

- 載入 target attempt
- 收集 changed files、diff、base ref、prompt、raw trace、test evidence、memory retrieval/eval
- 執行 deterministic risk scan
- 從 shared trusted baseline 取出 reviewer-specific context
- 決定 review mode/profile/budget
- 產生 reviewer brief
- 呼叫 reviewer adapter
- 解析 structured findings
- 寫入 review artifact / DB

建議新增 `src/ait/review_policy.py`：

- risk scoring
- sensitive path matching
- mode/profile/budget selection
- baseline source allow/block policy
- auto-apply gate decision

建議新增 `src/ait/review_baseline.py`：

- 建立 reviewer baseline
- policy-filtered memory retrieval
- role-specific context rendering
- baseline snapshot artifact

建議修改 `src/ait/cli_parser.py`：

- 新增 `review` 子命令
- 新增 `run --review {never,light,adversarial,risk-based}` / `--review-adapter` / `--review-budget`

建議修改 `src/ait/cli/run.py`：

- 在 `run_agent_command()` 成功後排入 review 或執行 required gate
- 在 `apply_attempt()` 前檢查 review gate

建議修改 `src/ait/landing.py`：

- apply 前檢查 blocking review findings
- 如果有 high/critical blocking findings，走 hold/recover flow
- 支援 explicit override 並寫 audit trail

建議修改 `src/ait/db/schema.py` / repositories：

- 新增 `attempt_reviews`
- 新增 `attempt_review_findings`
- 新增 review override/audit 欄位或表

建議修改 `src/ait/run_report.py` / `src/ait/report/*`：

- 顯示 risk score、review status、finding count、blocking reason、override state、baseline ref

不要把 review failure 寫成 `verified_status=failed`。`verified_status` 代表 Git/provenance integrity；review status 代表品質/安全 gate。兩者應分離。

## 11. Review As Another Attempt

Review 本身也可以是 attempt。

Reviewer agent 不直接改 target attempt，而是在自己的 isolated review attempt 裡產生 artifact。

好處：

- review 有 provenance
- reviewer transcript 可追蹤
- review 失敗不污染 target
- 多個 reviewer 可並行
- 後續可 query/blame/recover
- 貼合 AIT 的 attempt model

資料模型應支援：

```text
target_attempt_id -> review_attempt_id
```

一個 target attempt 可以有多個 review attempts。

## 12. Proposed Data Model

`attempt_reviews` 欄位草案：

- `id`
- `target_attempt_id`
- `review_attempt_id` nullable
- `mode`: `light` / `adversarial` / `multi`
- `budget`: `quick` / `standard` / `deep`
- `profiles_json`
- `reviewer_adapter`
- `reviewer_agent_id`
- `risk_level`: `low` / `medium` / `high` / `critical`
- `risk_score`
- `risk_reasons_json`
- `status`: `queued` / `running` / `passed` / `blocked` / `warning` / `failed` / `overridden`
- `blocking`: boolean
- `artifact_ref`
- `baseline_ref`
- `target_head_oid`
- `base_ref_oid`
- `policy_hash`
- `baseline_policy_hash`
- `reviewer_model` nullable
- `created_at`
- `completed_at`
- `summary`

`attempt_review_findings` 欄位草案：

- `id`
- `review_id`
- `severity`: `critical` / `high` / `medium` / `low` / `info`
- `blocking`: boolean
- `lifecycle_status`: `open` / `acknowledged` / `fixed` / `false_positive` / `accepted_risk` / `superseded`
- `path`
- `line` nullable
- `hunk_ref` nullable
- `title`
- `body`
- `evidence_ref`
- `suggested_test` nullable
- `confidence`

`attempt_review_overrides` 欄位草案：

- `id`
- `review_id`
- `reason`
- `created_at`
- `actor` nullable
- `audit_ref` nullable

## 13. Review Freshness

Review 過期條件：

- target attempt commits 變了
- base branch moved
- repo policy changed
- memory policy changed
- baseline policy changed
- sensitive path config changed
- reviewer mode/profile/budget changed
- reviewer model changed
- approved facts / durable decisions relevant to touched files changed
- findings 被 fixed/superseded 後 target 沒重新 review

因此 review table 應保存：

- `target_head_oid`
- `base_ref_oid`
- `policy_hash`
- `baseline_policy_hash`
- `baseline_ref`
- review mode/profile/budget
- reviewer adapter/model

## 14. Finding Lifecycle

Review findings 不應只是一次性文字。建議 lifecycle：

- `open`: 尚未處理
- `acknowledged`: 使用者已讀，尚未修
- `fixed`: 已由後續 attempt 修復
- `false_positive`: 判定為誤報
- `accepted_risk`: 使用者接受風險並 override
- `superseded`: target attempt 或 review 已過期，被新 review 取代

這可以避免下一次 review 一直重複吵同一個問題，也能讓 query/report 更有用。

## 15. Review Gate Policy

Review 可以放行 auto apply 的最低條件：

- attempt `verified_status == succeeded`
- attempt 有 committed changes
- workspace/ref 可讀
- 無 conflict markers
- risk policy 不要求更深 review，或 required review 已 passed
- 無 high/critical blocking finding
- reviewer findings 都有 path/hunk/reason 等可審計資訊
- baseline retrieval 沒有 policy-blocked/stale/unapproved facts 被當成 trusted baseline
- memory eval 沒有 policy-blocked/stale/unapproved facts 被選入 trusted context
- 測試證據不能只看 agent 自述，需有 command/output/exit code 或明確標記為 missing evidence

阻塞條件：

- high/critical finding
- required review 還在 queued/running
- reviewer 無法解析結構化輸出
- review agent failure
- memory policy violation
- baseline policy violation
- reviewer 發現測試證據不足且變更碰到敏感路徑
- diff 太大且未明確允許 bypass
- critical risk 但缺少 required profile review

## 16. Human Override

AI reviewer 不是絕對權威。Human override 必須是一等公民。

支援：

```bash
ait review override <review-id> --reason "accepted risk"
```

Override 必須：

- 寫入 audit trail
- 顯示在 report/status
- 可 query
- 不修改原始 review finding
- 不把 failed review 偽裝成 passed review，而是標記為 overridden

可 query 範例：

```bash
ait query 'review.status="overridden"'
ait query 'review.override=true'
```

## 17. Safety Risks And Failure Modes

主要風險與失敗模式：

- prompt injection 誘導 reviewer 放行
- memory/context poisoning
- transcript summary 失真
- reviewer false negative
- reviewer false positive
- evidence laundering：agent 宣稱已測試但沒有證據
- policy drift：repo config 被設得太寬
- secret leakage：raw transcript/memory 未完整 redacted
- audit gap：decision report 有結論但缺少原始材料連結
- consensus failure：多 reviewer 互相矛盾但系統誤放行
- review fatigue：太多低品質 warning 造成使用者忽略真正風險
- baseline contamination：未審核或惡意 memory 被當成 trusted baseline
- baseline skew：producer 和 reviewer 拿到互相矛盾的 domain assumptions
- stale domain knowledge：舊決策被錯誤套用到新架構

## 18. Evaluation Strategy

建議驗證方式：

- 建 adversarial review benchmark
- 每個 case 包含 vulnerable diff、惡意 prompt/comment、誤導 memory、expected findings
- 衡量 finding recall
- 衡量 false positive rate
- 衡量 evidence completeness
- 衡量 memory contamination rate
- 衡量 blocked memory source 被選入 recall 的次數，理想值為 0
- 衡量 trusted baseline contamination rate，理想值為 0
- 衡量 summary fidelity
- 衡量 human Staff reviewer agreement
- 衡量 review latency 與使用者等待時間
- 衡量 review fatigue：每次 review 產生多少 non-actionable warnings
- 衡量 risk scoring calibration：low/medium/high/critical 與實際 defect severity 的一致性
- 衡量 baseline usefulness：reviewer 因 baseline 找到 domain-specific bug 的比例

## 19. MVP Scope

MVP 應包含：

- `ait review attempt <selector>`
- `latest-reviewable` selector
- deterministic risk scan
- risk level / risk reasons
- reviewer-specific trusted baseline snapshot
- review artifact 保存
- structured findings
- high/critical blocking gate
- `ait run --review risk-based --apply auto` 整合
- `ait run --review adversarial --apply auto` 整合
- report/status 顯示 review 結果與 baseline ref
- human override audit trail

MVP 不應包含：

- 自動修復 findings
- 自動相信 reviewer 結論
- GitHub PR inline comment 整合
- 所有 run 預設同步 review
- 把 review failure 混入 `verified_status`
- 每次都 multi-reviewer consensus
- 把所有長期記憶無差別餵給 reviewer
- 長期 finding dedup 的完整智慧化，只需保留 lifecycle 欄位

## 20. Recommended Default

建議預設：

- `ait run` 不自動跑 adversarial review
- low-risk attempt 不阻塞
- `ait apply` 不因沒有 review 而失敗，除非 repo policy 要求
- `ait review attempt latest-reviewable` 是手動入口
- `ait run --review risk-based --apply auto` 是推薦高安全模式
- `ait run --review adversarial --apply auto` 是 opt-in 強審查模式
- critical risk 才建議 multi-reviewer
- reviewer 使用 shared trusted baseline + role-specific retrieval，不直接共享 producer 的全部記憶與推理

最終產品定位：

> 平常不打擾；當使用者要 auto-apply、改到敏感檔案、或準備交付重要變更時，才啟動風險分級 review；高風險才升級為對抗式 AI review。所有 reviewer 都從同一個可追溯、經 policy 過濾的 repo baseline 出發，但依角色取得不同 context。
