# Daemon 常駐 Worktree 自動回收設計

> **⚠️ SUPERSEDED（2026-06）**：本方案（daemon 背景自動刪 worktree）經多輪 design review
> 評估，安全成本（與 resume/recover/continue 重入的 TOCTOU race、需重入協調原語）遠超
> 收益，已**放棄**。改採 `docs/worktree-cleanup-hint-design-zh.md`（只提示、使用者主動刪）。
> 本文件保留作決策記錄與可複用發現（containment DoS 修復、skip_migrations 並發分析、
> status cleanup_hint 設計）。

## Scope Statement

把既有的 `cleanup_repo()` 接進 daemon 常駐 reaper，讓被標記 `crashed/failed`
的 worktree 在到期後不只更新 DB 狀態、也回收磁碟。本變更是
`minimal-interruption-worktree-design-zh.md` →「自動 Prune」段的延伸：為其入口
清單新增缺少的「daemon 常駐週期」觸發點。同時對 `cleanup_repo()` 做 review 驅動的
強化（§2 `skip_migrations` 參數、§2 DoS 修復、§3 final recheck / conn 生命週期），
互動 `ait cleanup` 一併受益。**不**新造清理引擎、**不**改 `ait cleanup` CLI 介面與
決策矩陣、**不**新增 repo config、**不**自動刪 `succeeded`。

## Problem

`.ait/workspaces/` 長期堆積過時 worktree，缺自動回收。現況：

- 清理引擎 `cleanup_repo()`（`src/ait/cleanup.py`）已存在且安全（決策矩陣 + 三層
  保護：lease/dirty/active dev server；per-item 刪除失敗記入 `CleanupItem.error` 不拋，
  `cleanup.py:393-402`）。
- 自動觸發只掛 `ait run` 啟動（`_safe_startup_prune`，`cli/run.py:332`，`run.auto_prune`
  gate，預設 True，`policy.py:62`）與 land/apply 當下。
- daemon 常駐 reaper（`daemon_reaper.py:run_reaper_loop`）每 `scan_interval` 只
  `reap_stale_attempts()` 標記 `crashed/failed`（改 DB），**不回收磁碟**。

破洞：(1) 自動清理只掛 `ait run`；(2) reaper 標 crashed 卻不刪 worktree；(3) `succeeded`
無上限堆積；(4) orphan 只 opt-in 時清。本切片解 1、2，對 3 做非破壞性提示，4 維持現狀。

## 決策（review gate 拍板）

- **D1 orphan**：daemon cleanup 等同 `ait cleanup --apply`，orphan 跟隨 config
  （`cleanup.include_orphans`，預設 False 即 skip）。
- **D2 預設啟用**：daemon 週期 cleanup 預設啟用，`run.auto_prune`（預設 True）gate；
  opt-out = `run.auto_prune=false`。
- **D3 recover race**：刪除前 final recheck（status/lease/dev-server），見 §3。

## Goal

1. daemon 常駐期間定期執行等同 `ait cleanup --apply` 的安全 policy，回收
   `promoted/discarded` 與超過 retention 的 `failed/crashed`，不依賴指令路徑。
2. 對 `succeeded` 保留 worktree 給彙總提示。
3. 零新依賴、零新 repo config、不改 CLI 介面與決策矩陣、保留三層保護。

## Non-goals (this change)

- **不自動刪 `succeeded`**（detached commit 非 durable ref；安全不變量 #4）。
- **不改 orphan 預設**（D1 跟隨 config，預設 False）；不加 `orphan_retention_days`。
- **不持久化 throttle**。
- **不新增 repo config**；opt-out 用 `run.auto_prune`。
- **不改 `ait cleanup` CLI 介面與決策矩陣、不改既有 reason 體系**。但**會**對
  `cleanup_repo()` 內部做三處強化：(i) 新增 `skip_migrations: bool=False` 參數
  （§2，預設 False 不影響既有呼叫）；(ii) containment 前置（§2 DoS）；(iii) apply 前
  final recheck + conn 生命週期（§3）。互動 cleanup 一併受益、行為更保守。
- **不改** daemon 既有事件錯誤路徑（`daemon.py:199`、`events.py:456-457`）。

## Design

### 1. 接入點：reaper loop 新增週期性 cleanup

