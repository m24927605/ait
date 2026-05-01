# ait 專案 Staff+ Follow-up #2 Code Review

**審查時間**：2026-05-01（second follow-up）
**HEAD commit**：`35be919` (Add Staff review and refactor planning docs)
**前次 follow-up**：`docs/code-review-claude-followup-2026-05-01.md`
**待驗證範圍**：22 個新 commits（590dbf6..HEAD），其中包含 NEW-CR1、NEW-CR2、NEW-H1、NEW-H2 與多項 hardening
**測試結果**：`.venv/bin/python -m pytest` → **383 passed in 117.30s**；`PYTHONPATH=src python3 -m unittest discover -s tests` → **383 OK in 115.91s**
**Production readiness verdict**：**READY WITH CONDITIONS**（runtime fixes 全部到位；剩 1 條 test hygiene 風險與 1 條 minor 型別修正）

---

## 一、Final verdict matrix

| 上輪 finding | 修法狀態 | 證據 file:line |
|---|---|---|
| NEW-CR1 working tree / HEAD split | ✅ **完全修復** | `git status --short` 空、`git ls-files --others` 空、22 commits 把所有 Stage 0 fix 與 review docs 都進 HEAD |
| NEW-CR2 daemon SIGTERM graceful | ✅ **修復** | `daemon.py:156` `_install_stop_signal_handlers(stop_event)`；`daemon.py:428-441` 註冊 SIGTERM/SIGINT；`daemon.py:199` 在 finally 中 `_restore_signal_handlers` |
| NEW-CR2 stop_daemon wait + SIGKILL fallback | ✅ **修復** | `daemon.py:73-89` `os.kill(SIGTERM)` 後 `process.wait(timeout=5.0)` / `_wait_for_pid_exit(timeout=5.0)`，timeout 後 `process.kill()` 或 `os.kill(SIGKILL)` |
| NEW-CR2 verifier/client cleanup 真實執行 | ✅ **修復** | SIGTERM → handler 設 stop_event → accept loop 退出 → finally 跑 `_join_verifier_threads(timeout=5.0)` 等 |
| NEW-H1 finished/terminal intent 不能 abandon/supersede | ✅ **修復** | `app.py:460-461` `if intent.status not in {"open", "running"}: raise ValueError("Cannot abandon ...")`；`app.py:489-490` 同樣 guard for `supersede_intent` |
| NEW-H2 repeated local finish 不覆寫 first finish 的 ended_at/raw_trace_ref/exit_code | ✅ **修復** | `events.py:236` `if attempt.reported_status == "finished" and attempt.result_exit_code is not None: return False` 直接 short-circuit，UPDATE 不執行 |

---

## 二、22 個新 commits 個別檢視

### Critical / Stage 0 baseline 補位（先前未 commit 的修法）

