# AIT Memory Temporal Ranking 設計、實作與驗收

## 目的

AIT 已經具備長期記憶的基礎欄位：

- `memory_facts.valid_from`
- `memory_facts.valid_to`
- `memory_facts.superseded_by`
- `memory_facts.created_at`
- `memory_facts.updated_at`
- `memory_facts.status`
- `memory_facts.confidence`

目前也已經能透過 `ait memory eval` 檢查 selected fact 是否 stale、superseded、expired 或 policy-blocked。

但 recall 排序還缺少正式的時間權重模型。這份文件定義下一個實作切片：在 `build_relevant_memory_recall` 中加入 deterministic temporal ranking，讓 AIT 選入下一次 agent context 的記憶同時考慮語意相關性、時間新鮮度、記憶種類、confidence 與 evidence。

## 非目標

本切片不做以下事情：

1. 不導入外部向量資料庫。
2. 不改 SQLite schema。
3. 不使用 LLM-as-judge。
4. 不改 `ait memory search` 的一般搜尋排序，避免破壞使用者檢索預期。
5. 不把所有最新內容都排到最前面；時間只是權重之一，不是唯一排序依據。
6. 不自動接受或拒絕 memory facts。

## 設計原則

### 1. 時間權重只影響 recall，不影響 search

`ait memory search` 是人類探索工具，應盡量回傳純相關性結果。

`build_relevant_memory_recall` 是 agent context injection 的來源，應更嚴格地避免過期或低價值記憶進入 prompt。

因此本切片先只改 recall selection order。

### 2. 不同記憶種類有不同時間衰減

時間權重不能簡化成「越新越好」。不同 `kind` 的衰減不同：

| kind | 時間策略 |
| --- | --- |
| `current_state` | 強衰減，舊狀態很容易過期 |
| `workflow` | 中等衰減，流程會變但不一定每天變 |
| `rule` | 低到中衰減，規則穩定但仍可能被取代 |
| `decision` | 低衰減，架構決策通常長期有效 |
| `failure` | 中等衰減，失敗經驗有用但不應壓過成功規則 |
| `entity` | 中等衰減，entity 可能因重構改變 |
| `manual` | 最低衰減，使用者手動記憶有較高穩定性 |
| `note` | 中等衰減，兼容舊記憶層 |

### 3. 過期與 superseded 不靠權重處理

`valid_to`、`superseded_by`、`status != accepted` 是 hard governance，不是 soft ranking。

也就是說：

- expired memory 不應靠低分排序，而應被跳過。
- superseded memory 不應靠低分排序，而應被跳過。
- rejected/candidate structured facts 不應注入。

### 4. 相關性仍是主軸

Temporal ranking 不應讓低相關的新記憶打敗高相關的穩定記憶。

本切片採用 multiplicative factor：

```text
temporal_score = base_score * time_factor * confidence_factor * kind_factor
```

這樣 base relevance 仍是主軸，時間與治理訊號只調整排序。

## Ranking Model

### Input

每個 candidate 來自 `search_repo_memory`，包含：

- `score`
- `kind`
- `metadata.kind`
- `metadata.confidence`
- `metadata.updated_at`
- `metadata.valid_from`
- `metadata.valid_to`
- `metadata.superseded_by`
- `metadata.source_trace_ref`
- `metadata.source_commit_oid`
- `metadata.source_file_path`

### Age

使用 `updated_at` 作為主要 recency anchor。

若 `updated_at` 缺失，fallback 到 `valid_from`。

若兩者都缺失，視為未知時間，使用 neutral factor `1.0`。

### Half-life

用簡單 deterministic half-life model：

```text
time_factor = min_factor + (1 - min_factor) * 0.5 ** (age_days / half_life_days)
```

建議 half-life：

| kind | half_life_days | min_factor |
| --- | ---: | ---: |
| `current_state` | 14 | 0.35 |
| `workflow` | 45 | 0.50 |
| `failure` | 45 | 0.45 |
| `entity` | 60 | 0.50 |
| `rule` | 90 | 0.60 |
| `decision` | 180 | 0.70 |
| `manual` | 365 | 0.85 |
| `note` | 90 | 0.55 |

### Confidence Factor

| confidence | factor |
| --- | ---: |
| `manual` | 1.08 |
| `high` | 1.05 |
| `medium` | 0.92 |
| `low` | 0.78 |
| unknown | 0.90 |

### Kind Factor

