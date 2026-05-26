# Slice 00: Quality Review Standard

狀態：Ready for implementation
目標：建立後續所有 remediation slice 的設計、測試、驗收與 review 標準。

## Objective

定義一套「100 分品質」標準，讓後續每個 slice 在開始實作前就知道：

- 哪些設計邊界不可破壞。
- 哪些測試是最低要求。
- 哪些輸出與資料 contract 必須維持。
- reviewer 應如何判斷 PR 是否可 merge。

本 slice 是文件與 process gate，不改產品程式碼。

## Files To Change

- `docs/staff-review-remediation-slices/README.md`
- `docs/staff-review-remediation-slices/00-quality-review-standard.md`

## Files Not To Change

- `src/ait/**`
- `tests/**`
- `.github/workflows/**`
- package metadata

## Design Standard

每個後續 slice 都必須先回答：

1. 使用者可見行為改變是什麼？
2. Machine-readable contract 是否 additive？
3. 哪些 existing tests 代表不能破壞的 contract？
4. 新增測試如何證明 failure path 不會靜默成功？
5. 是否會把 local secrets、workspace path、ownership token、raw transcript 放到預設 human output？
6. rollback 是「停用讀取新資料」還是需要 migration？

## Review Standard

Reviewer 必須逐項檢查：

- Scope 是否只符合該 slice。
- 變更是否能由文件中的 evidence 與 acceptance 推導。
- 是否有測試覆蓋每個 acceptance item。
- CLI text output 是否能讓第一次使用者知道下一步。
- JSON output 是否保留既有欄位並新增必要欄位。
- 若測試無法執行，final response 是否明確說明。

## 100/100 Rubric

| 類別 | 分數 | 必須看到的 evidence |
| --- | ---: | --- |
| Scope control | 15 | PR description 指向單一 slice；diff 無 unrelated files。 |
| Design fit | 15 | 沿用現有 domain helper、CLI parser、report、DB repository pattern。 |
| UX contract | 15 | Snapshot 或 CLI smoke 證明 human output 有清楚 next step。 |
| Safety/security | 15 | 有 secret/workspace/token leakage check；failure path fail closed。 |
| Tests | 25 | Unit + CLI snapshot/smoke + regression；release/migration slice 需額外 gate。 |
| Reviewability | 10 | 每個檔案修改理由明確；沒有跨 slice hidden coupling。 |
| Verification | 5 | Verification commands 實際執行並列在 final response。 |

## Acceptance

- 每個後續 slice 都引用本標準。
- 每個後續 slice 都有自己的 Files To Change / Files Not To Change。
- 每個後續 slice 都有具體 Verification Commands。
- 後續實作不得用「品質 100」作為口號，必須用 rubric 證明。

## Verification Commands

```bash
git status --short
```

