# 10 - Prompt 搜尋

## 痛點

靠 shell history 或終端機捲動紀錄找舊 prompt 很不可靠；只要 session 多一點，很快就不知道當初是哪個 prompt 造成哪個結果。

## Demo 專案

這個範例的專案放在：

```text
10-prompt-search/workspace/
```

demo 會先建立一個可搜尋的 Claude Code attempt，接著用 AIT query 把它找回來。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `10-prompt-search/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"auth retry"' --format table
ait query --on attempt 'files_changed~"notes/auth-retry.md"' --format table
ait attempt show <attempt-id>
```

講解時可以帶觀眾看：

- 可以用 intent text 找回舊 attempt。
- 也可以用 changed file 找回舊 attempt。
- `raw_prompt_ref` / `raw_trace_ref` 指向 AIT 保存的 prompt 或 trace。
- 這比翻終端機歷史紀錄更穩定，也更適合團隊協作。

## Demo 重點

AIT 讓 prompt 與 attempt history 變成本機可查詢的 metadata。
