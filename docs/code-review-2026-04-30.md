# ait 專案 Staff 等級 Code Review 報告

**審查 commit**：`6d2cbc9` (Release ait-vcs 0.55.26)
**審查日期**：2026-04-30
**審查方式**：6 位 Staff 等級 reviewer 平行 read-only 審查（architect / llm-engineer / algorithm-engineer / backend-engineer / qa-engineer-1 / qa-engineer-2）
**測試套件實跑**：`PYTHONPATH=src python3 -m unittest discover -s tests` → 318 tests / 124.5s / **1 failure** / 11 ResourceWarning
**抽樣親驗**：5 條高衝擊度 finding 已實機重現

合計回報 **89 條 findings**，去重後 ~75 條：1 critical 測試失敗 + 4 critical 設計級 + 21 high + 30 medium + 23 low。

---

## 使用說明（給 Codex）

- 每條 finding 都有 `file:line` 與最小證據；可逐條依序修
- **必須先修 Critical 與 High**；Medium / Low 可後續批次處理
- 「待用戶決策」一節列出 13 項需先得到 PM/spec owner 裁示，**未經裁示前不要修**
- 修改前請先讀 `docs/ai-vcs-mvp-spec.md`、`docs/protocol-appendix.md`、`docs/implementation-notes.md` 對應段落
- 每個獨立 finding 應為一個 small commit；commit message 須含 `docs:../docs/code-review-2026-04-30.md keyword:CR1`（替換對應 ID）
- 修完後跑 `PYTHONPATH=src python3 -m unittest discover -s tests` 確認綠

---

## Critical（5 條，立即處理）

### CR1 — `test_cli_promote_dirty_head_branch_reports_clean_error` 已實機 fail
- **狀態**：實機 reproduce 過，returncode=1（expected 2）
- **位置**：`tests/test_app_flow.py:352`、`src/ait/cli.py:486`、`src/ait/workspace.py:215-220`
- **證據**：`WorkspaceError(RuntimeError)` 確認，CLI 有 catch `WorkspaceError` 但 promote dirty head branch 路徑仍 returncode=1，表示有非 `WorkspaceError` 例外在 try/except 外被 raise
- **修法**：debug 並讓 dirty head branch 檢查確實 raise `WorkspaceError`，或調整 cli.py:486 catch 範圍至 `(WorkspaceError, OSError, ...)` 以涵蓋實際 raise 的型別。同檔 line 305 與 line 352 對同一條 code path 期待要一致
- **驗收**：`PYTHONPATH=src python3 -m unittest tests.test_app_flow.AppFlowTests.test_cli_promote_dirty_head_branch_reports_clean_error` 通過

### CR2 — Memory recall 不過濾 superseded / valid_to expired 的 fact
- **位置**：`src/ait/memory.py:1396-1442`、`src/ait/memory.py:1826-1834`
- **證據**：`build_relevant_memory_recall` 中 fact 只檢查 `status == 'accepted'`；`_search_documents` 的 fact SQL 僅 `WHERE status = 'accepted'`，未過濾 `superseded_by IS NULL` 與 `valid_to > now`
- **違背 spec**：`docs/memory-temporal-ranking-design-zh.md:56-63`、`docs/long-term-memory-design.md`、`docs/ait-memory-architecture-design.md:250-258`
- **修法**：`_search_documents` SQL 加 `AND superseded_by IS NULL AND (valid_to IS NULL OR valid_to > ?)`（傳 `utc_now()`）；或在 `build_relevant_memory_recall` 對 fact 結果再 filter 一次
- **驗收**：補測試「superseded_by 非空的 accepted fact 不會被 recall」「valid_to 已過期的 accepted fact 不會被 recall」

### CR3 — Verifier / Outcome 反向耦合 spec 外的 memory 子系統
- **位置**：`src/ait/verifier.py:21,156-161`、`src/ait/outcome.py:25,30,52,71-72`
- **證據**：`verifier.py:21` `from ait.memory import extract_memory_candidates`；verifier 流程中讀 raw_trace 抽 memory candidates；`outcome.py:71-72` 把「無檔案改動但有 memory candidate」分類為 `succeeded`
- **違背 spec**：`docs/ai-vcs-mvp-spec.md` §Lifecycle、§Verification Rules 完全沒有「memory candidate」概念
- **修法**：把 memory candidate 抽取移出 verifier；verifier 只算 verified_status；outcome 移除 `has_memory_candidates` 參數；改由 memory 子系統在 verifier 完成後獨立 hook 進行（依賴方向 memory → core，不可反向）
- **依賴決策**：本修法等待「待用戶決策 #1」（memory 是否為 v1 一部分）

