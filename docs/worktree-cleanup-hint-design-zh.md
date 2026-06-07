# Worktree 可回收提示設計

## Scope Statement

**核心（本切片）**：在 `ait status` 顯示「可回收 worktree」提示，讓使用者知道何時該回收
堆積的 worktree——刪除永遠由使用者主動 `ait cleanup --apply` 觸發（既有且安全）。本方案
**不做** daemon 背景自動刪除。

附帶的 **cleanup 引擎 robustness 硬化**（malformed-ref / symlink 安全 / delete-time
containment 等，由設計 review 挖出的既有技術債）**拆為獨立 follow-up，不阻塞核心提示**
（見「Follow-up」段）。核心只需「status 唯讀計數對任何 ref 都不 crash」。

## 背景：為何不做背景自動刪（決策記錄）

最初構想是把 `cleanup_repo()` 接進 daemon reaper 做背景自動回收（見已 superseded 的
`daemon-worktree-prune-design-zh.md` S2 與 `worktree-reentry-coordination-design-zh.md`
S1）。經多輪設計 review，評估其安全成本遠超收益：背景刪除與 `ait resume`/`recover`/
`continue` 的重入有真實 TOCTOU race（使用者正在 worktree 裡、cwd 被背景刪），需跨路徑協調
原語（flock + active lease）；shell-integration eval 自動 cd 路徑**無持久 ait process**，
可靠的「使用者在場」偵測需 heartbeat/TTL。而互動 `ait cleanup` 的既有 dirty/lease/dev-server
保護對「使用者主動刪」已足夠。故保留刪除為使用者主動，只**提升可見性**。

## Problem

`.ait/workspaces/` 長期堆積過時 worktree。清理引擎 `cleanup_repo()` 已存在且安全，但
使用者缺「該清理了」的可見訊號：reaper 標 `crashed/failed`（`events.py`）的可回收 worktree
不被提示；`succeeded` 未 promote 的 worktree 無上限堆積；自動 prune 只掛 `ait run` 啟動
（`cli/run.py:332`），走其他路徑者不觸發也不知情。

## Goal

1. `ait status` 計算並提示「可回收 worktree」數量與一鍵指令，純讀、無刪除、無 race。
2. 對 `succeeded` 保留 worktree 一併提示（apply/discard 後可回收）。
3. status 唯讀計數對**任何** `workspace_ref` 值（含 malformed/hostile）都不 crash。
4. 零新依賴、零新 repo config、不改 `ait cleanup` 決策矩陣、不碰 resume/lease/flock、不改
   cleanup 刪除路徑（後者列 Follow-up）。

## Non-goals

- **不做** daemon 背景自動刪 worktree；**不做** worktree 重入協調原語（S1）。
- 不改 resume/continue/recover/lease 行為；不新增 repo config；不改 `ait cleanup` CLI 介面
  與決策矩陣。
- 本切片**不改 cleanup 刪除路徑**（containment DoS / symlink / delete-time recheck 等列
  Follow-up）。

## Design（核心：status cleanup_hint）

### §1.1 共享分類函式（status 計數；cleanup 去重為 Follow-up）

從 `cleanup.py:_terminal_decision`（`:322-331`）抽出純判定，回傳結構化結果：

```python
@dataclass(frozen=True)
class TerminalDecision:
    category: str   # "reclaimable" | "retained_succeeded" | "not_reclaimable"
    reason: str     # 既有 reason：promoted|discarded|reviewable|stale-failed|retention-window

def classify_terminal(attempt, *, retention_days) -> TerminalDecision: ...
```

- promoted/discarded → `(reclaimable, "promoted"|"discarded")`；succeeded →
  `(retained_succeeded, "reviewable")`；failed/crashed 超 retention →
  `(reclaimable, "stale-failed")`，未超 → `(not_reclaimable, "retention-window")`；其餘 →
  `(not_reclaimable, "reviewable")`。
- status 用它計數。`cleanup._terminal_decision` 改用它去重（映回既有 `(action, reason)`、
  決策矩陣不變）**建議一併做、但屬 Follow-up，不阻塞核心**。

