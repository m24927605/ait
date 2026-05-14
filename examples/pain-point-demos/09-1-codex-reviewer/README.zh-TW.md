# 09-1 - Claude Code 寫程式，Codex 負責審查

## 痛點

在真實開發流程裡，很常會想讓一個 AI 先寫程式，再交給另一個 AI 挑問題。問題是，如果中間沒有明確的交接紀錄，最後很難回答幾個關鍵問題：誰寫了這段程式？誰審查過？審查有沒有擋下風險？結果能不能被事後查證？

## Demo 專案

這個範例會在自己的資料夾裡建立一個獨立專案：

```text
09-1-codex-reviewer/workspace/
```

流程分成兩段。第一段由 Claude Code 實作 `divide(a, b)`，但刻意沒有處理除以零。第二段由 AIT 啟動 Codex 進行對抗式審查，檢查這個實作是否應該被接受。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請切到 `09-1-codex-reviewer/workspace/`，用下面這些 AIT 指令查看結果：

```bash
ait query --on attempt 'title~"unsafe divide implementation"' --format table
ait attempt show <attempt-id>
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review status --format text
ait review report --attempt <attempt-id> --format json
ait review finding list --severity high --format text
ait config show --format json
ait apply <attempt-id> --mode current
```

Demo 時可以照這個順序講：

- `ait query --on attempt 'title~"unsafe divide implementation"'`：先找出 Claude Code 產生的實作紀錄。
- `ait attempt show <attempt-id>`：確認這次 attempt 的 agent、指令、狀態與修改內容。
- `ait query --on attempt 'review.mode="adversarial"'`：證明這次結果不是只有「跑完」，而是有被對抗式審查挑戰過。
- `ait query --on attempt 'review.status="blocked"'`：證明 Codex 審查後沒有直接放行這個實作。
- `ait review report --attempt <attempt-id>`：查看 Codex 審查的摘要與 adapter 來源。
- `ait review finding list --severity high`：列出真正擋下這次實作的高風險問題。
- `ait config show --format json`：確認這個 demo workspace 已要求 apply 前必須通過 review gate。
- `ait apply <attempt-id> --mode current`：實際嘗試套用，結果應該會被 hold，而不是把有 blocking finding 的結果套到目前 checkout。

## Demo 重點

這個 demo 要讓觀眾看到：AIT 不是只把 Claude Code 和 Codex 串在一起執行而已，而是把「誰實作、誰審查、審查結果為什麼擋下」全部留下可查證的紀錄。當 review gate 開啟時，AIT 還能把審查結論變成 apply 前的阻擋條件，避免有高風險 finding 的 attempt 被直接套用。