### CR4 — Runner 繞過 daemon 協議直接呼叫 events handler
- **位置**：`src/ait/runner.py:22`、`src/ait/runner.py:83-93`
- **證據**：`from ait.events import handle_attempt_finished`；同檔啟動 daemon 但實際路徑不走它，造成 `event_id` 去重對 runner 路徑失效、無 ownership 驗證
- **違背 spec**：`docs/ai-vcs-mvp-spec.md` §Harness Integration Protocol「lifecycle-mutating events 必須帶 ownership_token 經 socket」
- **修法**：runner 走 `AitHarness`（已 import 於 `runner.py:23`）的 socket client 一條路；或將 `handle_*` 函式集中為 internal、僅供 daemon 與測試使用，runner 不得 import

### CR5 — `.ait-context.md` 寫入完全無總體 budget，可達 ~21KB
- **位置**：`src/ait/runner.py:442-452`、`src/ait/context.py:82-136`
- **證據**：4 個 section `agent_context (no budget) + relevant_memory(4000) + repo_memory(12000) + brain_briefing(5000)`；`render_agent_context_text` 對所有 attempts 的 changed/touched/read files 完全無界
- **違背 spec**：`docs/ait-memory-implementation-details.md:478`、`docs/llm-long-term-memory-zh.md:333-349`
- **修法**：定義聚合 budget（建議 16KB），按 priority 分配到三個 section，並在最終寫入前統一截斷補警告 marker

---

## High（21 條）

### 後端基礎建設

#### B-H1 — reconcile 違反 spec：mapping 缺漏不會 mark stale
- **位置**：`src/ait/reconcile.py:60-65`、`src/ait/reconcile.py:84-122`
- **證據**：`manual_repair_required` 永遠常數 `False`；`_rewrite_commit_oid` 對 attempt_commits 找不到 row 的 mapping 直接 silent 回傳 0
- **違背**：`docs/ai-vcs-mvp-spec.md:439`「reconciliation cannot determine a new commit mapping must be marked stale and surfaced rather than failing silently」
- **修法**：分 hit / orphan-but-recoverable / unmapped 三類；unmapped 時保留 `.ait/manual-reconcile-required` marker，回傳 unmapped count 並讓 `manual_repair_required=True`

#### B-H2 — post-rewrite hook 用 `cat >` 覆寫，連續 rewrite 互吃 mapping
- **位置**：`src/ait/hooks.py:14`
- **證據**：`cat > "$REPO_ROOT/.ait/post-rewrite.last"` 是覆寫；git post-rewrite 每次 amend/rebase 呼叫一次，第二次覆蓋第一次未 reconcile 的 mapping
- **修法**：改 append `>>`，或寫到 `.ait/post-rewrite.<timestamp>.<pid>` 由 reconcile 批次處理

#### B-H3 — SQLite 沒啟用 WAL／busy_timeout
- **位置**：`src/ait/db/core.py:10-21`
- **證據**：`connect_db` 只下 `PRAGMA foreign_keys = ON`；至少 17 處各自開 connection（`memory.py:239,350,474,499,645,662,687,854,864,888,1261,1299,1592`、`brain.py:106,247`、`reconcile.py:38`、`runner.py:463`、`verifier.py:44`），daemon 另開一條 `check_same_thread=False`
- **修法**：在 `connect_db` 加 `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;`，但 :memory: db 不適用 WAL，需條件套用
- **依賴決策**：等待「待用戶決策 #8」（多 process write 是否支援）

#### B-H4 — reaper 讀寫不在同一 transaction，read-then-write race
- **位置**：`src/ait/events.py:394-426`、`src/ait/daemon.py:177-209`
- **證據**：L394 implicit autocommit `SELECT ... WHERE reported_status='running'`，L401 才 `with conn:` 開 BEGIN。SELECT 與 UPDATE 之間若有其他 process 寫入新 heartbeat，reaper 仍把 attempt 標 crashed
- **修法**：開頭 `BEGIN IMMEDIATE`，讀+寫包同一交易

#### B-H5 — daemon 沒 startup recovery
- **位置**：`src/ait/daemon.py:127-175`、`src/ait/events.py:375-378`
- **證據**：`recover_running_attempts` 已寫但 `serve_daemon` 從未呼叫；只有 reaper 在 `startup_grace_seconds=30s` 後才掃，`heartbeat_ttl_seconds=300s`，daemon crash 重啟期間 attempts 卡 running 一整個 TTL
- **修法**：daemon 啟動 migrations 後立即 `recover_running_attempts(...)`