### §1.2 metric 語意：樂觀上界

`reclaimable_worktrees` 是**樂觀上界**：僅基於 terminal status + retention，**不含** cleanup
實際 `--apply` 時的 dirty / lease / dev-server 保護（其中 dirty 需逐一跑 `git status`，刻意
不在 status 做以維持輕量）。文案**不得**承諾「這 N 個都會被刪」，而導向 dry-run：「約 N 個
worktree 可回收，跑 `ait cleanup` 查看精確清單、`ait cleanup --apply` 回收」。

`retention_days` 取自 cleanup 同一來源 `cleanup_policy_from_config(repo_root)`（→
`_load_cleanup_config`，預設 `DEFAULT_FAILED_RETENTION_DAYS = 14`）；status 為唯讀，若該呼叫
拋**任何 `Exception`**（負/非整數/null/list 等）→ fallback 至 14、設 `config_warning: true`，
**絕不** raise。`_older_than_retention`（`cleanup.py:350-368`）沿用既有語意不改（無法解析→
不計 reclaimable；naive 當 UTC；fallback `ended_at or heartbeat_at or started_at`）。

### §1.3 status 端 ref 安全（唯讀不 crash；核心）

status 讀 DB `workspace_ref` 計數，必須對任何值健壯：

- **safe_resolve_workspace_ref(workspace_ref) -> Path | None**：絕對 ref →
  `Path(workspace_ref).resolve()`（`strict=False`）；相對 ref，或 `Path(...)`/`resolve()` 拋
  `OSError`/`RuntimeError`/`ValueError`/`TypeError`（malformed/hostile，如 embedded null
  byte）→ `None`。
- **計數**：`None`、或 resolved 不在 `get_workspaces_root(root).resolve()` 下（§1.5
  `path_is_inside`，symlink 逃逸即不符）、或 `exists()` 拋 `OSError` → 計 `anomalous_refs`、
  **不**計 reclaimable/retained；resolved 在內且 `exists()` 才計入 category。
- **anomaly reason（caller 賦予）**：`is_absolute()` False→`relative-ref`；resolve 拋→
  `resolve-error`；resolved 在 workspaces_root 外→`outside-root`；`exists()` 拋→
  `exists-error`。
- **既有 latest-attempt 欄位硬化**：`_recovery_dashboard_payload` 既有欄位
  （`lease_payload`、`Path(...).exists()`、`workspace_lease_path`、`_dev_server_payload`，
  `status_helpers.py:240-242`）也直接用 `attempt.workspace_ref`；若**最新** attempt 的 ref
  malformed/hostile，會在新計算外 crash status。改用 guarded 取值（包 try/except
  `OSError`/`ValueError`/`RuntimeError`/`TypeError` → 視為不存在/lease None）。
- **dedupe**：以 resolved workspace path 去重（重複/corrupt row 指同一 workspace 只計一次）；
  衝突優先序（不依 DB 順序）：`reclaimable` > `retained_succeeded` > `not_reclaimable`；
  `anomalous_refs` 以 raw ref 去重。

### §1.4 JSON 與 text 輸出

**JSON 形狀**（`cleanup_hint` 為 `_recovery_dashboard_payload()`（`:185`）新增頂層欄位，在其
全部三個 return 分支 `not_initialized`(`:200`)/`empty`(`:219`)/一般(`:286`) 都存在；前二者全
0；既有 key 不變）：

```json
"cleanup_hint": {
  "reclaimable_worktrees": 0,
  "retained_succeeded_worktrees": 0,
  "anomalous_refs": 0,
  "config_warning": false,
  "next_steps": [],
  "anomalies": []
}
```

- `anomalies`（一律填 JSON）：`{attempt_id, workspace_ref, reason}`；hostile DB 值的
  newline/控制字元在 **text renderer 需 escape/截斷**，JSON 保留原值。
