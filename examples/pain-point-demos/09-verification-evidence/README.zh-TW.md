# 09 - 對抗式審查

## 痛點

Agent 產生的修改看起來可能很合理，但仍然需要被挑戰：有沒有測試、證據夠不夠、是否只是自信地掩蓋了風險。

## Demo 專案

這個範例的專案放在：

```text
09-verification-evidence/workspace/
```

Claude Code 會建立 `src/multiply.js`，但不新增測試、也不執行測試。接著 demo 會對這個 attempt 執行 AIT adversarial review。為了讓現場 demo 穩定重現，`run.sh` 會使用 AIT 內建的 deterministic reviewer adapter，固定產生一個 blocking finding。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `09-verification-evidence/workspace/` 裡執行：

```bash
ait query --on attempt 'title~"risky multiply change"' --format table
ait attempt show <attempt-id>
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
```

講解時可以帶觀眾看：

- `ait attempt show` 先呈現原本 agent attempt 與它留下的 evidence。
- `evidence_summary.observed_tests_run` 顯示 AIT 是否觀察到測試執行。
- `review.mode="adversarial"` 顯示這個 attempt 被對抗式審查挑戰過。
- `review.status="blocked"` 顯示審查沒有直接接受這個結果。
- `ait review finding list` 會列出需要處理的 blocking finding。

## Demo 重點

AIT 可以保留 agent 的成果，同時另外記錄一份對抗式審查，明確指出這個結果是否安全到可以被接受。