#### B-H6 — verifier 包進 db_lock，git I/O 阻塞所有 client 數秒
- **位置**：`src/ait/daemon.py:309-321`、`src/ait/workspace.py:138-200`
- **證據**：對每筆 `attempt_finished/attempt_promoted` 在 `with db_lock:` 內呼 `verify_attempt_with_connection`；verifier 跑多次 `git rev-list/show --numstat/merge-base`，commit 多時可達數秒
- **修法**：拆出 db_lock 之外。先標 `pending_verify`，背景 thread 做 git I/O，最後再進 db_lock 寫回

### 演算法（5 條已 team-lead 親自重現）

#### A-F1 — Query DSL 字串字面值 CJK 完全壞掉
- **位置**：`src/ait/query.py:740`
- **證據（已重現）**：`bytes(token_value[1:-1], "utf-8").decode("unicode_escape")` 把 UTF-8 多位元組當 latin-1。`parse_query('kind="中文"')` → `value='ä¸\xadæ\x96\x87'`
- **修法**：手動處理常見 escape (`\\`, `\"`, `\n`, `\t`, `\xHH`)，保留原始 unicode；不要用 `bytes(...).decode('unicode_escape')`
- **驗收**：`parse_query('kind="中文"').value == "中文"`

#### A-F2 — Lifecycle 違反 spec：`succeeded` 也觸發 `finished`
- **位置**：`src/ait/lifecycle.py:51`
- **證據（已重現）**：`if any(str(item["verified_status"]) in {"succeeded", "promoted"} ...): update_intent_status(conn, intent_id, "finished")`
- **違背**：spec table `docs/ai-vcs-mvp-spec.md:339-344` 明示 `open|running -> finished` 的 trigger 是 `verified_status=promoted`，docstring 又寫「succeeded 或 promoted」
- **修法**：條件改為僅 `verified_status == "promoted"`，並同步修 lifecycle.py docstring
- **依賴決策**：等待「待用戶決策 #2」（spec 與實作哪個對）

#### A-F3 — ULID 同毫秒不單調 + 用 Mersenne Twister
- **位置**：`src/ait/ids.py:9-17`
- **證據（已重現）**：1000 個 ULID 中 988 個失序；`random.seed(0); new_ulid()` 連兩次相同
- **修法**：(a) 改 `secrets.randbits(80)`；(b) 對同毫秒做 monotonic counter（cache 上次 timestamp_ms 與 random_bits，timestamp 相同時 random+1，溢位則 timestamp+=1）
- **依賴決策**：等待「待用戶決策 #4」（是否需符合 Crockford ULID 3.4 節）

#### A-F4 — `abandon_intent` / `supersede_intent` 沒做 terminal-state guard
- **位置**：`src/ait/app.py:436`、`src/ait/app.py:468`、`src/ait/db/repositories.py:856-861`
- **證據**：`update_intent_status` unconditional UPDATE，無 status guard。`ait intent abandon <finished-intent>` 會從 finished 倒退到 abandoned
- **違背**：spec table 行 343-344「open or running -> abandoned/superseded」forward-only
- **修法**：在 SQL 加 `WHERE id = ? AND status IN ('open','running')` 並用 `rowcount` 檢查；或在 app 路徑加 `if intent.status not in {"open","running"}: raise ValueError(...)`

#### A-F5 — `_looks_like_infra_failure` 含 `"harness"` `"traceback"` 過於寬泛
- **位置**：`src/ait/outcome.py:76-89`
- **證據**：normal Python traceback 含 `"Traceback (most recent call last):"` 會被誤分類為 `failed_infra`；intent 名稱含 `harness` 也會中
- **修法**：移除 `"traceback"` marker；`"harness"` 改為 `"ait harness"` 或 `"harness binary"`
- **依賴決策**：等待「待用戶決策 #6」（marker 是否該 evidence-table-driven）

#### A-F6 — `outcome.classify` 用 `"^c"` 字面字串而非 SIGINT trace 標記
- **位置**：`src/ait/outcome.py:42`
- **證據**：`"^c"` 是字面 caret+c，任何 trace 含 `"^cdef"` `"^c is hard"` 都會誤判 interrupted
- **修法**：移除 `"^c"` marker（exit_code==130 已強訊號），或改比對 `"\x03"`、`"signal SIGINT"`、`"received SIGINT"`、`"Interrupted by signal"`

### LLM 整合

