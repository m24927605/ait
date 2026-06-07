# Worktree 重入協調原語設計（S1）

> **⚠️ SUPERSEDED（2026-06）**：本方案僅為支撐「daemon 背景自動刪 worktree」而生。經
> review 揭示其根本複雜度（shell-integration eval 路徑無持久 process，可靠「使用者在場」
> 偵測需 heartbeat/TTL），且背景自動刪整體已放棄。改採
> `docs/worktree-cleanup-hint-design-zh.md`（只提示、使用者主動刪，無需重入協調）。
> 本文件保留作決策記錄。

## Scope Statement

為 AIT 增加 worktree「重入協調原語」，讓任何刪除 retained worktree 的流程（互動
`ait cleanup --apply` 及未來 daemon 自動 prune＝S2）在刪除前能可靠偵測「有人正透過
`ait resume`/`ait continue` 進入該 worktree」，根治刪除與重入之間的 TOCTOU race。
本切片只做協調原語、單一 session 語意與重入路徑接線；daemon 常駐 prune（S2）在此原語
之上另案實作。

## Problem

worktree 在 attempt 為 terminal 時被 cleanup 視為可回收。但使用者可重新進入 retained
worktree，而現況協調不一致，使「使用者正在 worktree 裡、尚未改檔變 dirty」時可能被刪
（cwd 被拔；commit 仍在 object store 但 session 被毀）：

| 進入路徑 | 現況 | ait process 是否存活 |
| --- | --- | --- |
| `agent-continue`（`continue_cmd.py:339-345`） | **已**寫 active lease(owner=ait pid) | 是（agent subprocess 期間） |
| manual `launch_resume_shell`（`resume.py:182-190`） | `subprocess.run([shell])` 等待，**未**寫 active lease | 是（shell 期間 ait wait） |
| shell-integration eval（`resume_shell_script`，`continue_cmd.py:34`，經 `shell_integration.py` `ait()` `eval`） | 使用者 shell 直接 `cd`，**未**寫 lease | **否**（ait 產生 script 後退出） |
| `recover`（`cli/recover.py`） | 只 print，不進入 | — |

並且 `_lease_cleanup_block()`（`cleanup.py:300-319`）只對 orphan 用 active lease 擋刪；
`cleanup_repo` 的 evaluate→delete 間無互斥。

## 核心語意決策

**每個 worktree 同時只允許一個 active 重入 session（single active session）。** 並發
進入被**明確 busy 拒絕**（不 block、不覆蓋既有 owner）。理由：避免多 owner / refcount /
lease-directory 的持久格式（YAGNI，且 brainstorm non-goal 已排除 multi-owner）；同一
retained worktree 被多人同時進入罕見。這同時消除「多 eval shell 互相覆蓋 owner_pid、較新
shell 先退使 cleanup 誤刪舊 shell 所在」的 critical race，以及「持 exclusive lock 整個
session 致第二者無限 block」的問題。

## Goal

1. 三條進入路徑統一在進入時宣告 single active session，刪除側可靠偵測。
2. 刪除瞬間以 flock 臨界區關閉 recheck→delete 的 TOCTOU 窗口。
3. 純標準庫 `fcntl.flock`、沿用既有 `workspace_lease` schema 與 `lease_owner_alive`、沿用
   `.ait/locks/` 模式；不新增持久格式、不破壞 shell auto-path 與 recover 語意。

## Non-goals (this change)

- **不做 daemon 常駐 prune**（S2）。
- **不支援同一 worktree 的並發重入 session**（明確拒絕，見核心語意決策）。
- **不新增 lease JSON schema 欄位**；沿用 `state`/`owner_pid`/`owner_started_at`。
- **不強制可靠 shell EXIT trap**；正確性靠 owner_pid liveness，leave hook 僅 best-effort。
- **不改 recover 為進入 worktree**。
- `--force` 只覆蓋 dirty，不覆蓋 live active lease 或 busy lock。

## Design

### 為何「flock + active lease liveness」結合

- flock-only 不足：eval 路徑無長存 ait process，無法跨退出持 `fcntl` lock。
- lease-only 不足：仍有 cleanup「最後讀 lease」與「真正刪除」間的 final-delete race。
- 結合：flock 臨界區序列化「進入時檢查+寫 lease」與「cleanup recheck+delete」；active
  lease + owner_pid liveness 表示 session 進行中（單一），涵蓋無持久 process 的 eval 路徑。

