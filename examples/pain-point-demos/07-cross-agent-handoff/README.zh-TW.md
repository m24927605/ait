# 07 - 跨 Agent Handoff

## 痛點

Claude Code 做過的決策，如果 Codex 接手時看不到，很容易重複討論、走錯方向，或做出和前面相反的判斷。

## Demo 專案

這個範例的專案放在：

```text
07-cross-agent-handoff/workspace/
```

Claude Code 會寫入並接受一份 `AGENTS.md` 決策。AIT 會把這份決策匯入 memory，之後 Codex 透過 AIT context 取得它。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `07-cross-agent-handoff/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"record calculator module decision"' --format table
ait query --on attempt 'title~"read calculator module handoff"' --format table
ait memory list --format table
ait attempt show <decision-attempt-id>
ait attempt show <codex-attempt-id>
```

講解時可以帶觀眾看：

- Claude Code 的 decision attempt 已經成為接受結果。
- `ait memory list` 會顯示由這份決策建立的 repo memory。
- Codex 是後續另一個 attempt。
- Codex 取得的是 AIT context，不是某個聊天視窗裡的隱藏狀態。

## Demo 重點

AIT 讓跨 agent 交接有明確紀錄，也能在 repo 內被查證。