#### L-H1 — redaction pattern 覆蓋面狹窄
- **位置**：`src/ait/redaction.py:8-21`
- **證據**：缺 Anthropic key 完整格式、Google API Key (`AIza[0-9A-Za-z_-]{35}`)、Slack tokens (`xox[baprs]-…`)、JWT (`eyJ[A-Za-z0-9_-]+\.eyJ…`)、Bearer header、PostgreSQL/MySQL connection string、PEM body inline base64
- **修法**：擴充 SECRET_PATTERNS，與 `path_excluded` / `transcript_excluded` 並用

#### L-H2 — `intent_description` 在 agent context 注入端未 redact
- **位置**：`src/ait/context.py:91-92`、`src/ait/runner.py:444`
- **證據**：`render_agent_context_text` 直接印 `intent['description']`；`brain.py:564` 對 intent 走 redact，但 runner 寫 .ait-context.md 路徑沒走
- **修法**：`render_agent_context_text` 對 description / kind / title 統一過 `redact_text`，並用 `transcript_excluded` 對組合文字檢查

#### L-H3 — recall 中不同 ranker base score 尺度錯亂
- **位置**：`src/ait/memory.py:1338-1352`、`src/ait/memory.py:1490-1532`
- **證據**：vector ranker (cosine ~0~1) 與 literal ranker (10+len/8 ~10~15) merge 時，base_score 差 10x。`temporal_score = base_score * factors`（factors 0.3~1.5）讓 stale 高 literal 仍贏過 fresh 高 vector
- **修法**：merge 前對每個 ranker score 做 min-max 正規化（或 z-score）；或 multiplicative factor 改 additive bonus 並先正規化 base

#### L-H4 — failed/interrupted attempt 仍被預設 recall
- **位置**：`src/ait/memory.py:374-414`、`src/ait/runner.py:226-233`
- **證據**：`add_attempt_memory_note` 無視 `verified_status`，固定建立 `attempt-memory:*`；default `recall_source_allow` 含 `attempt-memory:*`
- **違背**：`docs/ait-memory-architecture-design.md:199-209,254-258`
- **修法**：對 `verified_status in {'failed','failed_interrupted','needs_review'}` 改 topic 為 `failure-lesson`，或寫入 `memory_facts kind='failure'`，或從 default `recall_source_allow` 移除非成功 attempt-memory

#### L-H5 — extract_memory_candidates 容易把 prompt-injection 升為 high-confidence durable fact
- **位置**：`src/ait/memory.py:510-547`、`src/ait/memory.py:804-817`
- **證據**：candidate detection 完全用 keyword（`以後/必須/不要/must/should/do not/decide`），attempt verified `succeeded` 後升為 `durable-memory:{attempt_id}` + `memory_facts.status='accepted', confidence='high'`
- **修法**：升級為 durable 應額外要求候選 line 在 changed_files 或 commit message 中有 corroboration；或 `confidence` 降為 `medium` 並要求人工確認；至少把 candidate 來源限制在 normalized transcript

#### L-H6 — fact recall 路徑缺 source / policy 檢查（與 note 不對稱）
- **位置**：`src/ait/memory.py:1396-1442` vs `src/ait/memory_eval.py:298-310`
- **證據**：note 走完整 `recall_source_blocked / recall_source_allowed / lint_blocked`；fact 只檢查 status。一個 fact 若 `source_file_path` 為 `secrets/api-keys.md` 仍會被 inject
- **修法**：把 `_fact_policy_blocked` 等價邏輯搬到 `build_relevant_memory_recall` 對 fact 也執行
- **依賴決策**：等待「待用戶決策 #13」（known gap 還是 bug）

### 架構

#### AR-F3 — `cli.py` 2,265 行、26 個頂層子命令家族
- **位置**：`src/ait/cli.py:116-382, 574-851`
- **證據**：spec §CLI Surface 只列 init/intent/attempt/query/blame/daemon；實作另增 `run/context/memory/bootstrap/doctor/status/upgrade/graph/repair/enable/shell/adapter/reconcile`，`memory` 子命令分支佔 277 行
- **修法**：(a) parser 與 dispatcher 切到 `cli/` 套件，每個子命令一個檔；(b) 超出 spec 的命令族抽到 `ait.contrib`
- **依賴決策**：等待「待用戶決策 #1」

#### AR-F4 — `memory.py` 2,187 行、`brain.py` 851 行職責失控
- **位置**：`src/ait/memory.py` 至少 8 處各自 `connect_db + run_migrations`（第 350,474,499,645,662,687 等）；`src/ait/brain.py:10` `from ait.app import init_repo`
- **證據**：memory.py 任何操作都隱式觸發 schema migration；不走 daemon 的 `db_lock`，會與 daemon 競爭。`brain.py` 反向 import `app.init_repo`
- **修法**：抽 `MemoryRepository` 物件由呼叫端注入 conn；memory.py 拆 `memory/notes.py`、`memory/import.py`、`memory/recall.py`、`memory/lint.py`、`memory/render.py`；brain 移除對 `app.init_repo` 的 import