### §1 共享 helper（新模組 `src/ait/worktree_activity.py`）

**lock 與 enter/leave 分層（回應「API 自相矛盾／巢狀自我死鎖」）**：lock 由 context
manager 提供；enter/leave 為 `*_locked` 變體，**假設 caller 已持 lock、自己不再取**，避免
同 process 對同檔巢狀 flock 自鎖（POSIX flock 為 per-open-file-description，不同 fd 同 process
會互鎖）。

```python
@contextmanager
def worktree_activity_lock(repo_root, workspace_ref):
    """取 .ait/locks/worktree-<id>.lock 的 fcntl.flock(LOCK_EX|LOCK_NB)。
    拿不到即 raise WorktreeBusy（caller 轉 busy 拒絕／cleanup skip）。"""

def active_session_owner(repo_root, workspace_ref):
    """（須在 lock 內呼叫）回傳目前 live active lease 的 (owner_pid, owner_started_at)
    或 None（無 active lease，或 lease 為 active 但 owner 已 dead＝stale）。"""

def enter_worktree_activity_locked(repo_root, workspace_ref, attempt_id, *, owner_pid,
                                   owner_started_at, owner_command):
    """（caller 持 lock）寫 state='active' lease；回傳 prior_state 供 leave 還原。"""

def leave_worktree_activity_locked(repo_root, workspace_ref, *, owner_pid,
                                   owner_started_at, restore_state):
    """（caller 持 lock）僅當 lease owner_pid/owner_started_at 仍 match 自己才把 state
    還原為 restore_state（進入前的 terminal state）；否則 no-op；workspace 不存在則 no-op。"""
```

**lock identity（回應「normalization」）**：`lock_id = sha256(str(Path(workspace_ref).resolve())
.encode())[:16]`；`resolve()` 解 symlink，且不要求路徑存在（deleted worktree 仍導出確定值），
確保所有 caller（進入路徑與 cleanup）導出同一 lock path。case-insensitive 檔案系統的同路徑
大小寫差異風險記錄為已知（與既有 `_branch_ref_lock` 同等假設）。

**single active session 入口協議**（所有進入路徑共用）：

```
with worktree_activity_lock(repo_root, ws) as ok:   # LOCK_EX|NB；WorktreeBusy → busy 拒絕
    existing = active_session_owner(repo_root, ws)
    if existing is not None and existing != mine:
        raise WorktreeBusy                          # 已有他人 live active session
    # recheck worktree 仍存在且 attempt 可 resume；否則拒絕（見各路徑）
    enter_worktree_activity_locked(..., owner_pid=mine_pid, ...)
# 離開 lock 後，session 由 active lease(owner liveness) 表示
```

### §2 三條進入路徑接線

**(a) process-backed：`launch_resume_shell`（resume.py）**

由 `subprocess.run` 改 `subprocess.Popen` 取 child shell PID。順序（parent 持 lock 整個
session，最強保護）：

```
with worktree_activity_lock(repo_root, ws):          # 拿不到 → 報 busy、不啟 shell
    if active_session_owner(...) not in (None, mine): raise WorktreeBusy
    proc = subprocess.Popen([shell], cwd=ws, env=...)         # ① spawn child
    enter_worktree_activity_locked(..., owner_pid=proc.pid, ...) # ② 寫 active lease
    # parent 持 lock 全程；cleanup 的 LOCK_EX|NB 必失敗 → skip worktree-busy
    rc = proc.wait()
    leave_worktree_activity_locked(..., restore_state=prior)
return rc
```

- **crash 窗口（已知 limitation）**：①spawn 與 ②寫 lease 之間 parent ait 若**異常終止**
  （非正常 wait），flock 隨 fd 關閉釋放、lease 未寫、child shell 成孤兒仍在 worktree 內 →
  cleanup 可能刪。窗口為兩相鄰語句間（μs 級），root-cause 為 parent 異常死亡（罕見）。本
  切片接受並記錄，不引入額外 mitigation（YAGNI）。
- agent-continue（`continue_cmd.py:339-345`）：同樣以入口協議在啟動 agent 前 enter、持 lock
  至 agent 結束再 leave；沿用既有 succeeded/failed settle。