| kind | factor |
| --- | ---: |
| `decision` | 1.04 |
| `rule` | 1.03 |
| `workflow` | 1.02 |
| `manual` | 1.04 |
| `current_state` | 1.00 |
| `entity` | 0.96 |
| `failure` | 0.88 |
| note/unknown | 1.00 |

Failure memory is useful, but it should not outrank a directly relevant accepted rule unless its base relevance is much stronger.

### Evidence Factor

本切片不把 evidence factor 放進主公式，以免過度調整舊資料。但 metadata 會保留 evidence 欄位，後續可加入：

- trace evidence
- commit evidence
- file evidence
- promoted outcome evidence

### Output Metadata

Recall selected item 應增加 metadata：

- `temporal_base_score`
- `temporal_score`
- `temporal_factor`
- `temporal_age_days`
- `temporal_kind`
- `temporal_ranker`

這讓 `ait memory recall --format json` 可以被測試，也讓未來 report 可以顯示排序原因。

## 實作計畫

### Step 1: 新增 helper

在 `src/ait/memory.py` 新增：

- `_apply_temporal_ranking`
- `_temporal_ranked_item`
- `_temporal_factor`
- `_parse_memory_time`

### Step 2: 改造 recall selection

目前 `build_relevant_memory_recall` 是：

```text
search candidates
for candidate:
  validate policy/status/lint
  select until limit
```

改成：

```text
search candidates
for candidate:
  validate policy/status/lint
  add to eligible
rank eligible with temporal ranking
select top N
mark remaining eligible as over selection limit
```

### Step 3: 保持 skipped 行為

被 policy、status、lint 擋掉的項目仍要進 `skipped`。

超過 selection limit 的 eligible item 也要進 `skipped`，reason 維持 `over selection limit`。

### Step 4: 更新 retrieval event

`memory_retrieval_events.selected_fact_ids_json` 不需改 schema。

因 selected items 仍是同一批 facts，只是排序更好。

### Step 5: 測試

新增或更新測試：

1. 新近的 `current_state` 優先於同相關但很舊的 `current_state`。
2. 很舊的 `decision` 不會被過度懲罰。
3. `failure` 在同分時不應壓過 `rule`。
4. recall JSON metadata 包含 temporal ranking 欄位。
5. `status != accepted` 的 structured fact 仍被跳過，不靠時間權重處理。

## 驗收標準

1. `ait memory recall` 對同相關 memory 會優先選時間更合適者。
2. `current_state` 比 `decision/rule/manual` 更容易受時間衰減。
3. `failure` 不會在同分時壓過成功規則。
4. selected item metadata 可看見 temporal ranking 資訊。
5. `ait memory eval` 既有 stale/superseded 檢查不被破壞。
6. 所有既有測試通過。

## 5 輪文件 Review

### Review 1: Staff 架構師

問題：

- 原始設計若直接把時間權重放進 `search_repo_memory`，會同時影響人類搜尋與 agent recall。

修正：

- 限定本切片只改 `build_relevant_memory_recall`。
- `ait memory search` 保持原本相關性排序。

### Review 2: Staff LLM 工程師

問題：

- 「最新」不等於「最好」。例如 180 天前的架構決策仍可能比昨天的 failure chat 更重要。

修正：

- 加入 per-kind half-life。
- `decision`、`manual`、`rule` 衰減較慢。
- `current_state` 衰減最快。

### Review 3: Staff 後端工程師

問題：

- 改 schema 會增加 migration 和 release 風險，但目前欄位已足夠。

修正：

- 不新增 schema。
- 只使用既有 metadata 與 `memory_facts` 欄位。

### Review 4: Staff 測試工程師

問題：

- 時間相關測試容易 flaky。

修正：

- 測試資料使用固定 ISO timestamp。
- 不依賴 `utc_now()` 的當下時間去判斷邊界。
- 測試只比較明確差距，例如 5 天 vs 400 天。

### Review 5: Staff 產品/治理 Review

問題：

- Temporal ranking 若不透明，使用者不知道為什麼某記憶被選中。

修正：

- selected metadata 增加 temporal 欄位。
- `ait memory recall --format json` 可以檢查 `temporal_score`、`temporal_factor`、`temporal_age_days`。

## 最終可實作結論

本切片可以實作，因為：

1. 不改 schema。
2. 不改 general search。
3. 不依賴外部服務。
4. 測試可 deterministic。
5. metadata 可觀測。
6. 風險集中在 recall selection order，可用既有測試保護。