#### AR-F5 — `db/repositories.py` 1,058 行混合 spec 內外表
- **位置**：`src/ait/db/repositories.py:1-1058`、`src/ait/db/schema.py:194-289`
- **證據**：spec §Storage Mapping 只列 7 表，migration v6 加了 4 張 memory graph 表（`memory_facts`/`memory_fact_entities`/`memory_fact_edges`/`memory_retrieval_events`）；`db/__init__.py` 把這些 record 重新匯出
- **修法**：把 memory 表的 schema/repositories 拆到 `db/memory_repositories.py`，`db/__init__.py` 不轉出；spec/notes 補一段「v1 持久化的官方表 vs 擴充表」

### 測試品質

#### Q1-H1 — daemon transport 缺 partial frame、多 envelope 交錯、abrupt close 測試
- **位置**：`tests/test_protocol_transport.py`
- **修法**：補 (a) partial bytes buffer + 等續傳；(b) 連續多 envelope 同 stream 交錯讀寫；(c) client 寫一半即斷線，server 應拋 transport error 不卡死

#### Q1-H2 — daemon 並發/reaper 測試規模太小、用 sleep-based race shaping
- **位置**：`tests/test_daemon_concurrency.py:73,100`、`tests/test_daemon_reaper.py`
- **修法**：擴展為 5 client × 50 event 並斷言事件總和；補 reaper 對 10 stale batch 行為驗證；改用 event/condition 取代 `time.sleep(0.01)`

#### Q1-H3 — migration 缺 forward-only 與 partial-apply 測試
- **位置**：`tests/test_db_migrations.py`
- **修法**：補 v1→v2→v3 中間不可跳號；migration 中途失敗回滾；手動把 schema_version 設 1 但 schema 已是 N，run_migrations 觸發補做（不可清空）

#### Q1-H4 — protocol envelope 邊界覆蓋不足
- **位置**：`tests/test_protocol.py`
- **修法**：補 schema_version != 1、attempt_id 含非法字元/超長、payload 非 dict、RFC3339 含 tz offset、tool_event `duration_ms` 為負、files entry 缺 path 等 6 條 case

#### Q2-F1 — temporal ranking 公式無數值驗證
- **位置**：`tests/test_memory.py:103-205`，源碼 `src/ait/memory.py:1490-1568`
- **證據**：5 個 temporal recall 測試只 `assertEqual` 第一名 id 或 `assertIn("temporal_score", ...)`；half-life 表（current_state=14d、rule=90d、decision=180d）、confidence 倍率（manual 1.08/high 1.05/low 0.78）、kind 倍率（decision 1.04/failure 0.88）三個常數表沒有任何測試 assert 具體乘積
- **修法**：新增 unit test 直接呼叫 `_temporal_ranked_result`，給 fixed `now` 與 anchor，`assertAlmostEqual(temporal_score, base_score * 預期乘積, places=4)`，至少對 (rule, decision, current_state, failure) × (high, low) 各取一格

#### Q2-F2 — query DSL 錯誤路徑與安全性測試極少
- **位置**：`tests/test_query.py`（235 行只 1 處 assertRaises at line 78）
- **修法**：補 (1) `parse_query("kind=")` → QueryError；(2) `parse_query("(kind=\"x\"")` → QueryError；(3) `compile_query(... limit=-1)` → QueryError；(4) `execute_query(..., 'observed.tool_calls > "abc"')` → QueryError；(5) `parse_query('kind="\\"; DROP TABLE intents; --"')` 應只回 string literal；(6) 驗證 placeholder 數 = params 數

#### Q2-F3 — `test_relevant_memory_recall_does_not_rank_failure_above_rule` 名實不符
- **位置**：`tests/test_memory.py:179-205`、源碼 `src/ait/memory.py:1559-1568`
- **修法**：改名為 `test_rule_kind_outranks_failure_when_temporal_ranking_applied`；另補一個「兩 fact 同 kind 同 confidence 同 updated_at 時 tie-breaker 為 id 字典序」的測試

---

## Medium（30 條）

### 後端