**(b) shell-integration eval：`resume_shell_script`（continue_cmd.py:34）**

無長存 ait process，靠「lease owner_pid = 使用者互動 shell PID」+ liveness：

1. `shell_integration.py` 的 `ait()` function（`:147-168`）在呼叫
   `command ait continue … --shell-hook` 前 `export AIT_SHELL_PID=$$`（互動 shell PID；
   `$(...)` 有中間 subshell，ait 自身 `getppid()` 為 subshell 不可用，故須由 shell function
   顯式傳入）。
2. `ait continue --shell-hook` 的 ait process：
   - **驗證 `AIT_SHELL_PID`（回應偽造風險）**：須為正整數、PID alive、且**屬當前 UID**
     （拒絕跨 UID，例如以 `/proc/<pid>` owner 或平台等價檢查）；記錄 `owner_started_at`
     （`_pid_started_at`）以防 PID reuse；任一不符 → 退出非 0、**不輸出 cd script**。
   - 於 `worktree_activity_lock` 內：依入口協議檢查 single session + **recheck worktree 仍
     存在且 attempt 可 resume**（回應「enter 前 worktree 被刪」）；不符（含 cleanup 先贏 lock
     刪除）→ 退出非 0、不輸出 cd script（`ait()` 的 `eval ""` 為 no-op，fallback
     `command ait` 提示 busy/已回收）。
   - 通過則 `enter_worktree_activity_locked(owner_pid=AIT_SHELL_PID, ...)` 寫 active lease，
     釋放 lock，輸出 eval script。
3. **正確性靠 liveness**：使用者 shell 存活期間 owner alive → cleanup 擋刪（保守
   over-retention：shell 活著即保留，即使已 `cd` 離開，可接受）。shell 退出後 lease stale →
   由 `lease_owner_alive` 回收，cleanup 才刪。
4. **leave hook 為 best-effort 優化（不納入本切片，列 Open Question）**：正確性不依賴它。

### §3 cleanup 整合（強化既有 `cleanup_repo`）

- **`_lease_cleanup_block` 改為對任何 attempt 擋 live active lease**：現況
  `state=="active" and lease_owner_alive and attempt is None` 才 retain；改為
  `state=="active" and lease_owner_alive`（去掉 `attempt is None`），對 terminal attempt 的
  live active lease 同樣 retain（reason `active-lease`）。owner **dead** 的 stale active
  lease 不擋（依原 policy 回收）。
- **刪除臨界區**：在 apply 刪除點（`cleanup.py:145-148`），對判定 remove 的項目以
  `worktree_activity_lock`（LOCK_EX|NB）：
  - `WorktreeBusy`（process-backed session 持有）→ item `skip`、reason `worktree-busy`。
  - 取得後**在同一 lock 內**：重讀 lease（live active → skip `active-lease`）、dirty
    （→ `dirty`）、active dev server（→ `active-dev-server`）、fresh DB status（非 terminal
    → `raced-reactivated`）；全不命中才**在同一 lock 內** `_delete_worktree_item`。eval 路徑的
    enter（亦在同 lock 內檢查+寫 lease）被序列化，TOCTOU 關閉。
- 互動 `ait cleanup --apply` 一併受益、更保守；CLI 介面與既有 reason 體系不變（新增
  `worktree-busy`/`raced-reactivated` 仍走 cleanup report，符合安全不變量 #7）。

### §4 leave / settle 與 stale 回收（回應 minor）

- **leave settle**：`restore_state` = 進入前的 terminal lease state（由 enter 回傳的
  `prior_state`）。manual resume/eval **不改 DB attempt status、不改 retention**（resume 僅
  檢視；唯 `--finish` 才走既有 apply 流程）。leave 僅在 owner match 時把 lease 由 active 還原
  為 prior_state；owner mismatch / workspace 已刪 → no-op（防 nested/舊 trap 誤清）。
- **stale 回收**：owner dead 的 active lease 由 `lease_owner_alive`（PID + `owner_started_at`
  防 reuse，`workspace_lease.py:172-200`）判定 → 不擋刪，依原 policy 回收。
- `--force` 不刪 live active lease / busy lock（只覆蓋 dirty）。
- corrupt/missing lease 不阻塞 cleanup；enter 在 lock 內重寫有效 active lease。

## Testing

