# ait 專案 Staff+ Follow-up #3 Code Review

**審查時間**：2026-05-01（third follow-up）
**HEAD commit**：`e475563` (Add second Claude follow-up review report)
**前次 follow-up**：`docs/code-review-claude-followup-2-2026-05-01.md`
**待驗證**：上輪三條 condition（NEW-M1 test hygiene、NEW-M2 type signature、NEW-L1 stderr flush）
**Production readiness verdict**：**READY**（已從 "READY WITH CONDITIONS" 升級為 "READY"）

---

## 一、Final verdict

| 項目 | 上輪狀態 | 本輪狀態 | 證據 |
|---|---|---|---|
| NEW-M1 test_runner daemon cleanup | conditions 待修 | ✅ **已修復** | `tests/test_runner.py:29-49` setUp 加 `addCleanup(stop_started_daemons)` + `_terminate_pid` SIGTERM/SIGKILL helper；實機驗證 35 個 daemon-spawning test 跑完後 daemon count delta = 0 |
| NEW-M2 add_attempt_memory_note 簽名 | conditions 待修 | ✅ **已正確**（其實上輪我誤判）| `src/ait/memory.py:390` 從 commit 919b1bf 起就是 `-> MemoryNote | None`；caller 都正確處理 None |
| NEW-L1 stderr flush | conditions 待修 | ✅ **已修復** | `src/ait/daemon.py:232, 323, 375` 三處 reaper / client / verifier warning 都加了 `flush=True` |

**Critical/High/Medium release blocker**：**無**

**修法只在 working tree 沒進 HEAD**：**無**（git status 乾淨、無 untracked）

---

## 二、實機驗證細節

### 2.1 git status / 提交歷史
- `git status --short` → **空輸出**（乾淨）
- `git ls-files --others --exclude-standard` → **空**（無 untracked）
- 從上輪 baseline `35be919` 起新增 2 commits：
  - `dd6643b` Fix follow-up conditions for daemon test hygiene（同時涵蓋 NEW-L1 stderr flush + NEW-M1 test_runner addCleanup）
  - `e475563` Add second Claude follow-up review report（前次報告 commit 進 HEAD）

### 2.2 兩套測試套件實跑
| Runner | 結果 |
|---|---|
| `.venv/bin/python -m pytest` | **383 passed in 295.95s** ✅ |
| `PYTHONPATH=src python3 -m unittest discover -s tests` | **383 OK in 293.83s** ✅ |

兩套並行執行均綠。

### 2.3 NEW-M1 test_runner daemon cleanup（實機 baseline 測試）

操作流程：
```
BEFORE = ps -eo | grep "ait.cli daemon serve" | wc -l    → 43
PYTHONPATH=src .venv/bin/python -m pytest tests/test_runner.py
sleep 3
AFTER  = ps -eo | grep "ait.cli daemon serve" | wc -l    → 43
DELTA  = 0
```

35 個 test 全綠 + daemon process count **完全沒增加** → NEW-M1 在 test_runner.py 範圍內**完全修復**。

修法 implementation（`tests/test_runner.py:29-49`）：
```python
class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._started_daemon_pids: set[int] = set()
        self._start_daemon_patcher = patch(
            "ait.runner.start_daemon",
            side_effect=self._start_daemon_for_test,
        )
        self._start_daemon_patcher.start()
        self.addCleanup(self._start_daemon_patcher.stop)
        self.addCleanup(self._stop_started_daemons)

    def _start_daemon_for_test(self, repo_root):
        status = _real_start_daemon(repo_root)
        if status.running and status.pid is not None:
            self._started_daemon_pids.add(status.pid)
        return status

    def _stop_started_daemons(self) -> None:
        for pid in tuple(self._started_daemon_pids):
            _terminate_pid(pid)
```

`_terminate_pid` helper（`tests/test_runner.py:1043-1058`）做 SIGTERM → 5 秒 poll → SIGKILL fallback。Pattern 健全，覆蓋 setup error、test exception、normal pass 三條路徑（addCleanup 不會被例外 skip）。

### 2.4 NEW-M2 add_attempt_memory_note 簽名

```
$ grep -n "def add_attempt_memory_note" src/ait/memory.py
390:def add_attempt_memory_note(repo_root: str | Path, attempt_result) -> MemoryNote | None:
```

簽名已是 `MemoryNote | None`。`git log -S` 顯示這簽名從 commit 919b1bf（首次引入此函式）就已是 `MemoryNote | None`——上輪 follow-up #2 的 NEW-M2 finding 是我誤判（讀 line 401 沒對到 line 390 的真簽名）。在此修正前次誤報。

Caller 端 None 處理檢查：
- `src/ait/runner.py:285-287` `_add_attempt_memory_note_with_warning`：忽略回傳值（call 後就丟），無需處理 None ✅
- `tests/test_memory.py:774-783` `test_add_attempt_memory_note_deduplicates_by_source`：明確 `assertIsNotNone(first)`、`assertIsNone(second)`（dedupe 第二次 return None）✅
- `tests/test_memory.py:797-802` `test_add_attempt_memory_note_skips_failed_attempt_source_side`：`assertIsNone(note)`（failed attempt return None）✅

