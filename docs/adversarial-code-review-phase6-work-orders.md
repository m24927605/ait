# AIT Review Orchestration Phase 6 Work Orders

Status: Proposed work orders

本文件定義 Phase 6 的實作切片。Phase 6 的目的不是新增更大的產品面，而是把 Phase 1-5 的 review orchestration V0 打磨成可交付、可驗收、可 debug、可長期演進的基礎能力。

每個 slice 都必須遵守：

- 不改變未啟用 review 的 `ait run` / `ait apply` / `ait recover` 預設行為。
- 不把 review failure 寫成 `verified_status=failed`。
- 不把 review status 混入 Git/provenance verifier 語意。
- 不讓 stale / malformed / missing required review silent pass。
- 不讓 reviewer 寫 target attempt workspace。
- 不把 candidate / stale / policy-blocked memory 放入 trusted baseline。
- 不在 AIT core 直接新增 network access。

## Phase 6A: Implementation Review And Stabilization

### Objective

審查 Phase 1-5 已完成實作，修正低風險瑕疵、補齊測試缺口、整理命名與錯誤訊息，確保 V0 行為穩定且不破壞既有流程。

此 slice 不應新增大功能；只做 stabilization。

### Files To Change

- `src/ait/review.py`
- `src/ait/review_policy.py`
- `src/ait/review_baseline.py`
- `src/ait/review_adapter.py`
- `src/ait/review_queue.py`
- `src/ait/cli/review.py`
- `src/ait/cli/run.py`
- `src/ait/landing.py`
- `src/ait/run_report.py`
- `tests/test_review_*.py`
- `tests/test_cli_run.py`
- `tests/test_landing.py`
- `tests/test_recover.py`

### Files Not To Change

- 不修改 verifier 的 `verified_status` 語意。
- 不修改 unrelated Git workspace apply/recover 底層流程。
- 不新增 DB schema，除非現有 Phase 1-5 schema 有明確 bug。
- 不新增 LLM adapter 行為。
- 不新增 async daemon 或 worker 功能；該功能屬於 Phase 6B。

### Acceptance

- Review disabled 時，既有 `ait run` / `ait apply` / `ait recover` 行為不變。
- `verified_status` 只代表 Git/provenance integrity。
- Review status、finding status、override status 與 verifier 狀態分離。
- 已知 malformed reviewer output 不會通過 gate。
- 已知 missing required review 不會通過 auto apply gate。
- Review artifact、baseline ref、risk reasons 的命名與 JSON shape 穩定。
- 錯誤訊息可行動，至少包含 target attempt、review id 或 selector 建議。
- 測試 fixtures 不依賴執行順序。
- 沒有與 review orchestration 無關的 refactor。

### Tests

```bash
python -m pytest tests/test_review_*.py
python -m pytest tests/test_cli_run.py tests/test_landing.py tests/test_recover.py
```

### Review Checklist

- [ ] Review disabled path 沒有新增阻塞。
- [ ] Auto apply path 只在 policy 要求時檢查 review gate。
- [ ] Manual apply path 支援 warning / override，不 silent fail。
- [ ] Review failure 沒有污染 target attempt。
- [ ] 沒有新增直接 network access。
- [ ] 所有新增或修正測試都能單獨執行。

## Phase 6B: Review Queue Worker

### Objective

讓 queued review 能被本地 worker 明確處理，支援最小可用的 background review 模型，但不引入長駐服務複雜度。

### Files To Change

- `src/ait/review_queue.py`
- `src/ait/review.py`
- `src/ait/cli/review.py`
- `src/ait/cli_parser.py`
- `tests/test_review_queue_worker.py`
- `tests/test_review_queue.py`

### Files Not To Change

- 不修改 target attempt workspace。
- 不新增外部 queue service。
- 不新增 daemon lifecycle manager。
- 不改變 `ait run` 預設同步行為；async run integration 屬於 Phase 6C / 6D 後續。

### Acceptance

- 支援：

```bash
ait review worker --once
ait review worker --max-jobs 5
```

- Worker 能找到 queued review job。
- Job lifecycle 正確更新：
  - `queued -> running -> passed`
  - `queued -> running -> blocked`
  - `queued -> running -> failed`
- Reviewer timeout、非零 exit、malformed output 都會進入可審計 failed 狀態。
- 同一 target attempt / profile / budget / baseline hash 的重複 queued job 不會被重複處理。
- Worker crash 後留下的 running job 可被後續 worker 判斷為 stale running 或 retryable failed。
- Worker 不會修改 target attempt。
- Worker output 在 CLI 中清楚顯示 processed / skipped / failed count。

