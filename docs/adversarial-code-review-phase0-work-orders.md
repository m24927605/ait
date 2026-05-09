# AIT Review Orchestration Phase 0 Work Orders

Status: Proposed work orders

Phase 0 是文件與規格收斂階段。目標是讓後續 coding agent 不需要猜測 feature 邊界。

## Phase 0A: Baseline Design Bundle

### Objective

建立完整設計文件與 MVP phase plan。

### Files To Change

- `docs/adversarial-code-review-design.md`
- `docs/adversarial-code-review-mvp-plan.md`

### Files Not To Change

- `src/**`
- `tests/**`

### Acceptance

- Design doc 明確定位為 proposed design。
- MVP plan 明確列出 Phase 0-5。
- 明確寫出 Phase 3 才有 LLM reviewer。
- 明確寫出 Phase 4 才有 risk-based async orchestration。
- 明確寫出 shared trusted baseline + role-specific retrieval。

### Review Checklist

- 是否有把 proposed feature 寫成已實作？
- 是否有把 `ait review latest` 當主入口？
- 是否有讓所有 run 預設阻塞？
- 是否有把 review failure 混入 verifier？

## Phase 0B: Phase-Specific Specs

### Objective

為 Phase 0-5 建立 implementation specs。

### Files To Change

- `docs/adversarial-code-review-phase0-spec.md`
- `docs/adversarial-code-review-phase1-spec.md`
- `docs/adversarial-code-review-phase2-spec.md`
- `docs/adversarial-code-review-phase3-spec.md`
- `docs/adversarial-code-review-phase4-spec.md`
- `docs/adversarial-code-review-phase5-spec.md`

### Acceptance

每份 spec 都必須包含：

- Objective
- Non-goals
- Files to change
- Files not to change
- Contract details
- Required tests
- Verification commands
- Implementation review checklist

### Review Checklist

- Phase 1 是否足夠小？
- Phase 2 是否仍然無 LLM？
- Phase 3 是否 opt-in？
- Phase 4 是否避免所有 run 等 LLM？
- Phase 5 是否限制 multi-reviewer 只用於 critical/high-value paths？

## Phase 0C: Agent Handoff Playbook

### Objective

建立給 coding agent 使用的共通 handoff/playbook。

### Files To Change

- `docs/adversarial-code-review-agent-handoff.md`
- `docs/adversarial-code-review-phase0-work-orders.md`
- `docs/adversarial-code-review-phase1-work-orders.md`
- `docs/adversarial-code-review-phase2-work-orders.md`
- `docs/adversarial-code-review-phase3-work-orders.md`
- `docs/adversarial-code-review-phase4-work-orders.md`
- `docs/adversarial-code-review-phase5-work-orders.md`

### Acceptance

- 每個 phase 都拆成 PR-sized slices。
- 每個 slice 都有禁止事項。
- 每個 slice 都有 tests 或文件驗收方式。
- 每個 slice 都有 review checklist。

### Verification Commands

```bash
rg -n "^#|^##|^###|Objective|Acceptance|Review Checklist|Files To Change|Files Not To Change" docs/adversarial-code-review-*.md
git diff -- docs/adversarial-code-review-*.md
```

## Phase 0 Exit Criteria

Phase 0 完成後，下一個 coding agent 應可直接接 Phase 1A，不需要重新討論：

- CLI 名稱
- selector 語意
- Phase 1 scope
- 不碰 DB/LLM/apply gate 的限制
- risk scoring v0 的方向
