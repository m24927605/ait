# AIT Review Orchestration Phase 0 Implementation Spec

Status: Proposed implementation spec

Phase 0 的目的不是寫 runtime code，而是把設計轉成可執行規格。完成 Phase 0 後，coding agent 應能根據 Phase 1 spec 開始第一個 vertical slice，而不需要重新解讀產品方向。

## Objective

建立 review orchestration 的實作基準：

- 明確分離 verifier 與 review gate。
- 明確定義 Phase 1-5 的實作邊界。
- 明確定義第一個可合併 slice。
- 明確記錄何時才引入 LLM reviewer。
- 明確記錄 shared trusted baseline + role-specific retrieval 原則。

## Non-Goals

Phase 0 不做：

- 不新增 Python module。
- 不新增 CLI command。
- 不新增 DB migration。
- 不修改 `ait run`、`ait apply`、`ait recover` 行為。
- 不呼叫 LLM。
- 不呼叫 network。
- 不變更 memory policy runtime。

## Files To Change

Phase 0 只允許文件變更：

- `docs/adversarial-code-review-design.md`
- `docs/adversarial-code-review-mvp-plan.md`
- `docs/adversarial-code-review-phase0-spec.md`
- `docs/adversarial-code-review-phase1-spec.md`
- `docs/adversarial-code-review-phase2-spec.md`
- `docs/adversarial-code-review-phase3-spec.md`
- `docs/adversarial-code-review-phase4-spec.md`
- `docs/adversarial-code-review-phase5-spec.md`

## Files Not To Change

Phase 0 不應修改：

- `src/**`
- `tests/**`
- `pyproject.toml`
- `.github/**`
- `.ait/**`

## Required Design Decisions

Phase 0 必須固定以下決策：

- First implementation slice is `ait review attempt latest-reviewable --format json`.
- Phase 1 has no DB migration and no LLM.
- Phase 2 persists review data and adds apply gate, still no LLM.
- Phase 3 introduces the first real single LLM reviewer.
- Phase 4 wires LLM review into risk-based async orchestration.
- Phase 5 introduces multi-reviewer profiles only for critical risk.

## Required Contracts To Define

Phase 0 文件必須定義：

- `latest-reviewable` selector semantics.
- Phase 1 JSON output contract.
- Risk reason object shape.
- Review status enum.
- Finding severity enum.
- Finding lifecycle enum.
- Baseline artifact purpose.
- Override audit trail semantics.
- Phase-specific test commands.

## Acceptance Checklist

文件驗收：

- 每個 phase 都有 objective、non-goals、implementation scope、test acceptance、review checklist。
- 文件明確寫出 review failure 不得改 `verified_status`。
- 文件明確寫出 reviewer 不應讀取未過濾的全部 memory。
- 文件明確寫出 `ait review latest` 不作為 MVP 主入口。
- 文件明確寫出 `ait run` 預設不阻塞。
- 文件明確寫出 Phase 3 才有真正 LLM reviewer。

## Suggested Review

Phase 0 PR 應以設計審查為主：

- 產品語意是否清楚？
- Phase boundary 是否能降低 coding agent 發散？
- 是否有過早引入 LLM、DB、daemon 或 apply gate？
- 是否遺漏 failure mode？
- 是否能直接切出 Phase 1 coding task？

## Verification Commands

Phase 0 沒有 runtime tests。建議只做文件結構檢查：

```bash
rg -n "^#|^##|Phase 3|LLM reviewer|latest-reviewable|verified_status" docs/adversarial-code-review-*.md
git diff -- docs/adversarial-code-review-*.md
```
