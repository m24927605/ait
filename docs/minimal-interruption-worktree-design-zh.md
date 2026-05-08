# AIT 最低度干擾 Worktree 自動管理設計

狀態：Draft
日期：2026-05-07

## 核心原則

AIT 的 product contract 應該是：

```text
使用者只負責意圖與最後可見狀態的批准。
AIT 負責 execution environment、worktree、branch、patch、cleanup、recovery。
```

換句話說，`git worktree` 是 AIT 的內部實作細節，不應該成為使用者日常心智模型。

使用者應該感知到：

- 我提出任務。
- AIT 在隔離環境完成修改與驗證。
- AIT 告訴我結果。
- 需要改動我目前 checkout、push、開 PR、刪除不確定資料，或發生衝突時，才請我決定。

使用者不應該感知到：

- 要不要手動 `git worktree add/remove/prune`。
- 要不要先 `stash`。
- 要不要自己切到 attempt worktree。
- 要不要自己 rebase attempt。
- 哪個 `.ait/workspaces/attempt-*` 才是正確工作區。

## 目標

1. **隱藏 worktree**
   - 正常文字輸出不顯示 worktree path。
   - JSON/API 可保留 `workspace_ref` 以維持工具相容性。
   - Debug 指令仍可查到完整 workspace metadata。

2. **預設隔離執行**
   - agent run 永遠在 AIT 管理的 internal worktree 執行。
   - 使用者目前 checkout 不因 agent 執行而被修改。
   - 使用者 checkout dirty 時，不要求清理、不自動 stash。

3. **自動套用與整合**
   - 成功 attempt 可以由 AIT 自動計算 landing plan。
   - root clean 且可 fast-forward 時，自動 land。
   - root dirty 但無檔案重疊時，可用 patch/three-way apply 自動整合。
   - root dirty 且有重疊時，只用高階語言請使用者選擇整合策略。

4. **自動清理**
   - 成功 land 且沒有需保留 artifact 時，自動移除 internal worktree。
   - 失敗、中斷、衝突、需要 review 的 attempt 保留短期可復原狀態。
   - AIT 啟動、run、status、cleanup 時可低噪音地 prune stale workspace。

5. **可復原**
   - 在清理任何 worktree 前，AIT 必須確定結果已被 durable ref、commit、patch artifact 或 DB metadata 保留。
   - 中斷或 crash 後，使用者可以用 `ait recover` 找回最近未完成工作。

## 非目標

- 不重寫 Git storage model。
- 不做全自動 semantic merge。
- 不替使用者自動 push 或開 PR，除非使用者明確要求。
- 不在未確認情況下刪除使用者 checkout 中的 untracked 檔案。
- 不要求 v1 支援跨機器同步 workspace metadata。

## 現有基線

目前系統已經具備幾個關鍵基礎：

- `create_attempt_workspace()` 會建立 `.ait/workspaces/attempt-*` detached Git worktree。
- `run_agent_command()` 已經在 attempt workspace 執行 agent command。
- 成功 run 時可以 auto-commit attempt workspace 的變更。
- `attempt promote` 可以把 attempt head 更新到 target branch。
- `attempt land` 可以把 attempt materialize 回 checkout，並在可行時清理 worktree。
- `cleanup` 已經有 retention policy、worktree scan、artifact scan。
- daemon recovery 可以處理 stale running attempts。

主要缺口不是缺少 worktree 能力，而是 UX 還把 worktree 暴露為使用者需要處理的概念。

## 使用者體驗目標

### Happy Path

使用者執行：

```bash
ait run --intent "fix login timeout" -- claude -p "fix it"
```

預期文字輸出應該接近：

```text
AIT run finished
Status: succeeded
Changed: 3 files
Result: ready to apply
Next: ait apply latest
```

如果使用者設定 `apply = auto`，且 AIT 判斷安全，輸出可以是：

```text
AIT run finished
Status: applied
Changed: 3 files
Branch: main
```

不需要顯示：

```text
Workspace: /repo/.ait/workspaces/attempt-0007-...
```

除非使用者加 `--debug`、`--format json`，或發生需要人工排查的狀況。

### Dirty Checkout

使用者目前有本地修改時，AIT 應該仍然可以執行：

```text
AIT run finished
Status: succeeded
Changed: 2 files
Your local edits were left untouched.
Result: ready to apply
```

如果使用者要求套用，而檔案沒有重疊：

```text
AIT applied the result without touching your existing edits.
Changed: 2 files from AIT, 1 existing local file preserved
```

如果有重疊：

```text
AIT found overlapping edits in src/auth.py.
Choose: integrate automatically, keep result for review, or discard result.
```

這裡仍不提 `worktree`，除非進入 debug mode。

## 中斷預算

