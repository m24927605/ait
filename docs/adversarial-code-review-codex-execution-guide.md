# AIT Review Orchestration Codex Execution Guide

Status: Proposed execution guide

本文定義如何請 Codex AI agent 實作 `AIT Risk-Based Pre-Apply Review Orchestration`，目標是用可控的小 slice、明確測試與必要的獨立 review，把實作品質穩定推近 90%+。

## Executive Rule

不要請 agent 一次實作整個 phase，更不要一次實作整個 review orchestration。

可靠做法是：

```text
Phase 1A -> implement -> targeted tests -> review
Phase 1B -> implement -> targeted tests -> review
Phase 1C -> implement -> targeted tests -> review
...
```

每次只交付一個 work-order slice，並用對應文件驗收。

## Execution Strategy

本文不指定任何執行設定。品質策略只依賴任務切片、測試、scope control 與 review gate。

建議執行分工：

| 工作 | 建議做法 | 說明 |
| --- | --- | --- |
| Phase 1 implementation | 一個 slice 一次實作 | 範圍小、deterministic、無 DB/LLM/apply gate |
| Phase 2A-2C implementation | 一個 slice 一次實作，測試要嚴格 | DB/baseline 需要 migration 與 trust-boundary tests |
| Phase 2D apply gate | 實作後做獨立 code review | gate failure path 風險高 |
| Phase 3A-3C parser/fake reviewer | 先 fake reviewer，再真 reviewer | parser tests 要 fail closed |
| Phase 3D real reviewer | 實作後做獨立 code review | prompt/invocation/artifact 邊界需仔細審 |
| Phase 4 orchestration | 再拆小，避免一次做完 | async/run/apply/status 複雜 |
| Phase 5 multi-reviewer | 再拆小，嚴格控 scope | consensus/lifecycle/report 容易過度設計 |

如果某個 slice 仍然太大，應先拆更小，而不是依賴調高執行設定。

## Required Workflow Per Slice

每個 slice 固定流程：

1. Read the phase spec.
2. Read the phase work-order.
3. Inspect existing code patterns before editing.
4. Implement only the current slice.
5. Add or update tests required by the slice.
6. Run targeted tests.
7. Run listed regression tests when practical.
8. Report changed files, tests run, and any known gaps.
9. Request or perform independent review for risky slices.

不得跳過第 3 步。AIT repo 已有許多既有 patterns，coding agent 必須先讀現有 CLI、DB、policy、landing、test helper 寫法。

## Required Prompt Template

交給 Codex agent 的 prompt 建議使用：

```text
請只實作 <slice-id>，例如 Phase 1A。

必讀文件：
- docs/adversarial-code-review-agent-handoff.md
- docs/adversarial-code-review-phase<N>-spec.md
- docs/adversarial-code-review-phase<N>-work-orders.md

任務：
- 只完成 <slice-id> 的 Objective / Acceptance。
- 嚴格遵守該 slice 的 Files To Change / Files Not To Change。
- 不要做下一個 slice。
- 不要擴大 scope。

禁止：
- 不要修改 verified_status 語意。
- 不要新增未要求的 DB migration。
- 不要呼叫 LLM 或 network，除非該 slice 明確要求。
- 不要修改 ait run/apply/recover 預設行為，除非該 slice 明確要求。

完成條件：
- 新增或更新必要 tests。
- 執行該 slice 的 Verification Commands。
- 回報 changed files、tests run、known gaps。
```

## Phase 1 Recommended Execution

Phase 1 必須按順序實作：

1. `Phase 1A: CLI Surface And Empty Handler`
2. `Phase 1B: Selector Resolution`
3. `Phase 1C: Changed Files And JSON Contract`
4. `Phase 1D: Risk Scoring V0`
5. `Phase 1E: Regression Hardening`

不要合併 1A-1D 到同一個 PR。Phase 1 的品質關鍵是：每一步都能獨立 review，且每一步都沒有 DB/LLM/apply gate。

Phase 1 每個 PR 的必查點：

- `ait review latest` 沒有被新增。
- `latest-reviewable` 語意被測試保護。
- JSON contract deterministic。
- risk reason codes 是 stable strings。
- `ait run` / `ait apply` 未被改動。

## Phase 2 Recommended Execution

Phase 2 必須按順序實作；Phase 2D 必須做獨立 code review。

順序：

1. `Phase 2A: Review Schema And Repositories`
2. `Phase 2B: Persist Deterministic Review Result`
3. `Phase 2C: Baseline Snapshot V1`
4. `Phase 2D: Review Policy And Apply Gate`
5. `Phase 2E: Report And Status Integration`

Phase 2 不能跳過 baseline tests。Shared trusted baseline 是此功能的核心價值，不能只做 schema/apply gate。

Phase 2D review 必查：

- review policy disabled by default。
- missing review 不會影響 apply，除非 policy 要求。
- blocked/failed required review hold，而不是 silent apply。
- override 有 audit trail。
- `verified_status` 不受 review status 影響。

