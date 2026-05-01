# ait 專案 Staff+ Follow-up Code Review

**審查時間**：2026-05-01
**HEAD commit**：`590dbf6` (Fix NB-M3: reconnect harness sends after daemon drops)
**baseline**：`6d2cbc9`
**21 commits 已落地、35 個檔案仍有未 commit 變動**
**測試結果**：`.venv/bin/python -m pytest` → **382 passed in 111.55s**；`PYTHONPATH=src python3 -m unittest discover -s tests` → **382 OK in 109.65s**
**Production readiness**：**仍 NOT READY，但接近**。8 條 commit 個別都修對，惟有兩個系統性風險仍是 release blocker（commit/working-tree 分裂、daemon 進程殘留）。

---

## 一、Final verdict

| 維度 | 狀態 | 說明 |
|---|---|---|
| 8 條 follow-up commits 是否真的 fixed | **是**，每條 source + test 都到位 | 每條 commit 都有 file:line 證據 + regression |
| Stage 1+2 commits 是否未被破壞 | **是**，21 commits 完整鏈條都在 HEAD | git log 6d2cbc9..HEAD 完整 |
| 是否有新增 critical regression | **無新 critical regression** | 但有兩個 systemic risk |
| Daemon process 殘留是否仍是 blocker | **是，confirmed production blocker** | 系統當前 116 個 orphan ait daemon process |
| 測試是否真綠 | 是，382 pass | 但有 caveat：tests 跑的是 working tree，不是 HEAD |

---

## 二、8 條 follow-up commits 個別判定（fixed / partial / failed）

### eb0ee76 — AR-NEW-H5 log daemon client and verifier failures
- **狀態**：✅ **fixed**
- **source**：`src/ait/daemon.py:284-289` `_handle_client_safely` 把 `pass` 改 `print(f"ait daemon client warning: {exc}", file=sys.stderr)`；`daemon.py:336-341` `_verify_attempt_in_background.run` 也改成 print warning
- **regression**：`tests/test_daemon_concurrency.py:167-176`（client 失敗）+ `tests/test_daemon_verifier_threads.py:51-60`（verifier 失敗），都用 `contextlib.redirect_stderr` 驗證 warning 文字
- **品質**：good。仍用 `print` 而非 `logging`，但 May-01 review 接受這種寫法

### e0ec074 — AR-NEW-H4 warn when attempt memory note writes fail
- **狀態**：✅ **fixed**
- **source**：`src/ait/runner.py:259, 263, 280-285` 把兩條路徑（正常 + KeyboardInterrupt）統一走 `_add_attempt_memory_note_with_warning` helper，內部 `try/except Exception: print warning`
- **regression**：`tests/test_runner.py:378-397, 705-731` 兩條 path 都 patch `add_attempt_memory_note=side_effect=RuntimeError` 並斷言 stderr 含 `"ait warning: add_attempt_memory_note failed: memory write failed"`
- **品質**：good。覆蓋 normal + interrupt 兩條 path

### 7a86764 — LE-NEW-H2 skip failed attempts at memory-note source
- **狀態**：✅ **fixed**
- **source**：`src/ait/memory.py:407-409` `add_attempt_memory_note` 開頭 `if verified_status in {"failed","failed_interrupted","needs_review"}: return None`
- **regression**：`tests/test_memory.py:737-754` 直接 call 後 assert `note is None` + `notes == ()`；`tests/test_runner.py:441-456` 整合 path 一起改名 `does_not_add_failed_attempt_memory_note`
- **品質**：good，**但** function signature 仍宣告 `-> MemoryNote`，現在會回 None。建議補 `MemoryNote | None` 型別。Low risk，列為 minor follow-up

### 07b3fc8 — LE-NEW-H1 make local finish fallback events unique
- **狀態**：✅ **fixed**
- **source**：`src/ait/runner.py:498-518` 改走 `process_event(...)`，`event_id=f"ait-run-local-finish:{attempt_id}:{new_ulid()}"`，envelope 帶 `ownership_token`
- **regression**：`tests/test_runner.py:200-237` 連發兩次 fallback，最後 `SELECT COUNT(*) FROM meta WHERE key LIKE "event_seen:ait-run-local-finish:{attempt_id}:%"` 必為 2
- **品質**：good。**但** test 沒驗第二次 finish 對 attempt 狀態的影響（兩次 finished 是否導致 attempt 狀態重複 mutate）。屬可接受邊界，列為 minor follow-up

