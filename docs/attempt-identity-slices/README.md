# Attempt Identity Slice Index

狀態：Draft
日期：2026-05-26

此目錄把 attempt 自動別名與自動描述拆成可獨立實作、測試、review 的小 slice。

實作順序不可跳過：

1. [01 Identity Store And Backfill](01-identity-store-and-backfill.md)
2. [02 Deterministic Description Builder](02-deterministic-description-builder.md)
3. [03 Selector Resolution For Handles](03-selector-resolution-for-handles.md)
4. [04 CLI List And Show Rendering](04-cli-list-and-show-rendering.md)
5. [05 Manual Alias Commands](05-manual-alias-commands.md)
6. [06 Status Recover Continue Integration](06-status-recover-continue-integration.md)

每個 slice 的品質標準：

- Scope 小到可以在單一 PR 中完整 review。
- 明確列出 files to change 和 files not to change。
- 新增或更新測試必須能在本機 deterministic 通過。
- 不依賴網路或外部 LLM。
- 不改動 root checkout 或使用者原始檔。
- 不移除既有 JSON 欄位。
- 不把後續 slice 的功能偷渡進來。

## 100 分實作品質門檻

每個 slice 只有在以下條件全部成立時，才視為可 merge：

| 類別 | 分數 | Gate |
| --- | ---: | --- |
| Scope control | 15 | 只完成本 slice；沒有後續 slice 功能、無 unrelated refactor、無 metadata churn。 |
| Data contract | 15 | DB/API/JSON contract additive、idempotent、可 rollback，且錯誤情境 fail closed。 |
| UX contract | 15 | 人類輸出低干擾、可掃讀；machine output 保持既有欄位；debug 邊界清楚。 |
| Tests | 25 | 覆蓋 happy path、collision、missing data、backfill/idempotency、JSON compatibility、regression cases。 |
| Safety | 15 | 不改 root checkout、不外呼 network、不依賴 LLM、不暴露 `ownership_token` 或 workspace path 到不該出現的預設輸出。 |
| Reviewability | 10 | diff 小、命名清楚、無隱性 coupling；final response 可直接對照本文件驗收。 |
| Verification | 5 | 跑完 slice 指定 commands；若未跑，必須明確說明原因且不得宣稱完成。 |

低於 100 分時不要合併。修正方式是縮小 scope、補測試或拆出下一個 slice，而不是放寬驗收。

每個 slice 完成後 final response 必須包含：

- Modified files
- Implemented scope
- Tests run
- Acceptance checklist result
- Residual risks

Coding agent prompt template：

```text
請只實作 docs/attempt-identity-slices/<slice>.md。

嚴格遵守：
- 只完成該 slice 的 Objective / Acceptance。
- 只修改 Files To Change。
- 不做 Files Not To Change。
- 不實作後續 slice。
- 新增/更新該 slice 要求的測試。
- 跑 Verification Commands。
- final response 必須列出 modified files、tests、residual risks。
```