`run_reaper_loop()` 維持現有順序，新增第四步（於 `db_lock` 釋放後）：

```python
def run_reaper_loop(
    *, conn, db_lock, stop_event,
    heartbeat_ttl_seconds: int, scan_interval_seconds: float,
    startup_grace_seconds: float, repo_root: Path | None = None,
    workspace_cleanup_interval_seconds: float = DEFAULT_DAEMON_CLEANUP_INTERVAL_SECONDS,
) -> None:
    interval = workspace_cleanup_interval_seconds
    if interval <= 0:                      # 防呆：零/負值會每 loop 跑
        print("ait daemon: invalid workspace_cleanup_interval_seconds "
              f"{interval}, clamping to {MIN_DAEMON_CLEANUP_INTERVAL_SECONDS}",
              file=sys.stderr, flush=True)
        interval = MIN_DAEMON_CLEANUP_INTERVAL_SECONDS    # = 1.0
    last_cleanup = None
    ...
    # 每輪，db_lock 釋放後：
    if repo_root is not None and run_auto_prune(repo_root):
        now = time.monotonic()
        if last_cleanup is None or (now - last_cleanup) >= interval:
            _run_workspace_cleanup(repo_root)
            last_cleanup = now             # end-to-start；僅在實際跑時推進
    # auto_prune 為 False 時整個 if 跳過、last_cleanup 不推進，
    # 故切回 True 後首輪即可立刻跑。
```

- **Retry / end-to-start**：helper 不向上拋（§2），`last_cleanup` 不論成敗都更新
  （retry = 每 interval 一次）；在 cleanup 返回後更新，實際間隔 = `cleanup_duration +
  interval`。
- **常數**：production 固定 `DEFAULT_DAEMON_CLEANUP_INTERVAL_SECONDS = 3600.0`（不可由
  config 調）；`MIN_DAEMON_CLEANUP_INTERVAL_SECONDS = 1.0`（clamp 下限）。測試用小正值。

### 1b. Daemon 生命週期與停止回應（契約）

1. **stop 延遲**：cleanup 執行中 loop 不檢查 `stop_event`；stop 延遲到 cleanup 返回後。
2. **join 有界**：關閉 `reaper_thread.join(timeout=5.0)`（`daemon.py:95`）；cleanup >5s
   則 join 超時、主線程續關，reaper thread 因 `daemon=True`（`daemon.py:81`）隨 process
   終止。
3. **中途退出**：`git worktree remove --force` 對單一 worktree 相對原子；中途被殺則
   已刪的已刪、未刪留待下次，半刪殘留由下次 cleanup 與 `git worktree prune`
   （`cleanup.py:166`）收尾。不需交易式回滾。
4. **子程序有界（回應「join 可棄置 thread，需 cleanup 操作有界」）**：cleanup 的 git
   子程序（`worktree remove`/`prune`、dirty `status`）應設 timeout——`workspace.py` 與
   `cleanup.py` 的 `_git_run`/`_git` 現況 `subprocess.run` **無 timeout**；本切片為其加
   timeout（如 30s），逾時 → 該 git 呼叫拋 → 落入 per-item `CleanupItem.error` 或整體
   except，不致無限卡死。`_path_size()` 的遞迴遍歷無 subprocess、受檔案系統限制，最壞
   單次有界但可能慢（見 Open Question 3）。經此 shutdown 最壞延遲 ≈ 單項 git timeout
   量級；join 5s 超時後 daemon thread 仍因 `daemon=True` 隨 process 結束。
5. **接受此同步設計**（YAGNI）：throttle 1hr 撞 shutdown 機率低、且子程序有界。

### 2. cleanup helper、可觀察性、並發（skip_migrations）、DoS 修復