| Commit | 修法 | HEAD 證據 | 狀態 |
|---|---|---|---|
| `61a6fb0` Fix L-H1 redaction expansion | redaction.py 從 6 patterns → 13 patterns（含 sk-ant、AIza、xox*、JWT、Bearer、postgres/mysql、PEM block） | `src/ait/redaction.py:8-31`，`grep -c re.compile = 13` | ✅ |
| `f3b2eb3` Fix A-F3 ULID secrets+monotonic | random.getrandbits → secrets.randbits + threading.Lock + 同毫秒 counter + 溢位 timestamp+=1 | `src/ait/ids.py:1-37` | ✅ |
| `6783058` Fix A-F1 query DSL string | `_decode_string_literal` 手動 escape 處理保留 unicode；`_quote_string_literal` 給 list_shortcut_expression 安全引用 | `src/ait/query.py:186, 754, 794` | ✅ |
| `f609e6b` Fix B-H1 reconcile unmapped | `unmapped_mappings` 計入結果；`manual_repair_required = bool(unmapped)`；保留 post_rewrite_path 並寫 marker | `src/ait/reconcile.py:24, 42-74` | ✅ |
| `34ea016` Fix NEW-CR1 event lifecycle | events 的 ownership_token 校驗順序、attempt_started 對 terminal early-return、attempt_promoted 寫 verified_status、reaper BEGIN IMMEDIATE 等都進 HEAD | `events.py:113, 233-236, 335-365, 415` | ✅ |
| `7c56ae6` Fix B-L7 promotion ref | `if not promotion_ref.startswith("refs/heads/"): raise EventError(...)` | `events.py:344` | ✅ |
| `2ca075b` Fix A-F5 outcome markers | 移除 `"traceback"` 這類過寬子字串；改 `"ait harness"`、`"harness binary"`、`"signal sigint"`、`"received sigint"` | `src/ait/outcome.py:81-92` | ✅ |
| `7b7d9f8` Fix A-F8 idresolver LIKE escape | `LIKE ? ESCAPE '\\'` + `_escape_like(value)` 對 `%` `_` `\` escape | `src/ait/idresolver.py:56-72` | ✅ |
| `9b0b683` Fix B-H2 hook + transport | hooks.py:14 `cat >>`；daemon_transport.py 對既有 socket live probe 拒絕、`chmod(0o600)` | `src/ait/hooks.py:14`；`src/ait/daemon_transport.py:59, 68` | ✅ |
| `6505382` daemon lifecycle/concurrency | NB-H2/H3 join verifier、duplicate event 不 spawn、合併 client error log 等 | `daemon.py` 整體 | ✅ |
| `c0ac04b` config atomic writes | `_write_text_atomic(path, ...)` 寫 tmp 後 `os.replace`；config.py / .gitignore 都走 atomic | `src/ait/config.py:61, 122, 126-130` | ✅ |
| `891fe27` adapter real-binary | `_same_file` samefile-aware 比對；wrapper recursion 提前 fail | `src/ait/adapters.py:541+` | ✅ |
| `2b3f0d2` memory context quality | context cap、redact intent text、advisory recall 過濾、CJK token in eval | `runner.py`、`context.py`、`brain.py`、`memory_eval.py` | ✅ |
| `bea0819` codex transcript | normalize spinner 字 / progress 行 dedup | `src/ait/transcript.py` | ✅ |
| `246bb59` harness retry state | `_finish_failed` 與 `_finish_attempted` 分離；__exit__ 不再 auto-finish 已失敗的 finish；utc_now 統一 | `src/ait/harness.py:79, 107, 174-180` | ✅ |
| `9208377` DB and workspace hardening regressions | tests | tests/* | ✅ |
| `0b59ae8` Document attempt commit lifecycle | `docs/implementation-notes.md` 補 ait attempt commit 章節 | docs | ✅ |
| `35be919` Add Staff review docs | 三個 review docs + refactor plan 進 HEAD | `docs/code-review-2026-04-30.md`, `2026-05-01.md`, `claude-followup-2026-05-01.md`, `architecture-refactor-plan.md` | ✅ |

### follow-up #1 已有的 8 commits（再確認仍在）

`a9ed5d6` NEW-CR2、`1e36d70` QA-2-H5 stabilize、`98013fe` NEW-H1、`fdb6878` NEW-H2 全在 HEAD 線上，與上述 commits 相互依存且測試綠。

---

## 三、特定驗證項目逐條對照

### 1. NEW-CR1 working-tree / HEAD split

- `git status --short` → **空輸出**（乾淨）
- `git ls-files --others --exclude-standard` → **空**（無 untracked）
- `git diff HEAD --stat` → **空**（無未 commit 變動）
- review docs 都進 HEAD：
  ```
  docs/code-review-2026-04-30.md
  docs/code-review-2026-05-01.md
  docs/code-review-claude-followup-2026-05-01.md
  docs/architecture-refactor-plan.md
  ```
- 三個新測試檔（test_ids.py、test_outcome.py、test_redaction.py）也進 HEAD
- 隨機抽查證實上輪「working tree 才有」的修法現在都 in HEAD：redaction 13 patterns、ids secrets+monotonic、query CJK、reconcile manual_repair、events BEGIN IMMEDIATE、attempt_started early-return、attempt_promoted writes verified_status、idresolver LIKE escape、hooks `>>`、socket chmod 0600

**判定**：✅ **完全解決**

### 2. NEW-CR2 daemon orphan blocker

#### a. SIGTERM 進入 graceful shutdown
- `serve_daemon` 在 line 156 一進 try 就 `_install_stop_signal_handlers(stop_event)`
- handler（daemon.py:432-441）對 SIGTERM/SIGINT 都 `stop_event.set()` 然後 return
- `run_accept_loop` 在主迴圈 line 257 檢查 `stop_event.is_set()` 立即 return
- finally 跑：`stop_event.set()`（已 set 過）→ `reaper_thread.join(5.0)` → `_join_verifier_threads(5.0)` → `conn.close()` → `server.close()` → 移除 socket 與 pid file → `_restore_signal_handlers`

✅ **Graceful path 完備**

#### b. stop_daemon 等死 + SIGKILL fallback
- `daemon.py:72-89`：
  ```
  os.kill(status.pid, signal.SIGTERM)
  process = _STARTED_DAEMON_PROCESSES.pop(status.pid, None)
  if process is not None:
      try: process.wait(timeout=5.0)
      except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5.0)
  elif not _wait_for_pid_exit(status.pid, timeout=5.0):
      try: os.kill(status.pid, signal.SIGKILL)
      except OSError: pass
      _wait_for_pid_exit(status.pid, timeout=2.0)
  ```
- 兩條路徑（自啟 / 外部 pid）都會等死 + SIGKILL 兜底

✅ **修復**

#### c. verifier / client cleanup 真實執行
- `_handle_client_safely` 把 client error 印 stderr（daemon.py:289）
- `_verify_attempt_in_background` 把 verifier error 印 stderr（daemon.py:340）
- `_join_verifier_threads` 在 stop 時被 finally 呼叫，會輪詢 `_VERIFIER_THREADS` list 並 join，未完成的 thread 會被收集進下一輪
- regression：`tests/test_daemon_verifier_threads.py` 三個測試（含 verify failure log + thread join + lifecycle hardening）

✅ **修復**

#### d. 實機測試 daemon 殘留
- 跑 pytest + unittest 兩遍後系統有 **317 個 ait daemon process** 在運行
- 多數年齡 0:15 ~ 3:48；80 個是最近 1 分鐘新生
- 但這 **不是** runtime 級 production blocker，原因見「四、test hygiene 殘留風險」

### 3. NEW-H1 abandon / supersede terminal guard
- `src/ait/app.py:460-461`：
  ```python
  if intent.status not in {"open", "running"}:
      raise ValueError(f"Cannot abandon {intent.status} intent")
  ```
- `src/ait/app.py:489-490`：
  ```python
  if intent.status not in {"open", "running"}:
      raise ValueError(f"Cannot supersede {intent.status} intent")
  ```
- 對 finished / abandoned / superseded 三種 terminal 狀態都拒絕

✅ **修復**

### 4. NEW-H2 fallback finish idempotent
- `src/ait/events.py:233-236`：
  ```python
  def handle_attempt_finished(...) -> bool:
      if attempt.reported_status == "finished" and attempt.result_exit_code is not None:
          return False
  ```
- 短路後不執行任何 UPDATE，所以：
  - `ended_at`：保留第一次的（不會被 sent_at CASE 覆寫）
  - `raw_trace_ref`：保留
  - `result_exit_code`：保留
  - 也不會更新 `evidence_summaries` 的 raw_trace_ref / logs_ref

✅ **修復**

### 5. 其他這輪新 commits

| 主題 | commit | 狀態 |
|---|---|---|
| event lifecycle hardening | 34ea016 + 6505382 | ✅ |
| promotion target ref validation (refs/heads only) | 7c56ae6 | ✅ |
| outcome marker cleanup (移 traceback / ^c → 真 SIGINT marker) | 2ca075b | ✅ |
| idresolver LIKE escape | 7b7d9f8 | ✅ |
| hook append + daemon socket transport hardening (chmod 0600 + live probe) | 9b0b683 | ✅ |
| daemon lifecycle / concurrency hardening | 6505382 | ✅ |
| memory context quality（cap / redact intent / advisory filter / CJK） | 2b3f0d2 | ✅ |
| adapter real-binary detection (samefile-aware) | 891fe27 | ✅ |
| config atomic writes | c0ac04b | ✅ |
| regression tests + review docs tracking | 9208377 + 35be919 | ✅ |

---

## 四、新發現的殘留風險

### NEW-M1（Medium，**test hygiene 不是 production blocker**）— `test_runner.py` 的 35 條 daemon-spawning tests 沒清理 daemon

**事實**：審查跑完兩套測試後 `ps -eo` 顯示 **317 個 ait daemon process** 仍活著，多數年齡 0-3 分鐘。

**根因**：
- `src/ait/runner.py:109` `run_agent_command` 必呼 `start_daemon(root)`（這是 production 設計，daemon 在背景持續服務）
- `tests/test_runner.py` 有 30+ 個 test 直接叫 `run_agent_command(...)`，每次生 daemon
- 沒有 `addCleanup(stop_daemon, root)` 也沒有 `tearDown` 統一清理
- `with tempfile.TemporaryDirectory()` 結束後 tempdir 刪光，daemon's cwd 變失效但 daemon 進程繼續活著
- 預設 `DEFAULT_DAEMON_IDLE_TIMEOUT_SECONDS=600`（10 分鐘），daemon 會在 10 分鐘 idle 後自殺，期間累積

**為什麼不是 production blocker**：
1. production user 跑 `ait run` 是頻繁但有間隔的，daemon idle_timeout=600s 在大多數情境下會自我清理
2. 連續 `ait run` 同一 repo 會 reuse 同一 daemon
3. user 顯式 `ait daemon stop` → SIGTERM handler 走 graceful shutdown（已驗證）
4. 機器重啟 daemon 也消失
5. SIGTERM 對單獨 orphan 仍有效（前次 follow-up 親驗 `kill -TERM <pid>` 即死）

**為什麼仍需處理**：
1. 開發者跑 unit test 累積 100+ orphan，吃 macOS / Linux fd 與 inode 上限
2. CI 短時間多次跑 test 也會累積
3. 發布前 sanity check 容易看到「為什麼這麼多 daemon」嚇到

**修法（任一）**：
- (a) `tests/test_runner.py` 的 setUp 寫 `self.addCleanup(stop_daemon, repo_root)`
- (b) test 設 `config["daemon_idle_timeout_seconds"] = 1` 讓 daemon 自己快速 exit
- (c) 加一個 fixture 在 module 級 tearDown 跑 `_kill_orphan_daemons` 掃殘留 process

**驗收**：
- 跑完 pytest + unittest 後 `ps -eo pid,args | grep "ait.cli daemon serve" | grep -v grep` 應 ≤ 5
- session 結束後逐步 idle-timeout 掉

### NEW-M2（Medium）— `add_attempt_memory_note` 型別簽名仍宣告 `-> MemoryNote`

**位置**：`src/ait/memory.py:401-413`
**證據**：function 在 line 408-409 早 return None，但簽名仍 `-> MemoryNote`
**影響**：mypy / pyright 會抱怨；caller 端不知道要 handle None
**修法**：簽名改 `-> MemoryNote | None`，更新 caller 端 None handling
**驗收**：`mypy src/ait/memory.py` 對此函式無新 error

### NEW-L1（Low）— `_handle_client_safely` 與 `_verify_attempt_in_background` 用 `print(file=sys.stderr)` 預設 buffered

**位置**：`src/ait/daemon.py:289, 340`
**證據**：detached daemon 的 stderr 通常 block-buffered，SIGTERM 後 buffer 可能丟失
**影響**：偶發 debug 看不到 warning
**修法**：加 `flush=True`
**驗收**：daemon 故意觸錯後 log 仍可見（即使 SIGTERM 緊接而來）

---

## 五、是否仍有 critical/high production blocker

**Critical**：**無**
- NEW-CR1 已完全 commit（git 乾淨）
- NEW-CR2 graceful shutdown + stop_daemon SIGKILL fallback 都到位

**High**：**無**
- NEW-H1 abandon/supersede terminal guard 落地
- NEW-H2 finish idempotent 落地

**Medium 殘留**：1 條 test hygiene（NEW-M1）+ 1 條型別簽名（NEW-M2）

**Low 殘留**：1 條 stderr flush（NEW-L1）

---

## 六、是否有任何修法只存在 working tree 沒進 HEAD

**無**。

驗證：
- `git diff HEAD --stat` → 空
- `git ls-files --others --exclude-standard` → 空
- 隨機抽查 redaction、ids、query、reconcile、events、outcome、idresolver、hooks、daemon_transport、config、adapters、memory、harness 都在 HEAD

NEW-CR1 在這輪完全解決。

---

## 七、是否有測試不足或 flaky 風險

| 風險 | 位置 | 評估 |
|---|---|---|
| `test_start_daemon_recovers_running_attempt_after_sigkill` 用 `time.sleep(1.1)`、`reaper_ttl_seconds=1` | `tests/test_daemon_lifecycle.py` | **flaky 中** — CI 慢機可能偶發 fail；建議 sleep 上拉到 2.0 並加 retry |
| `test_daemon_e2e.py` 多個 subprocess + timeout=60 | `tests/test_daemon_e2e.py` | 一般情況穩；極端 IO load 下可能 timeout 但 60s 足夠 |
| test_runner 不清理 daemon → 連跑數次測試 fd 增 | `tests/test_runner.py` 30+ 個 `run_agent_command` test | 見 NEW-M1 — **build/CI 風險** |
| sleep-based race shaping（先前 follow-up 已標 Q1-L2） | `tests/test_daemon_concurrency.py:101` | 現況可接受但建議改 Barrier |
| test_memory_security 對 prompt-injection 的 3 條 e2e | `tests/test_memory_security.py:15, 46, 77` | strict assertion，覆蓋上輪 LE-NEW-CR1 攻擊向量 |
| test_concurrency 兩 process 同 intent create_attempt | `tests/test_concurrency.py:42` | 用 `multiprocessing.spawn` 真並發，cover NB-H1 |

**結論**：除 NEW-M1 (test_runner daemon 不清理) 外，無重大測試缺口。

---

## 八、若仍 NOT READY，必修項與 file:line

**Verdict**：**READY WITH CONDITIONS**（不是 NOT READY）

理由：
- 4 個指定驗證點（NEW-CR1 / NEW-CR2 / NEW-H1 / NEW-H2）全 ✅
- 22 commits 邏輯清晰、git 乾淨、test 雙綠、無 working tree split
- daemon orphan **runtime** 已 mitigation（idle_timeout + SIGTERM handler + stop_daemon wait + SIGKILL fallback）
- 殘留是 test hygiene + 1 條型別 + 1 條 stderr flush，三者皆非 runtime production blocker

**conditions**（建議在 release 前處理）：
1. **NEW-M1**（Medium）`tests/test_runner.py` 30+ 個 `run_agent_command` test 加 `addCleanup(stop_daemon, repo_root)` 或統一設短 idle_timeout
2. **NEW-M2**（Medium）`src/ait/memory.py:401` 函式簽名 `add_attempt_memory_note` 改 `-> MemoryNote | None`
3. **NEW-L1**（Low）`src/ait/daemon.py:289, 340` 兩處 `print(..., file=sys.stderr)` 加 `flush=True`

可同 PR 處理；不需阻擋當前 release。

---

## 九、誠信宣告

- 全程 read-only review，沒改任何 source / test / docs
- 每條判定都附 file:line 與實機證據
- 兩套測試套件實機跑出 383 passed / 383 OK
- 22 commits 逐個 source 檢視，git diff 對照前次 follow-up 標記為 working tree only 的修法都已進 HEAD
- daemon 殘留問題用 `ps -eo` 實機驗證 317 個進程，並追根因到 `test_runner.py` 的 cleanup 缺口（非 runtime 機制問題）
- 不假裝、不偽造、不 fabricate
