# 01 - 變更範圍隔離

## 痛點

Agent 一次改太多、甚至刪到重要檔案時，如果直接作用在主工作目錄，現場很難判斷哪些變更是安全的、哪些需要丟掉。

## Demo 專案

這個範例的專案放在：

```text
01-blast-radius/workspace/
```

Claude Code 會被要求刪除：

```text
01-blast-radius/workspace/src/calculator.js
```

如果 `workspace/` 還不存在，執行 `./run.sh` 時會自動建立。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `01-blast-radius/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"Claude: broad risky edit"' --format table
ait attempt show <attempt-id>
```

講解時可以帶觀眾看：

- `workspace_ref`：AIT 為這次嘗試建立的隔離 worktree。
- `files.changed`：AIT 記錄到哪些檔案被新增或刪除。
- `raw_prompt_ref` / `raw_trace_ref`：這次操作留下的 prompt 或 trace 證據。
- 在 apply 之前，這些高風險修改不會直接進入主 workspace。

## Demo 重點

AIT 不是要你相信 agent 說了什麼，而是把高風險變更先收進一個可查、可比較、可丟棄的 attempt。