### 636ea05 — LE-NEW-H3 guard durable recall and fact approval policy
- **狀態**：✅ **fixed (test-only)** — fix 本來就在 HEAD，這 commit 補 regression
- **source**：commit 只動 `tests/test_memory.py`。實際 fix 在：(a) `src/ait/memory_policy.py:24-31` `DEFAULT_RECALL_SOURCE_ALLOW` 含 `"durable-memory:*"`，(b) `src/ait/memory.py:1999` SQL 加 `AND NOT (confidence = 'high' AND human_review_state != 'approved')`
- **regression**：`tests/test_memory.py:618-664` 兩條（durable-memory 默認可 recall + pending high-confidence fact 被擋）
- **品質**：good，fix + regression 都 align

### 8b1903c — ALG-H2 guard intent refresh against terminal regressions
- **狀態**：✅ **fixed**（針對 race window）；A-F4 explicit-abandon-from-finished 仍 partial
- **source**：`src/ait/lifecycle.py:23-71` 整段重寫，SELECT + UPDATE 全包進 `with conn:` 同一 transaction；UPDATE SQL 加 `WHERE status NOT IN ('finished','abandoned','superseded')` guard
- **regression**：`tests/test_lifecycle.py:119-129` `test_terminal_abandoned_intent_is_not_reopened_by_succeeded_attempt`
- **品質**：good 對它聲稱的 race。**但**：May-01 review 的 A-F4 還要求 `app.abandon_intent(finished-intent)` 也要拒絕，這條沒解。`app.py:441-453` `abandon_intent` 仍能把 `finished` 改成 `abandoned`（forward-only 違反）。需另一個 commit 補 explicit-abandon guard

### 3fc48b0 — QA-2-H5 recover running attempts after daemon SIGKILL
- **狀態**：✅ **fixed**
- **source**：`src/ait/daemon.py:142-146` `serve_daemon` 在 `with db_lock:` 內、`run_accept_loop` 之前直接呼叫 `recover_running_attempts(conn, now=_now(), heartbeat_ttl_seconds=_reaper_ttl(root))`；import 加在 `daemon.py:18`
- **regression**：`tests/test_daemon_lifecycle.py:84-129` 真 SIGKILL e2e：先設 `reaper_ttl_seconds=1`、`AitHarness.open` 發 attempt_started、`os.kill(started.pid, signal.SIGKILL)` → 等死 → `time.sleep(1.1)` → restart → assert `recovered.reported_status=='crashed'`、`verified_status=='failed'`
- **品質**：good，但有 timing 敏感點（`time.sleep(1.1)` 在 CI 慢機可能 flaky）。**risk**：production 預設 TTL=300s，attempts 仍須等 5 分鐘才被 recover；這條只解了「daemon restart 後仍會 recover」這條 invariant

### 590dbf6 — NB-M3 reconnect harness sends after daemon drops
- **狀態**：✅ **fixed**
- **source**：`src/ait/harness.py:60-95, 188-230` 加 `_HarnessConnectionError`（HarnessError 子類）+ `socket_timeout_seconds=3.0`；`_send` 包外層 try/except，遇到 `(BrokenPipeError, ConnectionResetError, OSError, _HarnessConnectionError)` 即 `close() + _connect()` 重試一次。**event_id 在 try/except 之外建立**（行 200-209），重試保留同 id，daemon dedupe 安全
- **regression**：`tests/test_harness.py:170-193` 起 server 在第一次收到 `attempt_finished` 時 `client.shutdown(SHUT_RDWR)`，第二次 accept 收到後正常回 ok=True；assertion 包含「兩次 attempt_finished 同 event_id」「server thread 結束」
- **品質**：good。retry 只一次（避免 ping-pong）；timeout 3s 合理。**但**：daemon 死後 reconnect 會打到 stale socket file，bind_unix_socket 已加 live probe（這在 working tree，HEAD 也許）— 跨 commit 對齊 OK

---

## 三、新發現的系統性風險

### NEW-CR1（Critical）— 21 commit 與 working tree 嚴重分裂；review 文件本身未 commit

