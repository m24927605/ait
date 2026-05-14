# 05 - 平行 Agent

## 痛點

Claude Code 和 Codex 如果同時在同一個 checkout 裡改檔案，很容易互相覆蓋，最後也很難比較誰的結果比較好。

## Demo 專案

這個範例的專案放在：

```text
05-parallel-agents/workspace/
```

Claude Code 和 Codex 都會建立 `approach.txt`，但 AIT 會把兩邊的結果放進不同的 attempt worktree。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `05-parallel-agents/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"parallel approach"' --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
ait attempt list --format table --limit 5
```

講解時可以帶觀眾看：

- 兩個 attempts 都從同一個 base revision 開始。
- 每個 attempt 都有自己的 `workspace_ref`。
- 兩個 attempts 都修改 `approach.txt`，但結果互不覆蓋。
- 人類可以先比較，再決定要不要 apply。

## Demo 重點

AIT 把平行 agent 工作變成可比較的候選結果，而不是讓它們在同一個 checkout 裡互搶檔案。