- `next_steps`：`reclaimable > 0` → 含 `ait cleanup`（dry-run）、`ait cleanup --apply`；
  `retained_succeeded > 0` → `ait attempt list --verified-status succeeded`、`ait apply
  <attempt>` 或 `ait attempt discard <attempt>`、再 `ait cleanup --apply`；`config_warning`
  → 含「cleanup config 無效，`ait cleanup` 可能失敗，請修正 `.ait/config.json`」。測試只斷言
  結構與關鍵指令子串，不 bake 完整句。
- whereami 是獨立 producer（`cli/whereami.py:12` `state.to_dict()`，不經
  `_recovery_dashboard_payload`），JSON 與 text **皆不含** `cleanup_hint`（無矛盾）。

**text 承載 renderer（單一插入點）**：`_format_status`（`:499`）於 `:505` `extend(
_format_status_current_work(...))` 包含後者輸出。故：

- `_format_status_current_work`（`:579`）：計數>0 加**一行**（`_format_status` 自動繼承，不在
  其自身另加）；`_format_status_condensed`（`:383`，獨立）：加同一行。
- 皆 0 不加；`anomalous_refs > 0` 加一行 warning（`ait status --format json` 看
  `cleanup_hint.anomalies`）；`config_warning` 加一行。**不加**：`whereami`、`_format_status_all`。
- 文案**不得**暗示 `ait cleanup --apply` 直接刪 succeeded。

### §1.5 共用 containment util

把 `cleanup.py:_path_is_inside`（`:500`）提為共享 public util `path_is_inside(child, parent)`
（置 `workspace.py` 或小 util 模組），status（與未來 Follow-up 的 cleanup 硬化）共用。**error
語意**：catch `(ValueError, OSError, RuntimeError)` → `False`（滿足「fs 錯誤不弄壞唯讀 status」）。

## Follow-up（獨立 robustness 硬化，不阻塞核心）

以下為 18 輪 design review 挖出的 **cleanup 刪除路徑既有技術債**，與核心 status 提示（唯讀、
不刪）獨立。建議另開切片實作，本切片**不**納入（避免無限精細化阻塞核心）。各項已有明確方向：

1. **containment DoS（所有 `_path_size` 前先 containment）**：`_evaluate_worktree`
   （`cleanup.py:226-230`）現 `_path_size` 在 `_path_is_inside` 前——corrupted/外部 ref 遞迴
   walk 才 skip；`_evaluate_artifact`（`:416-436`）outside 分支亦 size 外部。修：containment
   移到 size 前，外部 emit skip item（size 0、不遍歷）。
2. **artifact symlink 安全**：allowlisted artifact 為 symlink 時 resolve 可落在 workspaces_root
   內**另一 worktree**、被當 target 刪除。修：symlink artifact 直接 skip（`is_symlink`/lexists
   discovery，含 broken symlink）；containment 相對 owning `worktree_path`；刪除用原始 candidate
   路徑。需改 `_artifact_candidate_paths`（不 resolve）、`_evaluate_artifact`（加 `worktree_path`
   參數）。
3. **worktree symlink / 重複 resolved path**：symlinked worktree path resolve 到另一 worktree
   可被誤刪。修：skip symlink worktree candidate；ambiguous 重複 resolved path 在 remove 前 skip。
4. **delete-time containment**：`_delete_worktree_item`（`:393-402`）以 `attempt.workspace_ref`
   刪（非已評估 `item.path`）、無 final recheck。修：刪前以 `item.path` 重查 containment/非
   symlink-escaped，target 變動則 skip。需改簽名（加 `workspaces_root`）。
5. **anomalous-ref candidate model**：`_workspace_candidate_paths` 現回 `tuple[Path]`，無法承載
   raw-string anomalous item。修：定義 candidate record（`raw_ref`/`resolved_path`/`attempt`/
   `anomaly_reason`/`dedupe_key`），cleanup 對 safe_resolve→None 的 ref emit `anomalous-ref`
   skip item（path=raw、bytes=0、計 scanned_count）。
6. **新 skip/report states**：為上述各 case 定義穩定 `reason` 字串與 `CleanupItem` 形狀
   （`action`/`reason`/`bytes`/`deleted`/`error`），更新 cleanup JSON/decision_report/formatter
   /tests；text renderer 對 hostile ref escape/截斷。