```python
def _run_workspace_cleanup(repo_root: Path) -> None:
    try:
        policy = cleanup_policy_from_config(repo_root, apply=True, worktrees=True, artifacts=False)
        report = cleanup_repo(repo_root, policy, skip_migrations=True)   # 見「並發契約」
    except Exception as exc:               # 含 config 壞值、CleanupError；daemon 路徑無 migration 寫鎖
        print(f"ait daemon cleanup warning: {exc}", file=sys.stderr, flush=True)
        report_internal_error(category="daemon.workspace_cleanup", exc=exc)
        return
    removed = [it for it in report.items if it.deleted]
    errored = [it for it in report.items if it.error]
    if removed:                            # bounded 成功 log（回應 rollout 可見性）
        print(f"ait daemon cleanup: removed {len(removed)} worktree(s), "
              f"reclaimed {report.reclaimed_bytes} bytes", file=sys.stderr, flush=True)
    if errored:
        sample = "; ".join(f"{Path(it.path).name}: {it.error}" for it in errored[:5])
        more = "" if len(errored) <= 5 else f" (+{len(errored) - 5} more)"
        msg = f"ait daemon cleanup: {len(errored)} item(s) failed to delete: {sample}{more}"
        print(msg, file=sys.stderr, flush=True)
        report_internal_error(category="daemon.workspace_cleanup_items",
                              exc=RuntimeError(msg), context={"errored_count": len(errored)})
```

- 重用既有引擎與 builder（DRY）。**per-item 刪除失敗不中止 cleanup**：`_delete_worktree_item`
  已內部 try/except 存入 `CleanupItem.error`（`cleanup.py:393-402`），刪除迴圈
  （`cleanup.py:145-148`）不因單項失敗中斷；helper 檢查 report 回報 bounded summary。
  helper 的 `except` 僅捕捉 `cleanup_repo()` **整體**拋出（config 壞值、`CleanupError`）。
- **policy（D1）**：不傳 `include_orphans` → 採 config（預設 False）（`cleanup.py:105,111`），
  與 CLI 不帶 `--include-orphans` 一致。worktrees=True、artifacts=False、force off、
  retention 取 config 或預設 14。`artifact_allowlist` 不適用（artifacts=False）。
- **等價範圍（精確，回應「等同 ait cleanup --apply」）**：等價 = **CLI 預設行為**——
  worktree 清理、artifacts 預設關。`ait cleanup` 的 `--artifacts` 為 `store_true`
  （預設 False，`cli_parser.py:303-309`），故 daemon `artifacts=False` **正是** CLI 預設、
  非偏離。差異僅 daemon 預設 `apply=True`（CLI 需顯式 `--apply`）與 `skip_migrations=True`
  （CLI False）；決策矩陣與 reason 完全相同。
- **Retention 矩陣（daemon cleanup 對每個 status，沿用既有 `_terminal_decision`
  `cleanup.py:322-331`）**：

  | attempt 狀態 | daemon 動作 |
  | --- | --- |
  | `promoted` / `discarded` | **remove**（立即，無 retention 等待） |
  | `succeeded` | retain（reviewable，不刪，只在 §5 提示） |
  | `failed` / `crashed` | 超過 retention（config 或預設 14 天，自 `ended_at` 起算）→ remove；否則 retain |
  | `created` / `running` | retain（active） |
  | `verified=pending` 且非 crashed | retain |
  | orphan（無 DB row） | 跟隨 `include_orphans`（D1，預設 skip） |
  | 任一 + dirty / active dev server / active|preserve|conflict lease | retain/skip（force off） |

  retention **自 `ended_at` 起算**；reaper 標記 crashed 時把 `ended_at` 設為當下
  （`events.py`），故 reaper 製造的 crash 從「偵測標記時刻」起算 retention，而非最後心跳
  （明確語意，測試覆蓋）。
- `report_internal_error` 簽名 `(*, category, exc: BaseException, context=None,
  user_facing=None)`（`bug_report/api.py:18`，**無 `message=`**）。

**並發契約（`skip_migrations`：daemon 路徑完全只讀，根治寫鎖）**：問題根源是
`cleanup_repo()` 呼叫 `run_migrations()`，後者無條件 `BEGIN IMMEDIATE` + `set_meta`
UPSERT + commit（`db/core.py:83-131`），在 `db_lock` 外取 write lock。**修正**：
`cleanup_repo()` 新增 `skip_migrations: bool = False`；為 True 時**跳過** `run_migrations()`。
daemon 路徑傳 `skip_migrations=True`——前提成立：`serve_daemon()` 啟動已在
`with db_lock: run_migrations(conn)`（`daemon.py:64-65`）完成遷移後才啟 reaper
（`:69-83`），故 reaper cleanup 時 schema 必為最新。如此 daemon cleanup 對 DB **完全
只讀**（`connect_db` 的 PRAGMA 在已是 WAL 時不取寫鎖；`list_attempts` + §3 `get_attempt`
皆讀），**不取 write lock**，與 daemon 寫者在 WAL 下並發安全、不會 `database is locked`。
互動 `ait cleanup` 維持 `skip_migrations=False`（自行 migrate）。daemon 事件側既有錯誤
路徑不變、本切片不依賴它處理 cleanup 引發的鎖（因已無寫鎖）。