- **B-M1** `attempt_started` 即使 verified=`discarded` 仍會把 reported_status 改回 `running`：`events.py:111-143`
- **B-M2** `bind_unix_socket` 對既有 socket 直接 unlink 不檢查存活：`daemon_transport.py:50-55`
- **B-M3** `_write_response` 未捕 `BrokenPipeError`/`ConnectionResetError`/`OSError`：`daemon.py:324-325`
- **B-M4** daemon stop 不 join client thread，在飛事件可能消失：`daemon.py:240-273,165-174`
- **B-M5** `_pid_matches_ait_daemon` 子串比對寬鬆，可能誤殺他人程序：`daemon.py:394-406`
- **B-M6** `list_shortcut_expression` 用 f-string 把 user input 注入 DSL：`query.py:153-171`、`cli.py:443-447,511-516`
- **B-M7** unix socket 權限未收緊（umask 決定）：`daemon_transport.py:43-63`
- **B-M8** `process_event` 與 verifier 跨多 BEGIN，狀態可能不一致：`events.py:55-77`、`daemon.py:309-321`、`verifier.py:51-97`
- **B-M9** envelope timestamp 雙重驗證語法不一致（protocol 嚴格 vs events 用 fromisoformat）：`protocol.py:475-484`、`events.py:497-505`
- **B-M10** `replace_attempt_commits` DELETE+INSERT 空窗：`db/repositories.py:721-748`、`verifier.py:64-65`

### 演算法

- **A-F7** `blame_path` 解析 `:line` 但完全沒消費（silent no-op）：`query.py:174-234`。等待「待用戶決策 #3」
- **A-F8** `idresolver` `LIKE '%X%'` 對 `%`/`_` 通配符未轉義：`idresolver.py:56-67`。修法：escape 後加 `LIKE ? ESCAPE '\\'`
- **A-F9** temporal sort key 第二鍵重複 `temporal_score`、`age_days` 對未來時間 silent 截為 0：`memory.py:1493-1500,1508,1527`。修法：第二鍵改 `temporal_base_score`；未來 timestamp 不要截 0，視為未知 + 加 metadata flag
- **A-F10** `refresh_intent_status` SELECT/UPDATE 跨 transaction 與 abandon 競爭：`lifecycle.py:29-58`、`verifier.py:90`、`db/repositories.py:856-861`。修法：包 `BEGIN IMMEDIATE`；UPDATE 加 `WHERE status NOT IN (...)`
- **A-F11** `_terms` regex 完全剃除 CJK，中文搜尋僅靠 literal substring：`memory.py:2128-2129,2147-2149,1338-1352`。修法：regex 加 `|[㐀-鿿豈-﫿぀-ヿ가-힯]`，加 CJK bigram。等待「待用戶決策 #5」
- **A-F12** verifier 對 squash/cherry-pick promotion 與「無 commit 但 ref 動」誤判 failed：`verifier.py:135-142`、`workspace.py:191-200`。修法：消費 reconcile 結果取最新 oid 後再 `ref_contains_commits`

### LLM

- **L-M1** brain trace node 1400 chars 撐爆 briefing：`brain.py:633-650,372-426`。修法：trace node 限 400 chars 並 dedupe
- **L-M2** note 永遠 fallback 為 `note` half-life，manual note 拿不到 365 天 / 0.85：`memory.py:1505-1511,1880-1903`。修法：source=manual 的 note 在 metadata 標 `kind='manual'`
- **L-M3** source=`manual` 的 note 被 default policy block：`memory.py:347`、`memory_policy.py:25-28`。修法：default allow 加 `manual:*`；或 `add_memory_note(source='manual')` 自動寫成 `manual:user`
- **L-M4** redact lambda 多 group 未保護 KEY 名洩漏：`redaction.py:28-32`。修法：KEY 名 length>80 或含敏感 keyword 整體 redact
- **L-M5** confidence 沒對齊 outcome_class 階層：`memory.py:485-492`。修法：依 outcome_class 分階層（succeeded=high, succeeded_noop=medium, others=low）

### 架構

- **AR-F6** migration v3 是 no-op `SELECT 1;` 佔版本號：`db/schema.py:139-145`。修法：要嘛實際 `ALTER TABLE ... DROP COLUMN`，要嘛標 retired 並註解
- **AR-F7** `ait attempt commit` 在 spec 與 notes 都未記載：`app.py:390-425`、`cli.py:155-157,475-482`。修法：在 `docs/implementation-notes.md` 補一節說明
- **AR-F8** daemon `attempt_promoted` 不主動翻轉 `verified_status`，library 路徑會卡 pending：`events.py:331-346`、`daemon.py:312-316`、`protocol-appendix.md:177-192,220-226`。修法：把 verifier 觸發放回 `events.handle_attempt_*` 最後一段

