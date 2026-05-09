# AIT Review Orchestration Agent Handoff Playbook

Status: Proposed execution playbook

本文定義如何把 review orchestration 的各 phase 交給 coding agent 實作，目標是把實作品質提升到可穩定 review、可逐步合併的水準。本文補充 phase specs，不取代它們。

## Quality Target

「90% 以上品質」在本功能中定義為：

- 每個 PR 都有單一清楚目標。
- PR 只改 spec 允許的檔案。
- PR 不跨 phase。
- PR 不引入未要求的 DB、LLM、daemon、apply gate 或 queue。
- PR 有對應 tests，且測試命令可直接執行。
- JSON/CLI/schema contract 有測試保護。
- Failure path 有測試，且 fail closed。
- 未啟用 review 時，既有 `ait run/apply/recover` 行為不變。
- Reviewer memory/baseline 邊界有測試，不靠口頭保證。

低於 90% 的典型徵兆：

- 一個 PR 同時做 CLI、DB、LLM、apply gate。
- 沒有 fake reviewer，就直接接真 reviewer。
- 沒有 parser fail-closed tests。
- Review failure 改動了 `verified_status`。
- 未審核 memory 被當成 trusted baseline。
- Apply gate 在錯誤時 silent allow。

## Handoff Rule

每次交給 coding agent 的任務應包含：

- phase spec path
- work-order slice id
- exact objective
- files to change
- files not to change
- acceptance tests
- verification commands
- implementation review checklist

推薦 prompt 形狀：

```text
請只實作 docs/adversarial-code-review-phaseN-work-orders.md 的 Phase NX。
遵守該 slice 的 Files To Change / Files Not To Change。
不要做下一個 slice。
完成後跑該 slice 的 targeted tests，若失敗請修到通過。
最後回報 changed files、tests run、known gaps。
```

## PR Size Budget

建議每個 PR 的大小：

- Python source: 1-4 files
- Tests: 1-3 files
- Docs: 0-1 follow-up update
- No more than one new public CLI surface per PR
- No more than one schema migration per PR

超過此範圍時，應拆成下一個 work-order slice。

## Required Pre-Review Checklist

每個實作 PR 送 review 前，作者必須回答：

- 這個 PR 屬於哪個 phase / slice？
- 是否改了 spec 禁止修改的檔案？
- 是否新增或改變 public CLI？
- 是否改變 existing defaults？
- 是否有新增 DB migration？
- 是否有新增 LLM invocation？
- 是否有新增 apply gate？
- 是否有任何 review failure 寫入 `verified_status`？
- 是否有 tests 覆蓋 failure path？
- 是否有 regression tests 證明未啟用 review 時既有流程不變？

## Required Reviewer Checklist

Reviewer 應優先檢查：

- Scope creep: 是否偷做了下一 phase。
- Fail-closed behavior: 錯誤時是否 hold/failed，而不是 allow。
- Data separation: review status 是否和 `verified_status` 分離。
- Baseline safety: trusted/advisory source 是否分清楚。
- CLI clarity: selector 和錯誤訊息是否清楚。
- Test credibility: tests 是否真的建 fixture，而不是只測 mocked happy path。

## Stop Conditions

遇到以下情況應停止實作並回到 spec：

- 需要修改 `verified_status` 語意。
- 需要讓 `ait run` 預設等待 review。
- 需要讓 reviewer 直接改 target attempt workspace。
- 需要把 candidate/stale/policy-blocked memory 當 trusted baseline。
- 需要新增 network access 到 AIT core。
- 需要在 Phase 1/2 引入 LLM。
- 需要在 Phase 1 引入 DB migration。

## Phase Dependency Rules

- Phase 1 不依賴 Phase 2-5。
- Phase 2 依賴 Phase 1 selector/risk scan。
- Phase 3 依賴 Phase 2 persistence/baseline/gate。
- Phase 4 依賴 Phase 3 fake reviewer + parser + invocation。
- Phase 5 依賴 Phase 4 policy/status/report surfaces。

不得反向依賴。例如 Phase 1 不應讀 Phase 2 review tables。

## Documentation Update Rule

若實作過程改變以下任一項，必須同步更新對應 phase spec/work-order：

- CLI contract
- JSON contract
- schema fields
- policy defaults
- risk scoring weights
- review status enum
- finding lifecycle enum
- apply gate behavior
- verification commands

## Minimal Quality Bar By Phase

- Phase 1: selector + risk scan deterministic, no persistence, no LLM.
- Phase 2: persistence/gate/baseline auditable, review disabled by default.
- Phase 3: fake reviewer tests first, real reviewer opt-in, parser fail closed.
- Phase 4: risk-based auto flow does not slow low-risk runs.
- Phase 5: multi-reviewer only for critical risk, lifecycle preserves history.