**`skip_migrations=True` 防呆 guard（回應「若被未 migrate 路徑呼叫」）**：`cleanup_repo()`
在 `skip_migrations=True` 時，先讀 `schema_version` meta 並斷言 `== SCHEMA_VERSION`；不符
（stale 或缺）則拋 `CleanupError`，fail-safe 拒跑（由 helper except 捕捉 → warn + skip）。
如此即使未來有路徑在 migration 前誤呼叫，也不會在 stale schema 上靜默運作。`_run_workspace_cleanup`
亦於文件註明：僅應於 daemon 啟動 migration 完成後由 reaper 呼叫。

**Malformed config（兩種）**：(i) JSON 壞 / `cleanup` 非 dict → `_load_cleanup_config()`
回 `{}`（`cleanup.py:185-194`）→ 走預設、不崩；(ii) `cleanup` 為 dict 但欄位壞值
（`failed_retention_days` 非整數/負）→ `cleanup_policy_from_config()` 拋（`cleanup.py:98-103`）
→ helper except → warn + skip + 重試。不改 config loader。

**可觀察性**：(a) cleanup_repo 整體拋 → except + 上報；(b) per-item 失敗 → report 回報
bounded summary；(c) 連續失敗每 interval 重試重報；(d) **成功亦 log**（removed 數 +
reclaimed bytes，bounded）。

**Redaction**：stderr / `report_internal_error` 的 message 只用 basename
（`attempt-NNNN-<ulid>`），不主動拼絕對路徑。**`item.error`（git/fs 原始訊息）未遮蔽、
可能含絕對路徑**，會進 stderr 與 bug-report——明確接受（與既有 reaper warning 層級一致；
bug-report 有自身 redaction）。

**DoS 修復（containment 前置）**：`_evaluate_worktree()` 現況 `_path_size(resolved)`
（`cleanup.py:228`）在 `_path_is_inside`（`:229`）之前——corrupted ref 指向 workspaces
外時背景每小時遞迴 walk 才 skip。**修正**：`_path_is_inside` 移到 `_path_size` 前，
`outside-ait-root` 直接 skip（size 記 0、不遍歷）。

### 3. apply 前 final recheck（D3）與 conn 生命週期

**Race**：`cleanup_repo` 先 `_evaluate_worktree` 判 remove、之後才 `_delete_worktree_item`
真刪。背景刪除特有：stale worktree 在窗口內被 `recover`/`continue` 重啟（同步點：
`continue_cmd.py:333-336` `reported_status="running"` + `:339-345`
`update_workspace_lease(state="active")`）或外部寫入變 dirty。

**conn 生命週期**：`cleanup_repo` 開頭連線現於 `cleanup.py:132` close；改為保留至函式
結束（`finally: conn.close()`），dry-run 與 apply 同一連線。apply 階段供 final recheck
的 `get_attempt()` **只讀**查詢（skip_migrations 下全程只讀）。連線僅主 cleanup 執行緒用。

**final recheck 的具體形態（回應「精確 API/控制流」）**：**新增獨立 helper**，不重跑
`_evaluate_worktree`（避免重算 size 重新引入 DoS、避免重判 terminal decision）：

```python
def _recheck_worktree_protections(
    workspaces_root: Path, worktree_path: Path,
    attempt: AttemptRecord | None, conn, *, force: bool,
) -> tuple[bool, str] | None:
    """刪除前重查保護。回傳 (blocked, reason)；None 表示可續刪。
    只做保護判斷，不算 size、不重判 terminal/orphan 決策。"""
```