AIT 應該用「中斷預算」約束互動頻率：

| 情境 | 預設中斷次數 | 行為 |
| --- | ---: | --- |
| agent run 成功，但未設定自動套用 | 0 | 回報結果與下一步 |
| agent run 成功，設定自動套用且安全 | 0 | 自動套用與清理 |
| 需要修改目前 checkout，但沒有明確 apply 意圖 | 1 | 詢問是否套用 |
| dirty checkout 無重疊且使用者已要求 apply | 0 | 自動 three-way apply |
| dirty checkout 有重疊 | 1 | 詢問高階整合策略 |
| push、PR、刪除不確定資料 | 1 | 明確確認 |
| 非互動環境遇到不安全情境 | 0 | 保守停在 recoverable 狀態 |

## 架構設計

新增一個 workspace autonomy layer。它不是替代現有 `workspace.py`，而是把現有 primitive 包成 policy-driven workflow。

建議模組：

```text
src/ait/workspace_autonomy.py
src/ait/landing.py
src/ait/recovery.py
```

### WorkspaceLease

每個 internal worktree 應有 lease metadata。可以先用 DB 欄位加 sidecar JSON，避免 DB 尚未可用時無法清理 orphan。

建議 sidecar path：

```text
.ait/workspaces/<worktree-name>.lease.json
```

建議欄位：

```json
{
  "schema_version": 1,
  "attempt_id": "repo:01...",
  "intent_id": "repo:01...",
  "repo_root": "/repo",
  "workspace_ref": "/repo/.ait/workspaces/attempt-0001-...",
  "base_ref_oid": "...",
  "base_ref_name": "main",
  "created_at": "2026-05-07T00:00:00Z",
  "last_touched_at": "2026-05-07T00:10:00Z",
  "owner_pid": 12345,
  "owner_command": "ait run",
  "state": "active",
  "cleanup_policy": "auto",
  "preserve_reason": null
}
```

狀態：

- `active`: command/daemon 仍可能在使用。
- `succeeded`: attempt 有 committed result，等待 apply 或 retention。
- `applied`: 結果已套用，可清理。
- `failed`: 失敗，保留短期供 inspect/recover。
- `conflict`: 套用遇到衝突，保留供整合。
- `orphan`: DB 缺 record 或 record 不一致，需保守處理。
- `stale`: owner 不存在且超過 retention，可候選清理。

### CheckoutSnapshot

AIT 在 run/apply 前記錄使用者 checkout 的只讀 snapshot：

```text
branch
HEAD oid
tracked dirty files
untracked files
ignored artifact summary
index state
```

用途：

- 判斷 target branch 是否移動。
- 判斷使用者 dirty files 是否與 attempt touched files 重疊。
- 產生 landing plan。
- 在 error message 中用人話說明風險。

AIT 不應該為了建立 snapshot 而 stash 或修改使用者狀態。

### LandingPlan

`ait apply` 或 `ait run --apply` 先產生 landing plan，再執行。

建議 plan 類型：

1. `fast_forward_current_branch`
   - root clean。
   - attempt base 是 current HEAD 或可 rebase 到 current HEAD。
   - 可用現有 `land_workspace_head()` 或 `merge --ff-only`。

2. `update_non_checked_out_branch`
   - target branch 不是目前 checkout。
   - 可用 `update-ref`。
   - 不修改使用者工作目錄。

3. `patch_apply_clean_overlap`
   - root dirty，但 dirty files 與 attempt touched files 無交集。
   - 使用 binary patch 從 attempt base 到 attempt head。
   - 用 `git apply --3way` 套到目前 checkout。
   - 不自動 stage 使用者既有 dirty changes。

4. `auto_rebase_then_land`
   - target branch 已前進，但 attempt workspace clean。
   - AIT 自動 rebase attempt 到 target branch，再 land。

5. `integration_attempt`
   - root dirty 且 touched files 重疊。
   - AIT 建立新的 integration attempt，以目前 checkout/HEAD 為 base，嘗試 replay previous attempt patch。
   - 成功則回到 apply path。
   - 失敗則保留 conflict 狀態。

6. `hold_for_review`
   - 非互動、衝突、unsafe、或缺少 durable result。
   - 不改使用者 checkout。
   - 回報高階原因與下一步。

## 套用策略

### 不自動 stash

AIT 不應該預設 stash 使用者修改。原因：

- stash 會改變使用者 checkout 與 index 心智模型。
- stash apply/pop 的衝突 UX 很差。
- 使用者不需要知道 AIT 存在時，也不應該突然看到 stash entry。

改用：

- 隔離 worktree 執行。
- dirty snapshot。
- touched-file overlap detection。
- patch/three-way apply。
- 必要時 integration attempt。

### Patch Apply 規則

