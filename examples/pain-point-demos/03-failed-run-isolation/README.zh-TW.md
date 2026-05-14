# 03 - 失敗結果隔離

## 痛點

Agent 做到一半失敗時，最麻煩的是主工作目錄已經被改壞：測試壞了、檔案半成品留下來，還要手動清理。

## Demo 專案

這個範例的專案放在：

```text
03-failed-run-isolation/workspace/
```

Codex 會被要求在隔離 attempt 裡故意改壞 `test/calculator.test.js`。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `03-failed-run-isolation/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"Codex: intentionally broken test attempt"' --format table
ait attempt show <attempt-id>
```

講解時可以帶觀眾看：

- `workspace_ref`：失敗結果被保存在這個隔離 worktree。
- `files.changed`：壞掉的測試檔被 AIT 記錄下來。
- `raw_trace_ref`：Codex 的執行 trace，包含測試失敗的線索。
- 失敗 attempt 仍然可追溯，但不會默默污染主 workspace。

## Demo 重點

AIT 讓失敗結果留下證據，而不是留下爛攤子。