**輸入與比較規則**：`attempt` 為**原始快照**（提供 `attempt.id` 作 DB 查詢 key 與身分）；
helper 內用 `get_attempt(conn, attempt.id)` 取 **fresh** record，比較其
`reported_status`/`verified_status` 是否已非 terminal（terminal = `failed`/`crashed`
且 `verified` 非 `succeeded`/`pending`/`promoted` 中可重啟者；以既有
`_terminal_decision`/`_recover_status` 的 terminal 判定為準）。`attempt is None`（orphan）
時**跳過** DB status 檢查（orphan 無 DB 記錄，由 include_orphans policy 決定）。

**檢查順序與 reason 優先序（短路，確保決定性）**：依序 (1) lease、(2) dirty、(3) active
dev server、(4) DB status（fresh `get_attempt`）；**第一個命中者決定 reason**。故 recover/
continue 已寫 active lease 時 reason = `active-lease`（優先於 `raced-reactivated`）；僅當
lease/dirty/dev-server 皆未命中、但 fresh DB status 已非 terminal（「DB 改了但 lease 尚未
寫 active」的微窗口）才回 `raced-reactivated`。

控制流：在 `cleanup_repo` 的 apply 刪除點（`cleanup.py:145-148`），`if policy.apply and
item.action == "remove":` **之後、`_delete_worktree_item()` 之前**呼叫；非 None 則把該
item.action 改 `skip`、reason 設回傳值、不刪。recheck 內依上述順序檢查並**沿用既有 reason**：

| recheck 命中 | reason |
| --- | --- |
| lease active（owner alive / attempt running） | `active-lease` / `active` |
| lease preserve_reason | `lease-preserved` |
| lease conflict / orphan | `conflict` / `orphan` |
| dirty 且非 force | `dirty` |
| active dev server | `active-dev-server` |
| `get_attempt()` 顯示 status 已非 terminal（回到 created/running/succeeded/pending） | **新增 `raced-reactivated`** |
| `get_attempt()` 拋 DB 錯誤 | **fail-safe**：blocked、reason `recheck-unavailable`，不刪 |

僅「DB status 在快照後變化」與「recheck 不可用」用新 reason；其餘沿用既有，report
可解釋性不降（不變量 #7）。改為 skip 的項計入 report。此邏輯重用 `_lease_cleanup_block`、
`_is_dirty_worktree`、`_has_active_dev_server`（皆即時讀），避免重複實作保護判斷。

### 4. daemon 接線、常數歸屬與 repo_root

- 常數 `DEFAULT_DAEMON_CLEANUP_INTERVAL_SECONDS = 3600.0`、`MIN_DAEMON_CLEANUP_INTERVAL_SECONDS
  = 1.0` 定義在 **`daemon_reaper.py`**（`run_reaper_loop` 簽名引用；放 daemon.py 會與
  `daemon.py:16` 循環 import）。
- `serve_daemon()` 顯式 import 常數傳入 kwargs（`daemon.py:71-79`）。
- `repo_root` 由 `serve_daemon` 的 `resolve_repo_root()`（`daemon.py:48`）解析傳入
  （`:78`），daemon 路徑恆 non-None；`None` 只在單元測試、由守衛跳過。

### 5. succeeded 保留提示（status dashboard）

`_recovery_dashboard_payload()` 已 `:217` `list_attempts(conn)` 取全部 attempt，零額外
query 計算彙總。

**containment 共用 util**：把 `cleanup.py:_path_is_inside` 提為共享 public util
（`path_is_inside(child, parent)`，置於 `workspace.py` 或小 util 模組），`cleanup.py`
與 `status_helpers.py` 共用，避免 CLI 依賴私有函式或重複實作。

**workspace_ref 處理（相對 ref 一律視為異常，回應矛盾）**：DB 現存**絕對** resolved
path（`workspace.py:155`）；相對 ref **非**現況合法資料。故：

- `Path(workspace_ref).is_absolute()` 為 False → 視為 corruption、計入
  `anomalous_succeeded_refs`、**不**計 retained（不做 `root / p` 補救）。
- 絕對 ref → `resolved = Path(workspace_ref).resolve()`。

**計入 `retained_succeeded_worktrees`**（全滿足）：`verified_status == "succeeded"`；ref
為絕對；`resolved.exists()`；`path_is_inside(resolved, get_workspaces_root(root).resolve())`
（symlink 逃逸不計）。