## Phase 3 Recommended Execution

Phase 3 開始有真正 LLM reviewer，但必須先做 fake reviewer。

順序：

1. `Phase 3A: Structured Output Parser`
2. `Phase 3B: Reviewer Brief Rendering`
3. `Phase 3C: Fake Reviewer Invocation`
4. `Phase 3D: Real Single Reviewer Adapter`
5. `Phase 3E: Gate Hardening`

不要直接從 Phase 3D 開始。沒有 parser fail-closed tests 和 fake reviewer coverage，真 reviewer 實作品質無法穩定。

Phase 3 必查：

- malformed reviewer output fails closed。
- high/critical finding missing path/title/body fails closed。
- producer transcript 是 advisory/evidence，不是 trusted fact。
- reviewer 不能修改 target attempt workspace。
- 真 reviewer 是 opt-in。

## Phase 4 Recommended Execution

Phase 4 必須拆小實作，不應一次完成整個 orchestration。

順序：

1. `Phase 4A: Run Flag And Synchronous Required Gate`
2. `Phase 4B: Review Queue V0`
3. `Phase 4C: Async Run Integration`
4. `Phase 4D: Policy And Report Hardening`

Phase 4 最容易破壞 UX。原則：

- low-risk run 不應等 LLM。
- review omitted 時，既有 `ait run` 行為不變。
- auto apply 在 required review incomplete 時 hold。
- status/report 必須解釋為什麼 hold。

不要一開始就做 daemon-heavy queue。可以先做 simple queue 或 synchronous required gate，等語意穩定再進一步。

## Phase 5 Recommended Execution

Phase 5 必須拆小實作，避免把 consensus、lifecycle、query、report 全塞進同一個 PR。

順序：

1. `Phase 5A: Profile Policy`
2. `Phase 5B: Multi-Reviewer Orchestration With Fake Reviewers`
3. `Phase 5C: Finding Lifecycle Commands`
4. `Phase 5D: Review Query And Report Refinement`

Phase 5 必須避免 review fatigue。Multi-reviewer 不應成為 default，只應由 policy/risk 觸發。

必查：

- consensus fails closed。
- disagreement visible and actionable。
- accepted risk 不等於 passed。
- lifecycle update 不刪除原始 finding。
- query/report 幫助 human triage。

## When A Slice Is Safe To Implement Directly

以下類型通常適合直接交給單一 coding agent 實作：

- 新增 small CLI parser surface。
- 實作 deterministic selector。
- 實作 JSON formatting。
- 實作 pure risk scoring。
- 實作 parser with clear tests。
- 實作 simple repository CRUD。
- 實作 fake reviewer fixtures。

條件是：

- slice 小。
- tests 明確。
- 不碰 apply gate / async / consensus。

## When Independent Review Is Required

以下 slice 完成後必須做獨立 code review：

- DB migration。
- Apply gate。
- Baseline trust policy。
- LLM reviewer prompt/brief。
- Reviewer output parser fail-closed behavior。
- Async queue。
- `ait run --review risk-based --apply auto`。
- Override/audit behavior。
- Multi-reviewer consensus。

獨立 review 應採 code-review stance：先找 bug、regression、missing tests，再看架構美感。

## Hard Stop Conditions

Coding agent 遇到以下情況必須停下來，不要自行延伸：

- 需要修改 `verified_status` semantics。
- 需要讓所有 `ait run` 預設 review。
- 需要在 Phase 1/2 呼叫 LLM。
- 需要在 Phase 1 新增 DB migration。
- 需要在 Phase 3 前新增 reviewer adapter。
- 需要讓 reviewer 寫 target attempt workspace。
- 需要把 candidate/stale/policy-blocked memory 放入 trusted baseline。
- 需要 direct network access in AIT core。

## Required Final Report Per Slice

每個 coding agent 完成 slice 後， final response 必須包含：

```text
Slice: Phase NX
Changed files:
- ...

Tests run:
- ...

Result:
- passed / failed

Known gaps:
- ...

Scope confirmation:
- Did not change verified_status semantics.
- Did not add out-of-scope DB/LLM/apply/queue behavior.
```

## Recommended First Codex Task

第一個實作任務應該是 Phase 1A：

```text
請只實作 docs/adversarial-code-review-phase1-work-orders.md 的 Phase 1A: CLI Surface And Empty Handler。

必讀：
- docs/adversarial-code-review-agent-handoff.md
- docs/adversarial-code-review-phase1-spec.md
- docs/adversarial-code-review-phase1-work-orders.md

只新增 `ait review attempt <selector>` CLI surface 和空 handler。
不要實作 selector。
不要做 risk scoring。
不要新增 DB。
不要呼叫 LLM。
不要修改 apply/run/verifier。

完成後跑：
PYTHONPATH=src uv run pytest tests/test_cli_review.py -q
```

Phase 1A 完成且 review 通過後，再交 Phase 1B。這種節奏比一次交整個 Phase 1 更能穩定達到高品質。