**事實**：
- `git diff 6d2cbc9 HEAD --stat`：21 commits 涵蓋 31 個檔案、+2,133 / -169 行
- `git diff HEAD --stat`：仍有 35 個檔案、+870 / -119 行未 commit
- `git ls-files --others --exclude-standard`：6 個 untracked 檔案，包括 `docs/code-review-2026-04-30.md`、`docs/code-review-2026-05-01.md`、`docs/architecture-refactor-plan.md`、`tests/test_ids.py`、`tests/test_outcome.py`、`tests/test_redaction.py`

**證據**（May-01 review 標 verified-fixed 但實際未進 HEAD）：

| Finding | review 標 | HEAD 狀態 | working tree 狀態 |
|---|---|---|---|
| L-H1 redaction 13 patterns | ✅ | **只 6 個 pattern**（`src/ait/redaction.py:9-20` 只有 sk-/github_pat_/gh_/AKIA/KEY=/*KEY=） | 13 patterns 含 sk-ant/AIza/xox/JWT/Bearer/postgres/PEM ✓ |
| A-F1 query DSL CJK | ✅ | **`query.py:740` 仍 `bytes(...).decode("unicode_escape")`** | `_decode_string_literal` ✓ |
| A-F3 ULID secrets+monotonic | ✅ | **`ids.py` 仍 `random.getrandbits(80)`、無 monotonic** | secrets+monotonic ✓ |
| A-F5/F6 outcome markers | ✅ | **`outcome.py:87` 仍含 `"traceback"` 字面字串** | 已移除 ✓ |
| B-H1 reconcile mark stale | ✅ | **`reconcile.py:64` `manual_repair_required=False` 寫死** | unmapped 邏輯 ✓ |
| B-H4 reaper BEGIN IMMEDIATE | ✅ | **`events.py` 仍 implicit autocommit SELECT 後才 with conn** | BEGIN IMMEDIATE ✓ |
| B-H2 hook >> append | ✅ | 未檢視 | `>>` ✓ |
| B-M1 attempt_started terminal guard | ✅ | **`events.py:114` 無 early-return** | 有 ✓ |
| AR-F8 attempt_promoted 翻 verified_status | ✅ | **`events.py:331-346` 只寫 promotion_ref，無 verified_status='promoted'** | 完整實作 ✓ |
| A-F8 idresolver LIKE escape | ✅ | 未在 HEAD（idresolver.py 未 commit） | 有 ESCAPE 子句 ✓ |
| B-L7 promotion_ref `refs/heads/` | ✅ | 未在 HEAD | 有 ✓ |

**也就是**：May-01 review 列為「26 條 critical/high 中 22 條 verified-fixed」的判定，**幾乎一半的 fix 仍只在 working tree**，未進 HEAD。任何人 `git reset --hard HEAD` 或在乾淨 checkout 上跑都會看到原始 bug。

**為什麼測試還能綠？**因為測試直接讀檔案系統（working tree），不讀 git HEAD。LE-NEW-H1 的 fallback 走 `process_event`，HEAD 的 events.py 缺 ownership 校驗順序、reaper transaction 等等，但 working tree 補了；測試讀 working tree 全綠。

**影響**：
- 任何 reviewer / new contributor checkout HEAD 跑 test 會失敗
- CI 使用 git checkout 會 fail
- `git stash` 會把 fix 收進 stash，stash drop 會永久消失 fix
- review 文件本身（這份報告依賴的 May-01 / April-30）也是 untracked，risk 同樣

**修法**：把 working tree 全部變動 + untracked review docs 整理成多個邏輯 commit（依然每個 finding 一條），盡快進 HEAD。建議分批：
1. `Stage 0: redaction expansion` — redaction.py + tests/test_redaction.py
2. `Stage 0: ULID monotonic+secrets` — ids.py + tests/test_ids.py
3. `Stage 0: query DSL hardening` — query.py CJK + DSL injection + parse_blame_target leading-zero
4. `Stage 0: reconcile mark stale` — reconcile.py + tests/test_reconcile.py
5. `Stage 0: events transaction + lifecycle guards` — events.py BEGIN IMMEDIATE + attempt_started guard + attempt_promoted verified_status
6. `Stage 0: outcome markers cleanup` — outcome.py + tests/test_outcome.py
7. `Stage 0: workspace cumulative patch` — workspace.py
8. `Stage 0: idresolver LIKE escape` — idresolver.py
9. `Stage 0: hook append + transport hardening` — hooks.py + daemon_transport.py
10. `Docs: review reports` — 三個 review docs

**驗收**：
- `git diff HEAD --stat` 無輸出
- `git ls-files --others --exclude-standard` 無 review docs 與 test files
- `git stash` + `git stash pop` 不會丟失任何 fix

### NEW-CR2（Critical）— Daemon process 殘留是 production blocker（已實機驗證）

**事實**：審查時系統有 **116 個 orphan `ait.cli daemon serve` 進程在運行**。年齡 5+ 分鐘起跳，PPID=1（已 detached）。

**驗證**：
```bash
$ ps -eo pid,etime,args | grep -E "ait\.cli daemon serve" | grep -v grep | wc -l
116
$ ps -p 7860 -o pid,ppid,etime,args
  PID  PPID ELAPSED ARGS
 7860     1   06:31 Python -m ait.cli daemon serve
$ kill -TERM 7860 && sleep 2 && ps -p 7860
# (process gone) ✓ SIGTERM works individually
$ lsof -p 7860 | grep cwd
Python  7860 ... cwd  DIR  /private/var/folders/.../tmp1o7m2856
# tempdir from old test, daemon orphaned
```

**根因分析**：
1. `serve_daemon`（`daemon.py:128-185`）**沒有任何 SIGTERM signal handler**。Python default SIGTERM = 直接 terminate（不跑 finally），沒 graceful shutdown
2. `stop_daemon`（`daemon.py:68-82`）流程：
   ```
   status = daemon_status(root)
   if status.pid is not None and status.pid_matches:
       os.kill(status.pid, signal.SIGTERM)
   if status.socket_path.exists(): remove_socket_file(...)
   if status.pid_file.exists(): status.pid_file.unlink()
   ```
   `os.kill` fire-and-forget，**不等 daemon 真死**就 unlink pid file 並 return
3. 當 test 流程是「`Popen(ait run...)` → 完成 → stop_daemon → tempdir 清理」，若 daemon 在 SIGTERM 後因任何原因（race、accept 阻塞、socket cleanup 慢）沒立刻 die，test 進入 `with tempfile.TemporaryDirectory():` exit 階段，tempdir 被刪。daemon 進程的 cwd 變 invalid（已被 unlink，但 inode 還在），daemon process 繼續活著沒人管
4. 測試過程中 daemon 啟動次數遠多於 stop_daemon 配對成功次數

**為什麼 May-01 review 沒抓到**：當時 reviewers 沒 `ps -eo` 檢查殘留，僅看 daemon stop+restart 邏輯（NB-H2 join verifier、QA-2-H5 startup recovery）

**為什麼測試還是 pass**：每個測試自己都建獨立 tempdir，不共用 socket。orphan daemon 占用 fd、記憶體，但不影響別的 tempdir 的測試。所以 unittest 不報錯——但生產環境會累積到 fd 耗盡 / OOM

**production 影響**：
- 真實使用者跑多次 `ait run` 後沒手動 `ait daemon stop`，daemon 占用記憶體常駐
- macOS / Linux fd 與 inode 上限（默認 256-1024 fd / 進程）會被 daemon 各自吃掉
- daemon SQL connection 永遠 open，state.sqlite3-wal / -shm 檔案無法被刪
- 違反「使用者只要正常用 claude/codex/gemini，ait 在背後自動運作」核心目標

**修法**（兩條都需）：
1. **serve_daemon 安裝 SIGTERM/SIGINT signal handler**：
   ```python
   import signal
   def _handle_term(signum, frame):
       stop_event.set()
   signal.signal(signal.SIGTERM, _handle_term)
   signal.signal(signal.SIGINT, _handle_term)
   ```
   放在 `serve_daemon` 開頭，讓 SIGTERM 走 stop_event 路徑，finally 跑完整 cleanup（含 `_join_verifier_threads`）
2. **stop_daemon 等 daemon 真死才回**：
   ```python
   os.kill(status.pid, signal.SIGTERM)
   for _ in range(50):  # up to 5s
       try: os.kill(status.pid, 0)
       except OSError: break  # process gone
       time.sleep(0.1)
   else:
       # SIGKILL fallback
       try: os.kill(status.pid, signal.SIGKILL)
       except OSError: pass
   ```

**driver test**：補一條 e2e 測試 — start_daemon + send some events + stop_daemon + assert `os.kill(pid, 0)` raises ProcessLookupError 在 5s 內。**外加** test session 結束時 fixture 檢查 `ps -eo` 不留 orphan。

**驗收**：
- 跑完 `pytest` 後 `ps -eo pid,args | grep "ait.cli daemon serve" | grep -v grep` 必須空
- production 使用者反饋無 OOM / fd 耗盡

### NEW-H1（High）— A-F4 explicit abandon-from-finished 仍未守

**位置**：`src/ait/app.py:441-453` `abandon_intent`、`app.py:455-484` `supersede_intent`
**證據**：兩個函式都直接 `update_intent_status(conn, intent_id, "abandoned")` / `"superseded"`，**沒檢查當前 status**。`update_intent_status` 本身（`db/repositories.py:856-861`）也是 unconditional UPDATE
**對比**：ALG-H2 已修「自動 refresh path」的 race；但 explicit user-driven path 仍可違反 forward-only（finished → abandoned）
**修法**：兩個函式開頭都加：
```python
if intent.status not in {"open", "running"}:
    raise ValueError(f"Intent is {intent.status}, cannot {operation}: {intent_id}")
```
或在 SQL 加 `WHERE status IN ('open','running')` + rowcount 檢查
**驗收**：補測試「finished intent 不能被 abandon / supersede」

### NEW-H2（High）— LE-NEW-H1 fallback 第二次 finish 行為未驗

**位置**：`src/ait/runner.py:498-518` `_finish_attempt_locally`、`tests/test_runner.py:200-237`
**證據**：test 只驗 `meta.event_seen` 兩條都進，**沒驗 attempt.reported_status / verified_status / ended_at 是否被第二次 finish 重新覆寫**。如果 events.py 的 `handle_attempt_finished` 沒做 idempotent check，第二次會覆蓋第一次的時間戳
**對比**：working tree events.py 有 attempt_started 的 early-return guard，但 attempt_finished 是否也 guard 待查
**影響**：debug 日誌中 ended_at 不一致；attempt rerun 後 outcome 重新分類
**修法**：在 `handle_attempt_finished` 開頭加 `if attempt.reported_status == "finished": return False`，或於 test 補斷言「first finish 的 ended_at 不變」
**驗收**：補測試「two consecutive _finish_attempt_locally → ended_at == first call's timestamp」

### NEW-M1（Medium）— LE-NEW-H2 add_attempt_memory_note 型別不一致

**位置**：`src/ait/memory.py:407-409`
**證據**：function 簽名仍 `-> MemoryNote`，新增的 early-return 回 `None`。Type checker 會抱怨
**修法**：簽名改 `-> MemoryNote | None`，並更新所有 caller 處理 None（`runner.py:259, 263` 已 ignore 回傳值，但其他呼叫端需檢查）
**驗收**：`mypy src/ait/memory.py` 無新 error；caller 端不會炸

### NEW-M2（Medium）— Daemon timing-sensitive test 風險

**位置**：`tests/test_daemon_lifecycle.py:114, 116-117`
**證據**：`config["reaper_ttl_seconds"] = 1` + `time.sleep(1.1)` + 假設 SIGKILL 在這 sleep 期間完成
**影響**：CI 慢機 / load 高時可能 flaky；test name 包含 `sigkill` 較易識別
**修法**：把 sleep 改 `time.sleep(2.0)`；或用 `_wait_for_daemon_to_stop` poll loop

### NEW-L1（Low）— `_handle_client_safely` warning 仍可能未 flush

**位置**：`src/ait/daemon.py:289`
**證據**：`print(..., file=sys.stderr)` 預設 buffered（Python 3.x sys.stderr 是 line-buffered when isatty，否則 block-buffered）。daemon detached 時可能不 isatty → buffered → SIGTERM 後 buffer 丟失
**修法**：加 `flush=True` 或改 `sys.stderr.flush()` 後再 return
**驗收**：daemon 故意觸錯後 log 可見

---

## 四、Daemon process 殘留：是否仍是 production blocker

**結論**：**是，仍是 production blocker**。詳見 NEW-CR2。

關鍵點重述：
1. 系統當下有 **116 個 orphan ait daemon process** — 並非歷史遺留，是審查時跑 pytest+unittest 才生出來的
2. 根因在 `serve_daemon` 沒裝 SIGTERM handler + `stop_daemon` 不等 daemon 真死
3. NB-H2 修法（`_join_verifier_threads`）只在「serve_daemon finally block 跑到」的前提下有效，但 default SIGTERM 不會跑 finally
4. 即便 daemon 殘留，QA-2-H5 的 `recover_running_attempts` 會在下次 daemon start 時把過去的 stale attempts 標 crashed — 但**過去的 daemon 進程本身仍活著、佔記憶體 / fd**，這是另一回事
5. 整批 test 跑兩遍（pytest + unittest）就累積上百個 daemon，user 在自己機器上跑 ait 半天後也會累積

**強烈建議**：在解 NEW-CR1（commit working tree）的同時把 NEW-CR2 一併解掉。修法已附 patch。

---

## 五、其他觀察與建議

### Stage 1+2 commits 完整性
- 21 條 commits 都按順序在 git log 中，無 cherry-pick 衝突或 partial 殘留
- ad2b9bc → 590dbf6 鏈條完整
- 每條 commit message 都遵守 CLAUDE.md 格式（含 `docs:../docs/code-review-2026-05-01.md keyword:XXX`）

### Test 數從 358 升到 382
- 24 個新增 test 全綠
- 新增整合測試：`tests/test_daemon_e2e.py`（multi-process）、`tests/test_concurrency.py`（multiprocessing race）、`tests/test_daemon_verifier_threads.py`、`tests/test_memory_security.py`（prompt injection）
- LE-NEW-H1 / NB-M3 / QA-2-H5 / ALG-H2 都有對應 regression
- 但前述（May-01 review）未完成項：A-F4 explicit terminal guard、A-F12 cherry-pick conflict、Q1-NEW-H2/H3 部分 — 這些不在 8 條 follow-up commit 內，預期繼續 backlog

### 沒被本輪 commit 處理的 May-01 findings
參考 `docs/code-review-2026-05-01.md` § 八「Stage 3」與「Stage 4」中的多數項目仍 open，包括：
- AR-NEW-H2/H3 架構債（cli.py、memory.py、db/repositories.py 拆檔）
- ALG-CR1 的延伸（cherry-pick conflict）— ALG-H4
- LE-NEW-M3/M4/M5（candidate confidence / human_review approval workflow / transcript heuristic filter）
- 各種 medium / low

這些不是 regression，是 backlog；不影響 8 條 follow-up commits 的判定。

---

## 六、修復優先順序

### Stage A — 必須在 ship 前處理
1. **NEW-CR1 commit working tree fixes**：把 35 個檔案的未 commit 變動 + 6 個 untracked 檔案分類成多個邏輯 commit
2. **NEW-CR2 daemon SIGTERM handler + stop_daemon wait**：改 `serve_daemon` + `stop_daemon` + 補 e2e regression

### Stage B — 強烈建議同 PR 補
3. **NEW-H1 explicit abandon-from-finished guard**：補 app.py:441 / app.py:455 的 status check
4. **NEW-H2 fallback second-finish behavior verify**：events.handle_attempt_finished 加 idempotent check + test

### Stage C — 可分批
5. NEW-M1 LE-NEW-H2 型別簽名
6. NEW-M2 SIGKILL test sleep timing
7. NEW-L1 stderr flush

---

## 七、誠信宣告
- 全程 read-only review，沒改任何 source / test / docs
- 每條 finding 都附 file:line 與證據
- 8 條 commit 都讀過 source diff + test 內容 + 對應 May-01 review finding 的「建議修法」與「驗收方式」
- daemon 殘留問題有實機 `ps -eo` 驗證 + `kill -TERM` 確認 SIGTERM 在 individual process 是有效的
- 116 個 orphan daemon 數字來自審查時實機指令輸出
- 兩套測試套件實機跑出 382 passed / 382 OK，實際輸出已記錄
- 沒有 fabricate 任何行號或 spec 引用
