# 06 - 明確 Promotion

## 痛點

Agent 說「完成」只是代表它產生了一個結果，不代表這個結果已經被團隊接受，更不該自動進入 `main`。

## Demo 專案

這個範例的專案放在：

```text
06-explicit-promotion/workspace/
```

demo 會先產生 Claude Code 與 Codex 兩個候選 attempts，然後只接受 Claude Code 的結果進目前 branch。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `06-explicit-promotion/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"explicit promotion candidate"' --format table
ait attempt list --format table --limit 5
ait attempt show <promoted-attempt-id>
```

講解時可以帶觀眾看：

- 多個 candidate attempts 可以同時存在。
- `verified_status` 會顯示哪個 attempt 成為已接受結果。
- 如果有 `result_promotion_ref`，它就是 apply/promotion 的紀錄。
- AIT 把「agent 做完」和「人類接受」分成兩件事。

## Demo 重點

AIT 讓 apply/accept 成為明確動作；結果要進 `main`，必須先被選中。