### 測試（QA-1 + QA-2）

- **Q1-M1** `events.py:82` unsupported `schema_version` 沒測 → 補簡單 raise 測試
- **Q1-M2** `events.py:447` unsupported event_type 沒測 → 補簡單 raise 測試
- **Q1-M3** reaper crash 後 evidence_summary freeze 沒驗：`tests/test_daemon_reaper.py:75-78` → 補「crash 後再送 tool_event 應被拒/忽略」
- **Q1-M4** workspace remove 後 `git worktree list` 沒驗：`tests/test_workspace.py`、`tests/test_app_flow.py:107`
- **Q1-M5** hooks 對 pre-existing user post-rewrite hook merge 沒測：`tests/test_hooks.py:24-34` → 補一個有既存內容的 install 測試，斷言原內容仍在
- **Q1-M6** reconcile 只 1 個 happy path：補 (a) 畸形 line；(b) commit oid 不在 attempt_commits；(c) 多 attempt 同 commit 被 rewrite
- **Q1-M7** harness 缺 daemon 中途斷線 / connect 失敗測試：`tests/test_harness.py:108,150`
- **Q2-F4** temporal_score `age_days=None` 路徑（缺 updated_at）未覆蓋 → 補 unit test 直接構造 metadata 沒 updated_at
- **Q2-F5** `tests/test_cli_shell.py` 88 行只 3 case，缺：(1) 不支援 shell；(2) 損壞標記區塊；(3) `rc_path=None` 走 SHELL env；(4) 已存在 rc 但無 START 標記時 install append；(5) install 後 rc 不以 \n 結尾合併
- **Q2-F6** test_query.py 缺 SQL injection regression、precedence、NOT NOT 測試 → 補 placeholder 數 = params 數驗證、`A AND B OR C` precedence 等
- **Q2-F7** `test_memory_lint_fix_conservatively` 只驗 count 不驗 fix code：`tests/test_memory.py:292-315` → assert `{fix.code for fix in fixed.fixes} ⊇ {"duplicate","possible_secret","max_length"}`

---

## Low（23 條）

### 後端
- **B-L1** pid_file 寫檔不 atomic：`daemon.py:134`
- **B-L2** socket connectable timeout 0.2s 過嚴：`daemon.py:380-391`
- **B-L3** config write_text 非原子：`config.py:56-64`
- **B-L4** `_git_rev_parse` check=True 缺友善錯誤：`hooks.py:78-84`
- **B-L5** worktree add 失敗後未清空目錄：`workspace.py:82-119`
- **B-L6** reaper 例外 swallow 缺 log：`daemon.py:204-207`
- **B-L7** promote target_ref 未限 `refs/heads/...`：`workspace.py:203-240`、`app.py:327`。等待「待用戶決策 #9」
- **B-L8** `_iso_now` 與 `utc_now` 重複實作：`harness.py:219-220`、`db/core.py:24-25`
- **B-L9** `db_path != ":memory:"` 字串比對寫死：`db/core.py:15-18`
- **B-L10** dedupe 早於 ownership token 驗證可資訊洩漏：`events.py:55-63`

### 演算法
- **A-F13** `_candidate_line(line)[:600]` 截斷後 dedupe 可能誤合 → dedupe key 改用 hash of full
- **A-F14** `_score_document_lexical` prefix match 對極短 query term 大量假陽性：`memory.py:2024-2043` → 跳過 length<3 term
- **A-F15** Query DSL `id` 在 attempt subject 解析為 intent.id 易混淆：`query.py:498-504` → attempt subject 拒絕 `id`
- **A-F16** `parse_blame_target` 對 `:0` `:01` silent fall back：`query.py:177` → 明示 raise QueryError
- **A-F17** `_temporal_time_factor` 與 `_temporal_kind_factor` 對未知 kind fallback 不一致：`memory.py:1546,1568` → 集中 fallback + metadata flag

### LLM
- **L-L1** redact `\b` 邊界對 `_` 結尾 token 不完整：`redaction.py:9` → 改 lookarounds
- **L-L2** harness `_finish_attempted` 設在 send 前，daemon 拒絕後無法重試：`harness.py:170-172`
- **L-L3** `_find_real_binary` 用 Path.resolve() 對 wrapper symlink 規避脆弱：`adapters.py:543-556`
- **L-L4** `_dedupe_repeated_words` 只處理 Working/Starting，漏 Generating/Loading/Thinking：`transcript.py:102-105`
- **L-L5** `memory_eval._tokens` regex 跳過所有 CJK，中文 query 永遠拿不到 relevance hit：`memory_eval.py:286-287`
- **L-L6** `_temporal_time_factor` 未知 kind fallback 與 note 同表，metadata 不明確