`tests/test_worktree_activity.py`（新）：

- lock 互斥：`worktree_activity_lock` 持有時第二取 → `WorktreeBusy`；釋放後可再取。
- `active_session_owner`：live active → 回 owner；dead owner active → None（stale）。
- enter 寫 active + owner_started_at；`leave` owner mismatch → no-op、workspace 不存在 → no-op。
- single session：已有他人 live active 時入口協議 → `WorktreeBusy`。
- lock identity：symlink 與直接路徑 resolve 至同 lock_id；deleted worktree 仍導出確定 lock_id。

`tests/test_cleanup.py`：

- terminal/stale failed attempt + **live** active lease → 不刪（`active-lease`）；**dead**
  active lease → 依原 policy 可刪。
- 外部持 worktree lock 時 `--apply` → `skip`/`worktree-busy`。
- 同一 lock 內 recheck 期間 lease 變 active / dirty / dev-server / DB 非 terminal → 各 skip
  並驗 reason；全不命中才刪。
- `--force` 不刪 live active lease / busy lock，只影響 dirty。

`tests/test_cli_resume.py`：mock `Popen`，`launch_resume_shell` 持 lock→enter→wait→leave；
持 lock 期間外部 LOCK_EX|NB 失敗；已有他人 active session 時報 busy、不啟 shell；env/path
sanitizer 不回歸。

`tests/test_cli_continue.py`：agent-continue 持 lock 至結束再 leave；`--shell-hook`：缺失/
非當前 UID/非整數 `AIT_SHELL_PID` → 退出非 0、不輸出 script；worktree 已刪 → 不輸出 script；
正常 → enter(owner=AIT_SHELL_PID) 後輸出含 `AIT_RESUME_*` 的 script。

`tests/test_shell_integration.py`：`ait()` 在 `--shell-hook` 前 export `AIT_SHELL_PID=$$`；
snippet idempotent；既有 auto-path/reminder 不回歸。

全套：`PYTHONPATH=src python3 -m unittest discover -s tests` 綠燈。

## Rollout

- 純加法 + cleanup 更保守（多擋 live active lease、busy lock、single-session 拒絕並發），
  無 schema migration。
- `launch_resume_shell` 由 `run` 改 `Popen`：保持 returncode/env/cwd 語意。
- shell snippet 變更（export `AIT_SHELL_PID`）：idempotent、不破壞既有 trap 與 auto-path。
- **與 S2 銜接**：S2 daemon prune 在本原語上接 reaper；其 v9 §3「apply 前 final recheck」由
  本切片的 **lock 臨界區內 recheck+delete** 取代/強化（recheck 與 delete 同 lock 互斥，更強）。
  S2 落地時據此簡化其 §3。

## Open Questions

1. **eval leave hook 是否納入後續**：建議**不納入本切片**（正確性靠 liveness，leave 僅優化）。
   若要「shell 一退出即清」，後續加 zsh `add-zsh-hook zshexit`、bash 僅在無既有 `EXIT` trap
   時安裝非破壞性 trap。
2. **single active session 對 UX 的影響**：同一 worktree 第二個 resume/continue 會被 busy
   拒絕。建議接受（罕見、且避免 refcount 複雜度）；若實際有並發檢視需求，再評估 multi-owner
   lease-directory（另案，違反本切片 non-goal）。

## References

- `docs/daemon-worktree-prune-design-zh.md` — S2（本原語之上的 daemon prune）
- `src/ait/workspace_lease.py:51-200` — `create/update_workspace_lease`、`lease_owner_alive`、
  `_pid_started_at`
- `src/ait/workspace.py:576-587` — `_branch_ref_lock`（`fcntl.flock` + `.ait/locks/` 模式）
- `src/ait/resume.py:182-190` — `launch_resume_shell`（`run` → `Popen`）
- `src/ait/cli/resume.py:60`、`src/ait/cli/continue_cmd.py:34,60,339-345` — 三條進入路徑
- `src/ait/shell_integration.py:107,147-168` — `ait()` function（`AIT_SHELL_PID` 注入點）、
  auto-path
- `src/ait/cleanup.py:145-148,300-319` — apply 刪除點、`_lease_cleanup_block`（改任何 attempt
  擋 live active lease + lock 臨界區）
- `src/ait/cli/recover.py` — recover 只 print、不進入