當使用者已要求 apply，且 root dirty 但無重疊時：

1. 從 attempt workspace 產生 patch：

   ```bash
   git diff --binary <base_ref_oid>...HEAD
   ```

2. 在 root checkout 檢查：

   - patch touched paths 不在 dirty tracked set。
   - patch touched paths 不會覆蓋 untracked files。
   - submodule、rename、delete 需保守分類。

3. 執行：

   ```bash
   git apply --3way --whitespace=nowarn
   ```

4. 驗證：

   - 使用者原本 dirty files 仍存在。
   - AIT touched files 已更新。
   - 沒有 conflict marker。
   - 不自動 commit 使用者 checkout，除非 command 明確要求。

### Rebase 規則

如果 target branch 在 attempt 建立後移動：

- attempt workspace clean 時，AIT 可自動 rebase attempt onto target HEAD。
- rebase 成功後繼續 land。
- rebase 衝突時：
  - abort rebase 或保留 conflict 狀態，取決於能否安全復原。
  - 不要求使用者進入 worktree 手動修。
  - 建議下一步是「讓 AIT 幫你整合」或「保留供 review」。

## 清理策略

### 成功路徑

attempt 已成功套用且滿足以下條件時，自動清理：

- attempt result commit 已在 target ref、current checkout、或 durable patch artifact 中可追蹤。
- workspace 沒有 uncommitted tracked changes。
- local artifacts reconciliation 回報可清理。
- 沒有 active dev server 使用該 workspace。
- lease owner 不存在或已標記 completed。

清理動作：

1. stop workspace-owned dev servers。
2. cleanup worktree-local environment artifacts metadata。
3. `git worktree remove --force <workspace>`。
4. best-effort `git worktree prune`。
5. lease 標記 `applied` 或刪除 sidecar。

### 保留路徑

以下狀況保留 workspace：

- run failed。
- command interrupted。
- apply conflict。
- user requested review。
- workspace 有 uncommitted tracked changes。
- local artifacts 不允許 cleanup。
- DB/sidecar 不一致。

保留時不把 path 當主訊息，但提供 recover handle：

```text
AIT kept the result for recovery.
Recover: ait recover latest
Debug: ait recover latest --debug
```

### 自動 Prune

AIT 可以在下列入口做低成本 cleanup：

- `ait run` 開始前。
- `ait status`。
- `ait cleanup`。
- daemon startup recovery。

預設只清理明確安全的項目：

- `applied` 且超過短 TTL。
- `failed` 且超過 retention。
- sidecar 指向不存在 process 且 DB 狀態 terminal。
- orphan workspace 超過 retention 且 clean。

不自動清理：

- active lease。
- dirty workspace。
- DB 缺失但 workspace 有修改。
- 有 dev server 或長時間 command still alive。

## CLI 設計

### 日常指令

建議新增或調整：

```bash
ait apply [attempt-id|latest] [--to <branch>] [--mode auto|current|branch|none]
ait recover [attempt-id|latest] [--debug]
ait status [--debug]
```

`attempt land/promote/rebase/discard` 可以保留為低階指令，但日常文件應改推 `ait apply` 與 `ait recover`。

### `ait run` Apply Policy

建議設定：

```json
{
  "run": {
    "apply": "ask"
  }
}
```

支援值：

- `never`: 只產生 attempt result，不修改目前 checkout。
- `ask`: 成功後提示是否套用；非互動環境等同 `never`。
- `auto`: 安全時自動套用；不安全時 hold。
- `current`: 目標是目前 branch。
- `branch`: 只更新非 checked-out branch，不修改 working tree。

CLI override：

```bash
ait run --apply auto --intent "..." -- claude -p "..."
ait run --apply never --intent "..." -- claude -p "..."
```

### 輸出分層

Text mode：

- 偏產品語言。
- 隱藏 workspace path。
- 只顯示 changed files、status、branch、下一步。

JSON mode：

- 保留 `attempt_id`、`workspace_ref`、`base_ref_oid`、`landing_plan`、`cleanup_result`。
- 供 editor integration、CI、agent harness 使用。

Debug mode：

- 顯示 worktree path、lease path、Git commands、cleanup skip reason。

## Error Copy 改寫方向

現有錯誤常直接要求使用者 commit/stash 或進入 worktree。最低度干擾版本應改成高階處理語言。

例：

```text
refusing to promote ... main working tree has uncommitted tracked changes.
Commit or stash those changes first...
```

改為：

```text
AIT could not apply directly because your local edits overlap with the result.
Run `ait apply latest` to let AIT integrate them, or `ait recover latest --debug`
to inspect details.
```

原始 Git detail 可放在 debug payload。

## 安全不變量