### 架構/測試
- **AR-F9** `report.py` 1,247 行職責膨脹（4 種輸出 mux 在一檔）
- **AR-F10** CLI parser argparse 樣板碼 `--format/--limit/--offset` 重複 25 次
- **Q1-L1** 11 條 ResourceWarning（subprocess 殘留），多在 daemon-related test
- **Q1-L2** `time.sleep` race-shaping：`tests/test_daemon_concurrency.py:100`、`tests/test_daemon_reaper.py:99,123`
- **Q1-L3** `tests/` 缺 `__init__.py`，`python3 -m unittest tests.test_app_flow` 失敗
- **Q1-L4** `tests/test_protocol.py:254` 用 `envelope_to_dict(...)` 比較而非直接 ==
- **Q1-L5** `test_db_migrations.py:65-78` 只負面斷言 column NOT IN
- **Q1-L6** `test_lifecycle.py` 全部 in-memory db，無 transaction rollback 測試
- **Q2-F8** `test_path_claude_invocation_hits_wrapper` 等 5 個 adapter subprocess test 應加 `@unittest.skipUnless(shutil.which("ait"), ...)`：`tests/test_cli_adapters.py:388-451,453-523`
- **Q2-F9** `test_doctor_reports_daemon_stale_reason` 用 `os.getpid()` 寫 pid file：`tests/test_cli_adapters.py:687-724,1214-1243`
- **Q2-F10** `test_init_imports_detected_agent_memory_files` 沒檢查多源順序穩定性：`tests/test_cli_adapters.py:360-386`
- **Q2-F11** `tests/test_adapters.py` 11 處直接 mutate `os.environ["PATH"]`，建議改 `unittest.mock.patch.dict`
- **Q2-F12** `test_doctor_claude_code_passes_in_repo_checkout` 依賴跑測試的 repo 為 git repo：`tests/test_adapters.py:66-75`

---

## 待用戶決策（13 項，未經裁示前不要修）

1. **memory / brain 子系統屬不屬於 v1 spec 範圍？** 影響 CR3、CR4、AR-F3、AR-F4、AR-F5。
2. **Lifecycle `succeeded` vs `promoted` 觸發 finished**：spec table、spec 敘述、lifecycle.py docstring、實作 code 四處不一致。影響 A-F2。
3. **`ait blame foo:42` 行號 v1 是否規劃支援？** 不支援需 parser 拒絕含 line 的 target 並文件化。影響 A-F7、A-F16。
4. **ULID 是否需符合 Crockford 第 3.4 節 monotonic？** 不需也要在 implementation-notes 文件化。影響 A-F3。
5. **CJK 搜尋 v1 是否提供基礎支援？** 影響 A-F1（mojibake 必修）、A-F11、L-L5。
6. **outcome.failed_infra marker 是否該 evidence-table-driven？** 影響 A-F5、A-F6。
7. **runner 是否屬於 v1？** 影響 CR4 修法。
8. **WAL 啟用、:memory: 相容性、多 process write 是否屬支援情境？** 影響 B-H3。
9. **promote target_ref 是否強制 `refs/heads/...`？** 影響 B-L7。
10. **使用者命令路徑的狀態 guard 層級**：app vs db vs SQL WHERE。影響 A-F4、A-F10。
11. **discarded 後遲到 attempt_started 是否該 silent ignore？** 影響 B-M1。
12. **`add_attempt_memory_note` KeyboardInterrupt 用 `pass` 吞所有 Exception 是否 by-design？** 影響 L-H4 修法。
13. **fact recall 缺 source/policy 檢查（與 note 不對稱）是 known gap 還是 bug？** 影響 CR2 補強範圍與 L-H6。

---

## 抽樣親驗紀錄

team-lead 對以下 5 條 finding 親自跑指令重現：

1. ✅ `tests/test_app_flow.py:352` 實機 fail（rc=1, expected 2）
2. ✅ `lifecycle.py:51` 確實寫 `{"succeeded","promoted"}`
3. ✅ `ids.py` 1000 ULID 中 988 失序、`random.seed(0)` 兩次相同
4. ✅ `reconcile.py` `manual_repair_required` 永遠 `False`
5. ✅ `memory.py:1396-1442` fact 路徑只檢查 status，無 source / policy / superseded / valid_to 過濾
6. ✅ `query.py:740` `parse_query('kind="中文"')` → mojibake `'ä¸\xadæ\x96\x87'`