### Tests

```bash
python -m pytest tests/test_review_queue_worker.py tests/test_review_queue.py
```

### Review Checklist

- [ ] Queue claim/update 具備基本一致性。
- [ ] 失敗狀態 fail closed。
- [ ] Worker 沒有依賴外部服務。
- [ ] Worker 不讀取或寫入 target attempt workspace。
- [ ] CLI output 可用於 debug。

## Phase 6C: Review Freshness

### Objective

建立 review freshness 判定，避免已過期 review 被誤用於 apply gate。

### Files To Change

- `src/ait/review_policy.py`
- `src/ait/review.py`
- `src/ait/landing.py`
- `src/ait/run_report.py`
- `src/ait/report/*`
- `tests/test_review_freshness.py`
- `tests/test_review_gate_hardening.py`

### Files Not To Change

- 不修改 attempt commit model。
- 不修改 verifier semantics。
- 不實作 long-term finding dedup 智慧化；只需能標示 stale / superseded。

### Acceptance

Review 必須在以下情況被視為 stale：

- target attempt commits 改變。
- base ref 改變。
- repo review policy hash 改變。
- baseline policy hash 改變。
- sensitive path config 改變。
- mode / profile / budget 改變。
- reviewer adapter / model 改變。
- relevant approved facts / durable decisions 改變。
- finding 被標示 fixed / superseded 後 target 沒重新 review。

Apply gate 行為：

- Required review stale 時，auto apply 必須 hold。
- Manual apply 必須顯示 stale warning，若允許 override，必須留下 audit trail。
- Stale review 不可被顯示為 passed。

Report/status 行為：

- Review freshness 顯示為 fresh / stale / unknown。
- Stale reason 必須可見。
- `baseline_ref`、`policy_hash`、`baseline_policy_hash` 必須顯示或可 query。

### Tests

```bash
python -m pytest tests/test_review_freshness.py tests/test_review_gate_hardening.py
```

### Review Checklist

- [ ] Freshness 判定不依賴 reviewer 自述。
- [ ] Stale review 不可通過 required gate。
- [ ] Freshness metadata 足以 debug。
- [ ] Manual override 與 passed 狀態分離。

## Phase 6D: Adapter Configuration

### Objective

把 reviewer adapter 從硬編碼測試路徑提升為 repo policy 可設定的受控本地 adapter config，同時維持 AIT core 不直接新增 network access。

### Files To Change

- `src/ait/policy.py`
- `src/ait/review_adapter.py`
- `src/ait/review_policy.py`
- `src/ait/cli/review.py`
- `tests/test_review_adapter_config.py`
- `tests/test_review_real_adapter.py`

### Files Not To Change

- 不在 AIT core 直接呼叫遠端 LLM API。
- 不新增 provider-specific SDK。
- 不把 API key、token 或 secrets 寫入 artifact。
- 不允許 adapter 在 target attempt workspace 內寫檔。

### Acceptance

- Repo policy 可定義 default reviewer adapter。
- Repo policy 可依 profile 選 adapter。
- Adapter config 至少支援：
  - command
  - args
  - timeout seconds
  - working directory
  - allowed environment variables
  - output contract
- Adapter 執行時：
  - 從 stdin 或指定 brief file 取得 reviewer brief。
  - stdout / stderr 被保存為 artifact reference。
  - nonzero exit 轉成 failed review。
  - timeout 轉成 failed review。
  - malformed structured output 轉成 failed review。
- Adapter working directory 不可是 target attempt workspace。
- Missing adapter config 必須產生 actionable error，不可 silent allow。

### Tests

```bash
python -m pytest tests/test_review_adapter_config.py tests/test_review_real_adapter.py
```

### Review Checklist

- [ ] Adapter config 不暴露 secrets。
- [ ] AIT core 不直接新增 network access。
- [ ] Adapter failure fail closed。
- [ ] Adapter artifacts 足以 debug。
- [ ] Profile adapter resolution deterministic。

## Phase 6E: Stronger Apply Gate

### Objective

強化 apply gate，使 required review 的 missing / stale / failed / blocked / malformed 狀態都不能被誤放行，同時保留人工 override 作為一等公民。

### Files To Change

- `src/ait/landing.py`
- `src/ait/review_policy.py`
- `src/ait/review.py`
- `src/ait/cli/review.py`
- `tests/test_review_gate_hardening.py`
- `tests/test_landing.py`

### Files Not To Change

- 不改變 safe patch / dirty worktree / conflict handling 的原有優先語意。
- 不把 review gate 寫入 verifier。
- 不讓 override 改寫原始 finding。

