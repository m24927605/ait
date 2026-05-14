# 08 - 本機可查的 Provenance

## 痛點

如果 agent metadata 只能在雲端儀表板裡看，本機除錯、離線檢查或團隊內部稽核都會變得很不方便。

## Demo 專案

這個範例的專案放在：

```text
08-local-only-provenance/workspace/
```

AIT 的本機 metadata 會放在這個專案的 `workspace/.ait/`。

## 執行

```bash
./run.sh
```

## AIT 驗證流程

請在 `08-local-only-provenance/workspace/` 裡執行：

```bash
ait status --all --json
ait attempt list --format table
ait memory list --format table
```

講解時可以帶觀眾看：

- `ait status` 可以直接從本機 repo 讀出 AIT 狀態。
- adapter health 可以用 CLI 檢查。
- attempts 與 memory 不需要雲端儀表板也能查看。
- 專案內的 `.ait` 目錄就是 AIT 存放 metadata 的地方。

## Demo 重點

AIT 採 local-first 設計；重要紀錄可以直接在 repo 裡用 AIT 指令查到。