**異常診斷**：被排除的 succeeded ref（相對 / broken / symlink 逃逸 / `OSError`，含權限）
→ 計入 `anomalous_succeeded_refs`，使漂移在 JSON 可見、非全靜默；text 不為此加行。
（權限與 missing 不細分；統一計 anomalous，由 debug/JSON 承載。）

**JSON 形狀（向後相容：既有 key 全保留不變，`cleanup_hint` 為純新增頂層欄位；所有回傳
分支都存在）**：

```json
"cleanup_hint": {
  "retained_succeeded_worktrees": 0,
  "anomalous_succeeded_refs": 0,
  "next_steps": []
}
```

- `not_initialized`、`empty` early-return（`status_helpers.py:200-232`）附固定全 0。
- count > 0 時 `next_steps` 為非空字串陣列、須含關鍵指令（`ait apply`、`ait cleanup`）。
  **測試只斷言**結構（非空 list、含 `ait apply`/`ait cleanup` 子串），**不 bake** 完整句。

**text 承載 renderer（單一插入點）**：`_format_status`（`:499`）於 `:505`
`extend(_format_status_current_work(...))`，包含後者輸出。故：

- `_format_status_current_work`（`:579`）：`retained_succeeded_worktrees > 0` 加**一行**
  （`_format_status` 自動繼承，不在其自身另加）。
- `_format_status_condensed`（`:383`，獨立）：加同一行。
- count==0 不加；**不加**：`whereami`、`_format_status_all`。
- 文案**不得**暗示 cleanup 直接刪 succeeded；以實作 CLI 既有措辭為準。

### 安全不變量對齊

- #3 不刪含 uncommitted tracked changes → `force=False` + dirty check + §3 final recheck。
- #4 不刪無 durable result 的 succeeded → retain + 提示。
- #7 自動清理可由 report 解釋 → 重用既有 reason（§3 mapping），新增
  `raced-reactivated`/`recheck-unavailable`/`outside-ait-root` 仍走 report。
- #8 JSON/API 相容 → 既有 key 不變，`cleanup_hint` 純新增。

## Testing

`tests/test_daemon_reaper.py`：

- **決定論**：直接寫 attempt `ended_at`（+ heartbeat/started）為過去時間。
- stale failed/crashed 超過 retention → 鎖外觸發 cleanup 並刪；recent failed 保留；
  succeeded 保留。
- **鎖外觸發**：fake helper / monkeypatch `cleanup_repo`，被呼叫時斷言
  `db_lock.acquire(blocking=False)` 成功、**斷言後立即釋放**再返回。
- **並發無逸出（skip_migrations）**：兩執行緒（daemon 寫事件 + 真實 cleanup
  `skip_migrations=True`）驗證正常無 `database is locked`；斷言 cleanup 路徑**未**呼叫
  `run_migrations`（monkeypatch/spy）。
- **停止（§1b）**：fake 慢速 cleanup，cleanup 執行中才 `stop_event.set()`，驗證 loop 等
  返回後才結束、不卡死。
- **throttle / clamp**：scan 短、cleanup interval 長 → 只呼叫一次；慢速驗證下次落在
  `duration+interval`；`interval<=0` 被 clamp 到 1.0 並 log；`auto_prune=false` 時不跑且
  `last_cleanup` 不推進（切回 true 後首輪即跑）。
- **失敗/成功可觀察**：(a) cleanup_repo 連續拋 → 不中止、每 interval warning/上報、
  `last_cleanup` 推進；(b) per-item 失敗（monkeypatch 刪除原語強制 `CleanupItem.error`）→
  bounded summary；(c) malformed config 兩種（i 走預設、ii warn+skip+重試）；(d) 成功
  刪除 → log removed 數 + reclaimed。

`tests/test_cleanup.py`：

- **skip_migrations**：`skip_migrations=True` 時不呼叫 `run_migrations`、仍正確 list +
  刪除；`skip_migrations=False`（互動預設）行為不回歸。
- **D1**：config `include_orphans` 未設/false → orphan skip；true → orphan 清。
- 不刪 succeeded / dirty / active dev server。
- **§2 DoS**：ref 在 workspaces 外 → `outside-ait-root` skip，spy `_path_size` 斷言未對
  外部路徑遍歷。