### Acceptance

Auto apply 必須 hold，如果：

- Required review missing。
- Required review queued / running。
- Required review failed。
- Required review blocked。
- Required review stale。
- Required profile 缺失。
- Reviewer output malformed。
- Baseline policy violation。
- Memory policy violation。
- Sensitive path 變更缺少測試證據。
- Critical risk 缺少 required profile review。

Manual apply：

- 顯示 blocking reason。
- 若 policy 允許，可使用 explicit override。
- Override 後狀態是 `overridden`，不是 `passed`。
- Override 必須有 reason。
- Override 必須寫入 audit trail。

### Tests

```bash
python -m pytest tests/test_review_gate_hardening.py tests/test_landing.py
```

### Review Checklist

- [ ] Gate fail closed。
- [ ] Override 不偽裝成 passed。
- [ ] Blocking reason 足夠具體。
- [ ] 未啟用 review 的 apply 不受影響。
- [ ] Review gate 與 verifier 狀態分離。

## Phase 6F: Query DSL Integration

### Objective

讓 review、finding、override、freshness 可以透過 `ait query` 被查詢，支援 audit、debug 與長期分析。

### Files To Change

- `src/ait/query/*`
- `src/ait/report/*`
- `src/ait/run_report.py`
- `tests/test_review_query_dsl.py`
- `tests/test_report_review.py`

### Files Not To Change

- 不重新設計 query engine。
- 不新增全文搜尋引擎。
- 不讓 query 依賴 raw transcript parsing。

### Acceptance

支援查詢欄位：

- `review.status`
- `review.mode`
- `review.budget`
- `review.profile`
- `review.risk_level`
- `review.blocking`
- `review.override`
- `review.fresh`
- `review.baseline_ref`
- `finding.severity`
- `finding.blocking`
- `finding.lifecycle_status`
- `finding.path`

支援範例：

```bash
ait query 'review.status="overridden"'
ait query 'review.override=true'
ait query 'finding.severity in ["high", "critical"]'
ait query 'review.fresh=false'
ait query 'finding.lifecycle_status="open"'
```

無 review row 的既有 attempt 不應讓 query crash。

### Tests

```bash
python -m pytest tests/test_review_query_dsl.py tests/test_report_review.py
```

### Review Checklist

- [ ] Query field names 穩定。
- [ ] Empty review state 可處理。
- [ ] Query result 可追到 attempt / review / finding。
- [ ] Report 與 query 顯示一致。

## Phase 6G: Evaluation Benchmark

### Objective

建立本地 adversarial review benchmark，量測 reviewer quality、baseline usefulness、latency、review fatigue 與 memory contamination。

### Files To Change

- `src/ait/review_benchmark.py`
- `src/ait/cli/review.py`
- `tests/fixtures/review_benchmark/*`
- `tests/test_review_benchmark.py`
- `docs/adversarial-code-review-phase6-spec.md`

### Files Not To Change

- 不新增雲端 benchmark service。
- 不要求真實 LLM 才能跑測試。
- 不把 benchmark 結果當成 production gate。

### Acceptance

Benchmark case schema 至少包含：

- case id
- vulnerable diff
- malicious prompt/comment
- misleading memory
- expected findings
- expected blocked memory sources
- expected trusted baseline facts
- expected risk level

Benchmark metrics 至少包含：

- finding recall
- false positive count
- evidence completeness
- blocked memory source recall count
- trusted baseline contamination rate
- summary fidelity
- latency
- non-actionable warning count
- risk scoring calibration
- baseline usefulness marker

測試必須能用 fake reviewer 跑完，不依賴真實 LLM。

### Tests

```bash
python -m pytest tests/test_review_benchmark.py
```

### Review Checklist

- [ ] Benchmark 不依賴 network。
- [ ] Memory contamination 理想值可被測量為 0。
- [ ] Non-actionable warning 可被統計。
- [ ] Metrics JSON shape 穩定。
- [ ] Benchmark failure 不影響 production review gate。

## Phase 6 Exit Criteria

Phase 6 完成時，AIT review orchestration 應達到：

- Review disabled path 對既有使用者無行為改變。
- Queue worker 可處理 queued review。
- Required review gate 對 missing / stale / malformed / failed 狀態 fail closed。
- Adapter config 受 repo policy 控制，且 AIT core 不直接新增 network access。
- Review freshness 可被 report / status / query。
- Review、finding、override 可被 query。
- Human override 有完整 audit trail。
- Benchmark 可在本地用 fake reviewer 驗證。
- Regression tests 通過，尤其是 `run` / `apply` / `recover` 預設行為。
