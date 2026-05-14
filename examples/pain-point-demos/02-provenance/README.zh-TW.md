# 02 - 來源可追溯

## 痛點

Agent 跑完後，常見問題不是「有沒有改出東西」，而是事後說不清楚：當初的需求是什麼、誰跑的、改了哪些檔案、trace 在哪裡。

## Demo 專案

這個範例的專案放在：

```text
02-provenance/workspace/
```

Claude Code 會在隔離的 AIT attempt 裡建立 `notes/provenance-proof.md`。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `02-provenance/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"Claude: provenance proof"' --format table
ait attempt show <attempt-id>
```

講解時可以帶觀眾看：

- `agent_harness`：這次結果是由 Claude Code 產生。
- `files.changed`：這次 attempt 實際改了哪些檔案。
- `raw_prompt_ref` / `raw_trace_ref`：AIT 保存的 prompt 與 trace 線索。
- 事後可以用 intent 查回這次 attempt，不需要翻 terminal 紀錄。

## Demo 重點

AIT 會把一次 agent 操作整理成本機可搜尋的證據：intent、attempt、檔案變更與 trace metadata。
