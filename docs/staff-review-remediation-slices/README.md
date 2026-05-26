# Staff Review Remediation Slice Index

狀態：Ready for implementation planning
日期：2026-05-26

這組文件把 Staff 級跨職能審視發現的高影響問題，轉成可設計、可實作、可測試、
可驗收、可 code review 的小 slice。目標不是一次大改，而是讓每個 PR 都能獨立
驗證，逐步把 AIT 推向「可靠、容易理解、值得安裝」的開發者工具。

## Scope

這組 slice 覆蓋下列問題：

1. Raw Claude/Codex transcript 可能繞過 redaction 進入 memory/report/review。
2. Release gate 仍偏人工，PyPI/npm/wheel/global install smoke 未自動化。
3. Python 3.14+ 與 npm postinstall 對第一次安裝造成高摩擦。
4. `ait run`、`status`、`attempt show` 的 human/JSON 預設與日常心智模型不一致。
5. `apply/recover/resume/continue` 的下一步指令、attempt handle、workspace 概念不一致。
6. SQLite migration 缺少舊版 populated DB 升級驗證。
7. Reviewer adapter 預設繼承 env 太寬。
8. README/site facts/install tag/command docs 有版本與能力漂移。
9. 測試缺少真實 shell、PyPI/npm install、dirty repo、失敗 agent、跨 terminal 場景。
10. 公開 positioning 容易高於目前實際 gate。

## Non-goals

- 不在這組 slice 內新增 SaaS、telemetry、remote sync、hosted dashboard。
- 不把 browser console mutation、automatic merge、automatic push 偷渡進來。
- 不重寫整個 CLI 架構；只在必要範圍內收斂 daily path 與安全 gate。
- 不刪除已發布 JSON 欄位；machine contract 只能 additive 或明確 versioned。
- 不為了追求單一 PR 完成度而把 slice 合併成大 refactor。

## Required implementation order

不可跳過安全與 release gate，因為後續 UX 改動會增加使用量與外部安裝風險。

1. [00 Quality Review Standard](00-quality-review-standard.md)
2. [01 Transcript Redaction Boundary](01-transcript-redaction-boundary.md)
3. [02 Release And Install Smoke Gates](02-release-and-install-smoke-gates.md)
4. [03 First Success CLI Output](03-first-success-cli-output.md)
5. [04 Recovery Apply Mental Model](04-recovery-apply-mental-model.md)
6. [05 SQLite Migration Upgrade Safety](05-sqlite-migration-upgrade-safety.md)
7. [06 Reviewer Env Sandbox Policy](06-reviewer-env-sandbox-policy.md)
8. [07 Docs Positioning Drift Control](07-docs-positioning-drift-control.md)

## Slice quality bar

每個 slice 必須達到 100/100 才能 merge。低於 100 分時，不是放寬標準，而是縮小
scope、補測試、或拆成下一個更小 slice。

| 類別 | 分數 | Gate |
| --- | ---: | --- |
| Scope control | 15 | 只完成本 slice；沒有 unrelated refactor、format churn、後續 slice 功能。 |
| Design fit | 15 | 設計符合既有 AIT worktree/ledger/recovery/review 架構，不建立平行系統。 |
| UX contract | 15 | 人類輸出可掃讀、有唯一下一步；machine output additive 且可版本化。 |
| Safety/security | 15 | secrets 不外洩；不放寬 apply/review gate；不把 raw data 推入 memory/report。 |
| Tests | 25 | 覆蓋 happy path、failure path、regression、JSON/text contract、release 或 migration smoke。 |
| Reviewability | 10 | diff 小、命名清楚、file ownership 清楚、final response 能逐項對照驗收。 |
| Verification | 5 | 跑完指定 commands；未跑必須說明原因，且不得宣稱完成。 |

## Definition of Done

每個 slice 完成後，PR 或 coding agent final response 必須包含：

- Modified files
- Implemented scope
- Explicitly out-of-scope items
- Tests run
- Acceptance checklist result
- 100/100 rubric self-score with evidence
- Residual risks
- Follow-up slice, if any

## Global review rules

- 任何 touching transcript、memory、review、report 的 PR 都要優先審 secret leakage。
- 任何 touching publish/install/npm/PyPI 的 PR 都要跑 release smoke 或明確標示未跑。
- 任何 touching CLI defaults 的 PR 都要確認 TTY human path 與 `--json` path 兼容。
- 任何 touching SQLite schema 的 PR 都要有 old populated DB fixture 或 rollback rationale。
- 任何 touching docs positioning 的 PR 都要確認 README/site/package metadata 不互相漂移。

## Coding agent prompt template

```text
請只實作 docs/staff-review-remediation-slices/<slice>.md。

嚴格遵守：
- 只完成該 slice 的 Objective / Acceptance。
- 只修改 Files To Change。
- 不修改 Files Not To Change。
- 不實作後續 slice。
- 新增或更新該 slice 要求的測試。
- 跑 Verification Commands。
- final response 必須列出 modified files、tests、acceptance checklist、100/100 rubric、residual risks。
```