callers 全部正確處理 None。

### 2.5 NEW-L1 stderr flush

```
$ grep -n "flush=True" src/ait/daemon.py
232:            print(f"ait daemon reaper warning: {exc}", file=sys.stderr, flush=True)
323:        print(f"ait daemon client warning: {exc}", file=sys.stderr, flush=True)
375:            print(f"ait daemon verifier warning: {exc}", file=sys.stderr, flush=True)
```

三處 daemon warning（reaper / client handler / verifier background thread）全部加了 `flush=True`。SIGTERM 後 stderr 不會 buffer 丟失。

dd6643b commit diff 確認三處 print 都從 `file=sys.stderr` 改為 `file=sys.stderr, flush=True`，無遺漏。

---

## 三、健全性 (sanity) 觀察

### 3.1 daemon orphan 動態回到 0
驗證流程結束時 `ps -eo` 顯示 daemon count = **0**。先前累積的 43 個 orphan（皆從上輪並行 pytest+unittest 跑出）在 5+ 分鐘內隨 default `daemon_idle_timeout_seconds=600` 自然 idle-timeout 退出。確認：
- `serve_daemon` graceful shutdown 路徑（NEW-CR2 修法）能在 idle-timeout 與 SIGTERM 兩條路徑都正確走完 finally
- `_join_verifier_threads` 與 socket / pid file cleanup 都有跑（否則 .ait 目錄會殘留）

### 3.2 觀察項目（不是 blocker，僅資訊）

#### OBS-1（Info）— pytest + unittest 並行跑時 *其他* daemon-spawning test 仍會短暫累積 orphan
- 範圍：`tests/test_daemon_e2e.py`（subprocess.Popen 跑 `ait.cli run`）、`tests/test_daemon_lifecycle.py`（直接 start_daemon）
- 行為：兩套 runner 並行跑時，這些 test 各自 setup 新 daemon。雖然 finally block 會 stop_daemon，但兩 runner 競爭情境下偶發短暫 orphan，最後在 idle_timeout (600s) 內自清
- 為什麼非 blocker：
  1. 兩 runner 並行不是 production 場景，是 review 工具流程
  2. 各 test 自己有 try/finally + stop_daemon
  3. NEW-M1 dd6643b 的 commit message 明確 scope 為 test_runner.py
  4. NEW-CR2 的 graceful shutdown + idle_timeout safety net 涵蓋之
- 改進建議（可選，非必修）：把同 setUp/addCleanup pattern 推到 `test_daemon_e2e.py` 與 `test_daemon_lifecycle.py`；或為非 e2e 必要的 daemon test 設 `daemon_idle_timeout_seconds=2`

#### OBS-2（Info）— 上輪 NEW-M2 是誤報
我前次 follow-up #2 的「NEW-M2（Medium）型別簽名」實際上 HEAD 已是 `MemoryNote | None`。這次驗證後在本報告 § 2.4 公開更正。沒有需要做的修法。

---

## 四、是否仍有 blocker / working-tree-only 修法

| 類別 | 結論 |
|---|---|
| Critical | **無** |
| High | **無** |
| Medium | **無**（OBS-1 是 test 工具流程的觀察，不算 blocker；OBS-2 是上輪誤報的更正）|
| Low | **無** |
| 修法只在 working tree 沒進 HEAD | **無**（`git status --short` + `git ls-files --others --exclude-standard` 都空）|

---

## 五、Verdict

從上輪 **READY WITH CONDITIONS** 升級為 **READY**。

理由：
1. 上輪 3 條 condition 全部驗證 fixed at HEAD
2. 兩套測試套件實機綠（pytest 383 / unittest 383）
3. NEW-M1 用實機 baseline 比對驗證 test_runner.py 跑完 daemon count delta = 0
4. NEW-L1 三處 print 都加 `flush=True`
5. NEW-M2 是上輪誤報，本來就 OK
6. git 乾淨、無 working-tree-only 修法
7. 無新 critical/high/medium release blocker
8. NEW-CR1 / NEW-CR2 / NEW-H1 / NEW-H2 從上輪起就維持綠

可以 ship。

---

## 六、誠信宣告

- 全程 read-only review，沒改任何 source / test / docs
- 每條判定都附 file:line 與實機證據
- 兩套測試套件實機跑出 383 passed / 383 OK，輸出存於 task output file
- NEW-M1 修法用實機 baseline 比對驗證（BEFORE=43, AFTER=43, DELTA=0）
- NEW-M2 的上輪誤報已在 § 2.4 與 § 3.2 OBS-2 兩處公開更正
- 未殺任何 orphan daemon（read-only 原則）；最終驗證時 daemon count 自然回 0
- 不偽造、不假裝、不 fabricate