1. AIT 不預設 stash 使用者 checkout。
2. AIT 不在 root dirty 時用 `update-ref` 移動目前 checked-out branch。
3. AIT 不刪除含 uncommitted tracked changes 的 workspace。
4. AIT 不刪除無 durable result 的成功 workspace。
5. AIT 不覆蓋 root checkout 的 untracked files。
6. AIT 不在非互動模式做需要確認的外部可見動作。
7. AIT 所有自動清理都必須可由 cleanup report 解釋。
8. JSON/API 相容性優先於 text output 簡化。

## 實作切片

### Slice 1：降低文字輸出噪音

目標：先讓日常 UX 不再把 worktree 當主要概念。

變更：

- 調整 `_format_run_result()`，text mode 隱藏 `Workspace`。
- 保留 JSON `workspace_ref`。
- 錯誤訊息加高階建議，debug 才顯示 path。
- 文件把 `attempt land/promote` 降為進階操作。

測試：

- text output 不含 `.ait/workspaces`。
- JSON output 仍含 `workspace_ref`。

### Slice 2：WorkspaceLease sidecar

目標：讓 cleanup/recovery 有穩定依據。

變更：

- create workspace 後寫 `.lease.json`。
- run start/finish 更新 lease state。
- cleanup 讀 lease，active workspace 保守 skip。
- crash 後根據 pid/mtime/DB 狀態標記 stale。

測試：

- active lease 不被 cleanup。
- terminal lease 可被 cleanup。
- sidecar 缺失時 fallback DB。

### Slice 3：`ait apply`

目標：提供不暴露 worktree 的 landing 入口。

變更：

- 新增 `landing.py` plan builder。
- 新增 `ait apply latest|<attempt-id>`。
- clean root path 使用現有 `land_attempt()`。
- non-checked-out branch path 使用現有 `promote_attempt()`。
- text output 使用 applied/held/conflict vocabulary。

測試：

- clean root fast-forward apply。
- target branch 非目前 checkout 時不改 working tree。
- already applied idempotency。

### Slice 4：Dirty Checkout Safe Apply

目標：避免要求使用者 stash。

變更：

- 新增 checkout snapshot。
- 新增 attempt touched path set。
- 無重疊時產生 binary patch 並 `git apply --3way`。
- 有重疊時 hold 或建立 integration attempt。

測試：

- dirty unrelated file preserved。
- untracked target path blocks apply。
- overlapping tracked file enters conflict/hold。
- apply failure leaves root state recoverable。

### Slice 5：自動 cleanup 與 recover

目標：讓 worktree lifecycle 成為 AIT 背景責任。

變更：

- `ait recover latest` 顯示最近 held/failed/conflict attempt。
- `ait cleanup --apply` 可刪 applied terminal workspaces。
- `ait run` 開始前 best-effort prune safe stale workspace。
- local artifact/dev server cleanup 接進 lease state。

測試：

- applied workspace cleaned。
- failed workspace retained until retention。
- recover latest resolves to most recent held attempt。
- dev server active workspace not cleaned。

## 驗收標準

這個設計完成後，應符合：

1. 使用者可以長期只使用 `ait run`、`ait apply`、`ait status`、`ait recover`。
2. 正常 text output 不出現 `.ait/workspaces`。
3. 使用者 checkout dirty 時，agent run 不要求 commit/stash。
4. 安全 apply 不要求使用者手動操作 worktree。
5. 失敗或中斷後，使用者有單一 recover 入口。
6. cleanup 不需要使用者理解 Git worktree。
7. 進階使用者仍可用 debug/API 查完整 worktree details。

## 開放問題

1. `ait run` 預設 apply policy 要用 `ask` 還是 `never`？
   - `ask` 比較產品化，但會增加一次互動。
   - `never` 最安全，但需要使用者下一步 `ait apply`。
   - 建議初期預設 `never`，提供 config opt-in `ask/auto`。

2. Dirty checkout 的 patch apply 是否應預設 stage？
   - 建議不 stage，避免混入使用者 index 狀態。
   - 若使用者明確要求 commit，AIT 才處理 staging/commit。

3. integration attempt 是否要進入 v1？
   - 可以先 hold conflict，後續再做 auto integration。
   - 但架構應預留 plan type。

4. text output 是否完全隱藏 attempt id？
   - 建議顯示短 attempt id 或 `latest` handle。
   - 完全隱藏會降低 recover/debug 可用性。

## 建議下一步

先做 Slice 1 到 Slice 3。這三步能快速降低干擾：

1. 日常輸出不再強調 worktree。
2. 新增 `ait apply` 作為使用者語意入口。
3. clean checkout 的 apply/cleanup 自動化。

Dirty checkout safe apply 與 integration attempt 可以接在後面，因為它們風險較高，需要更完整測試。
