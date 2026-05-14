# 04 - 調查結果重用

## 痛點

Claude 已經查過一次問題，換 Codex 接手時卻又從頭看起。這不只浪費時間，也容易讓兩個 agent 得出不一致的結論。

## Demo 專案

這個範例的專案放在：

```text
04-memory-reuse/workspace/
```

Claude Code 會先記錄一個 auth retry 的調查結論，AIT 將它保存成本機 repo memory，接著 Codex 透過 `AIT_CONTEXT_FILE` 取得這段脈絡。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `04-memory-reuse/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"Claude: investigate auth retry"' --format table
ait query --on attempt 'title~"Codex: reuse auth retry investigation"' --format table
ait memory list --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
```

講解時可以帶觀眾看：

- Claude Code 與 Codex 是兩個獨立 attempts。
- `ait memory list` 會列出 AIT 保存的 repo memory。
- Claude Code 修改 `notes/auth-retry.md`。
- Codex 修改 `context-proof.txt`。
- Codex 的 trace 顯示它拿到了 AIT 提供的 context，而不是重新從零開始。

## Demo 重點

AIT 讓有價值的調查結果能跨 session、跨 agent 延續下去，不必靠聊天紀錄或口頭交接。