- **§3 final recheck**：評估 remove 後、刪除前模擬 (i) lease active、(ii) dirty、
  (iii) dev server、(iv) DB status 變 running/succeeded → 各改 skip 並**驗 reason**
  （`active-lease`/`dirty`/`active-dev-server`/`raced-reactivated`）、未刪；get_attempt 拋
  → `recheck-unavailable` skip。既有互動 cleanup（dry-run、既有 reason）不回歸。

status 測試：JSON 一般/`empty`/`not_initialized` 皆含 `cleanup_hint`（三欄位）；text
condensed 與 `_format_status` count>0 各**恰一行**（無重複）、count==0 不含；
`_format_status_all`/`whereami` 不含；相對/broken/symlink/OSError ref → 不計 retained、
計 anomalous；既有 JSON key 不變；`next_steps` 只斷言結構與關鍵指令子串。

全套：`PYTHONPATH=src python3 -m unittest discover -s tests` 綠燈。

## Rollout

- 純加法，無 schema migration。
- **預設開的 destructive 背景行為（D2）—— release 可見性**：
  - CHANGELOG / release note 明列：「daemon 常駐期間現在會週期（預設每小時）自動回收
    terminal worktree（promoted/discarded、超過 retention 的 failed/crashed）；預設啟用，
    `run.auto_prune=false` 可完全停用。」
  - 文件新增一節說明背景行為、刪除範圍與 opt-out。
  - 可見性：cleanup 每次**成功刪除 log removed 數 + reclaimed bytes**、失敗 log summary
    （見 §2），皆落 daemon log；cleanup report 亦可解釋每項決策。
- 互動 `ait cleanup` 因 §2/§3 強化更安全；`skip_migrations` 預設 False 不影響其行為。
- 落地 PR 同步更新 `minimal-interruption-worktree-design-zh.md` →「自動 Prune」入口清單
  並處理 Open Question 1。

## Open Questions

1. **母設計文字差異**：「自動 Prune」曾列「orphan 超過 retention 且 clean」可自動清，
   實作為 config opt-in（D1 維持）。落地 PR 更新該段。
2. **`succeeded` 自動回收**（需人工決定，不阻塞）：archive-before-delete 封存格式、保留
   天數、recover/resume 語意。本階段僅 status 提示。
3. **效能後續優化**（非本切片）：`cleanup_repo()` 對 retain 項目跳過 `_path_size()`。

## References

- `docs/minimal-interruption-worktree-design-zh.md` — 母設計
- `src/ait/cleanup.py:98-103,105,111,118-123,127-132,145-148,166,185-194,226-230,293-296,393-402,500` —
  retention 壞值、policy builder（include_orphans=None 跟隨 config）、init 前置、
  **conn 生命週期 / skip_migrations 插入點**、apply 刪除點、`worktree prune`、
  `_load_cleanup_config`、**containment/size 順序（DoS）**、dirty skip、
  `_delete_worktree_item`（per-item error 不拋）、`_path_is_inside`（提為共用 util）
- `src/ait/daemon_reaper.py` — `run_reaper_loop()`（接入點、常數、interval clamp）
- `src/ait/daemon.py:16,41-42,48,64-65,69-83,81,95,199` — import 方向、常數、
  `resolve_repo_root`、啟動先 migration（skip_migrations 前提）、kwargs、`daemon=True`、
  join、既有錯誤路徑
- `src/ait/events.py:456-457` — 事件 rollback + `report_internal_error`（既有）
- `src/ait/cli/continue_cmd.py:333-345` — continue 重啟同步點（§3 recheck）
- `src/ait/db/core.py:48-58,83-131` — WAL/busy_timeout；`run_migrations` 寫鎖（skip_migrations 依據）
- `src/ait/bug_report/api.py:18` — `report_internal_error` 簽名（無 `message=`）
- `src/ait/policy.py:62` — `run_auto_prune()`（D2 gate）
- `src/ait/cli/cleanup.py` — CLI `include_orphans` 傳 None 對照（D1）
- `src/ait/cli/status_helpers.py:185,200-232,217,383,499,505,579,675` — dashboard、
  early returns、renderer、delegate 點
- `src/ait/cli_parser.py:303-309` — `ait cleanup` 旗標預設
- `src/ait/app.py:211-262` — `create_attempt()` worktree/DB 順序（orphan 罕見性）