注：核心 §1.3 的 `safe_resolve_workspace_ref` 與 §1.5 `path_is_inside` 設計上即供這些 Follow-up
共用，故核心先落地不會與 Follow-up 衝突。

## Testing（核心）

`tests/test_cleanup.py`：

- **classify_terminal**：各分支回 `(category, reason)`（promoted/discarded→reclaimable；
  succeeded→retained,"reviewable"；超 retention failed/crashed→reclaimable,"stale-failed"；
  未超→not,"retention-window"；malformed/None `ended_at`→保守 not）。

`tests/test_status_*.py`：

- JSON 三分支（一般/`empty`/`not_initialized`）皆含 `cleanup_hint`（六欄位）；計數正確（含 0）。
- **config fallback**：invalid config（負/非整數/null/list）→ 不 raise、retention 用 14、
  `config_warning=true`、text/next_steps 含提示。
- **樂觀上界**：dirty/active-lease/dev-server 但 status 為 stale-failed 的 worktree 仍計
  reclaimable；文案為「約 N、跑 ait cleanup 確認」。
- **ref 安全**：相對/broken/symlink-逃逸/`OSError`/`ValueError`(null byte)/`TypeError` ref →
  不計 reclaimable/retained、計 `anomalous_refs`；`anomalies` 一律填、reason 正確；**最新
  attempt 的 malformed/hostile ref → `ait status`（text 與 JSON）不 crash**（既有欄位 guarded）；
  text 對含 newline/控制字元的 raw ref escape/截斷。
- **dedupe**：同一 resolved path 多 row 只計一次；優先序（succeeded+promoted → reclaimable）。
- text：condensed 與 `_format_status`（經 current_work）計數>0 各**恰一行**（無重複）、皆 0 不含；
  `anomalous_refs>0`/`config_warning` 各一行；`_format_status_all`、`whereami`（JSON 與 text）
  皆不含 `cleanup_hint`。status 計數**不**呼叫 `_path_size`（spy）。
- 既有 JSON key 不變。

全套：`PYTHONPATH=src python3 -m unittest discover -s tests` 綠燈。

## Rollout

- 純加法（status `cleanup_hint` + status 端 ref 安全），**不改 cleanup 刪除路徑**，無 schema
  migration、無行為破壞。status text 多一行（計數>0/anomaly/config_warning 時）；JSON 新增
  `cleanup_hint`；whereami 不變。
- 文件：getting-started / cleanup 文件補一句「`ait status` 提示可回收 worktree，跑
  `ait cleanup --apply` 回收；**`succeeded` 需先 `ait apply` 或 `ait attempt discard`，
  `ait cleanup --apply` 才回收**（cleanup 不直接刪 succeeded）」。
- Follow-up robustness 硬化另開切片（見上）。
- superseded：`daemon-worktree-prune-design-zh.md`（S2）、`worktree-reentry-coordination-
  design-zh.md`（S1）已標 superseded，指向本文件。

## v1 決策（非 blocker）

1. **succeeded 提示門檻**：v1 全部計入（不加「超過 N 天」），太吵再加。
2. **daemon log 提示**：v1 不加（只靠 `ait status`，YAGNI）。

## References

- `docs/daemon-worktree-prune-design-zh.md`、`docs/worktree-reentry-coordination-design-zh.md`
  — superseded（背景自動刪 + 重入協調，已放棄）
- `src/ait/cleanup.py:185-194,322-331,350-368,500`（核心引用）；`:209-218,226-230,393-436`
  （Follow-up 引用）
- `src/ait/cli/status_helpers.py:185,200,219,240-242,286,383,499,505,579` —
  `_recovery_dashboard_payload`（三 return 分支、既有欄位）、四 renderer、delegate 點
- `src/ait/cli/whereami.py:12` — 獨立 producer（不含 cleanup_hint）
- `src/ait/cli_parser.py:303-309` — `ait cleanup` 旗標（使用者主動回收入口）
- `src/ait/workspace.py:155` — `workspace_ref` 為絕對 resolved path（正規化依據）
