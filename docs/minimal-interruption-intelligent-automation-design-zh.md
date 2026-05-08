# AIT 最低干擾高度智能自動化設計

狀態：Draft
日期：2026-05-07
關聯文件：`docs/minimal-interruption-worktree-design-zh.md`

## 目標狀態

AIT 的目標不是「幫使用者管理 worktree」，而是讓使用者幾乎不需要知道
worktree 存在。理想產品合約是：

```text
使用者負責表達意圖、審核可見結果、批准外部副作用。
AIT 負責隔離執行、狀態判斷、套用策略、衝突處理、清理、復原與解釋。
```

高度智能自動化的判準不是「盡可能自動做事」，而是：

- 能安全自動化的，不中斷使用者。
- 不能安全自動化的，保守 hold，且說清楚原因與下一步。
- 不把 Git/worktree 低階細節丟給日常使用者。
- 所有自動決策都能用 debug/report 解釋。
- JSON/API 相容性優先於 text UX 簡化。

## 日常 UX

日常命令應收斂為：

```bash
ait run --intent "fix checkout timeout" -- claude -p "fix it"
ait apply latest
ait recover latest
ait cleanup
```

進階命令保留，但不作為日常引導：

```bash
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to <branch>
ait attempt rebase <attempt-id> --onto <branch>
ait attempt discard <attempt-id>
```

### Happy Path

```text
AIT run finished
Status: succeeded
Changed: 3 files
Result: ready to apply
Next: ait apply latest
```

若使用者設定 `run.apply = auto` 或 CLI 指定 `--apply auto`，且安全：

```text
AIT run finished
Status: applied
Changed: 3 files
Branch: main
Cleanup: internal workspace removed
```

### Dirty Checkout

Run 不要求使用者 commit/stash：

```text
AIT run finished
Status: succeeded
Changed: 2 files
Your local edits were left untouched.
Result: ready to apply
Next: ait apply latest
```

Apply 無重疊時：

```text
AIT applied the result without touching your existing edits.
Changed: 2 files
Cleanup: kept for recovery because your checkout has local edits
```

Apply 有重疊時：

```text
AIT could not apply directly because your local edits overlap with the result.
Changed: 2 files
Reason: overlapping local edits: src/auth.py
Recover: ait recover latest
```

## 已完成基線

目前已完成的最低干擾主幹：

- text run output 不再顯示 `.ait/workspaces/...`。
- JSON/API 保留 `workspace_ref`。
- 新增 `ait apply [latest|attempt-id]`。
- 新增 `ait recover [latest|attempt-id]`。
- 新增 `ait run --apply never|auto|current|branch`。
- repo config 支援讀取 `run.apply`。
- 新增 workspace lease sidecar。
- workspace create/run finish/apply/cleanup 會更新 lease state。
- cleanup 會讀 lease，保守處理 active/conflict/orphan/preserved。
- clean current checkout 可 fast-forward apply。
- non-current branch 可 update target branch，不碰 root checkout。
- dirty checkout 無 tracked/untracked 重疊時可 patch apply。
- dirty overlap、untracked overwrite、unsafe patch 會 hold/recover。
- 成功 apply 且有 durable branch/ref 時可清理 internal workspace。
- 新增 `DecisionReport` 統一模型，reason 包含 stable code、paths、debug metadata。
- apply/recover/status/integration/cleanup JSON/debug 均已接入 decision report。
- 新增集中式 reason code registry：`src/ait/decision_codes.py`。
- `ait status --debug` 會顯示 latest attempt、workspace、lease、reason code、apply readiness、next step。
- `ait status --all` 保留 agent readiness，並加入 repo-level recovery summary；normal text 不顯示 internal workspace。
- `ait recover --retry-apply`、`--create-integration`、`--auto-integrate`、`--discard` 已成為可執行 recovery 入口。
- dirty tracked overlap 可建立 integration attempt；成功結果可 apply，conflict 會保留 workspace 與 decision report。
- dirty checkout patch apply 會寫 durable patch/result artifact，成功後可安全清理 internal workspace。
- run startup 會執行 safe prune，低噪音清理已確定安全的 terminal workspace。
- active dev server workspace 會被 cleanup retain，reason=`active-dev-server`，debug/json 顯示 pid/port/log。
- 新增 `ait config show` 顯示 effective policy 與 invalid config warnings。
- 日常 text smoke tests 覆蓋 run/apply/recover/status/status --all/cleanup 不顯示 internal workspace path。
- dogfood matrix 的主要 workflow 已由 landing/cleanup/integration/cli_run/dev_server 測試覆蓋。
- README、getting-started、command reference、CLI help 已轉向 `run/apply/recover`。

## 剩餘缺口 / Future Work

核心低干擾自動化路徑已完成。剩餘項目目前屬於 hardening / future work，
不阻擋將 AIT 視為達到「最低干擾且高度智能自動化」的產品狀態。

### 已完成：Decision Report 統一模型

已新增：

```text
src/ait/decision_report.py
src/ait/decision_codes.py
```

核心資料已落地：

```json
{
  "schema_version": 1,
  "subject": "attempt|workspace|checkout|cleanup",
  "subject_id": "...",
  "decision": "apply|hold|cleanup|retain|recover|skip",
  "safety_level": "safe|caution|unsafe|unknown",
  "reasons": [
    {
      "code": "dirty-overlap",
      "message": "Your local edits overlap with the result.",
      "paths": ["src/auth.py"],
      "debug": {}
    }
  ],
  "next_steps": [
    {"command": "ait recover latest", "kind": "daily"},
    {"command": "ait recover latest --debug", "kind": "debug"}
  ]
}
```

已接入：

- `ait apply`
- `ait recover`
- `ait cleanup`
- `ait status --debug`
- `ait status --all`
- integration attempt

已完成驗收：

- 所有 hold/skip/retain/remove decision 都有 stable reason code。
- text 顯示人話。
- JSON/debug 顯示完整 reason code、paths、workspace/lease metadata。
- 測試覆蓋每個 reason code。

### 已完成：`ait status --debug` / `status --all` Recovery Dashboard

`ait status` 已能低噪音呈現日常狀態，`--debug` 顯示完整 lifecycle。
`ait status --all` 保留 adapter readiness，並加入 repo-level recovery summary。

Text mode：

```text
AIT Status
Latest result: ready to apply
Changed: 3 files
Next: ait apply latest
```

Debug mode：

```text
AIT Status
Latest result: held
Reason: dirty-overlap
Attempt: ...
Lease: ...
Workspace: ...
Cleanup: retained because local edits overlap
```

已完成：

- `status --debug` parser option。
- status payload include latest attempt, lease, cleanup decision, apply readiness。
- 不在 normal text 顯示 `.ait/workspaces`。

驗收：

- latest succeeded attempt 顯示 `ready to apply`。
- latest conflict/failed 顯示 `recoverable`。
- debug 顯示 lease path/workspace path/reason codes。

### 已完成：Recovery Engine 從「提示」升級為「可執行修復」

`ait recover` 已能執行安全修復入口。

新增模式：

```bash
ait recover latest
ait recover latest --debug
ait recover latest --retry-apply
ait recover latest --create-integration
ait recover latest --discard
```

已完成行為：

- `--retry-apply`：重新產生 LandingPlan，再跑 apply。
- `--create-integration`：針對 dirty overlap 建 integration attempt。
- `--auto-integrate`：在 policy 允許的範圍內建立並執行 integration attempt。
- `--discard`：只有在無未保存結果或使用者明確要求時 discard。

驗收：

- failed/conflict/held attempt 可被 `recover latest` 找到。
- `--retry-apply` 成功時套用並更新 lease。
- `--create-integration` 成功時產生新的 integration attempt。
- 非互動模式不做 destructive 動作。

### 已完成：Integration Attempt

Dirty checkout 有重疊時，AIT 應提供「讓 AIT 幫你整合」而不是只 hold。

設計：

1. Snapshot root checkout。
2. 建立 integration attempt，以 current HEAD/root dirty snapshot 為 context。
3. 產生原 attempt patch。
4. 在 integration attempt 中 replay patch。
5. 若成功，回到 normal apply path。
6. 若失敗，保留 conflict attempt，提供 debug/recover。

限制：

- 不修改 root checkout。
- 不 stash。
- 不覆蓋 root untracked files。
- 不自動 resolve semantic conflict。

驗收：

- tracked overlap 可建立 integration attempt。
- replay 成功後可 apply。
- replay conflict 後 root checkout 不變。
- recover 顯示 parent attempt 與 integration attempt 關係。

### 已完成：Run Startup Safe Prune

AIT 可在低成本入口自動清理已確定安全的狀態：

- `ait run` 開始前。
- `ait status`。
- daemon startup。
- `ait cleanup`。

只自動清理：

- `applied` 且有 durable result。
- workspace clean。
- 無 active dev server。
- lease owner 不存在或 terminal。
- local artifact reconciliation cleanup_allowed。

不自動清理：

- active lease。
- conflict/failed inside retention。
- dirty workspace。
- orphan unknown。
- 有 dev server。

驗收：

- run startup 不輸出噪音。
- debug/report 可看到 prune decision。
- dirty/orphan/dev-server workspace 被 retain 並有 reason。

### 已完成：Dev Server Lease Awareness

cleanup/status/recover debug 已能引用 dev server records。

已完成：

- dev server records 寫入 workspace lease 或被 lease report 引用。
- cleanup evaluate 時若 workspace 有 active dev server，action=`retain`，reason=`active-dev-server`。
- recover/debug 顯示 dev server pid/port/log。

驗收：

- active dev server workspace 不被 cleanup。
- stopped server record 可 prune。
- debug report 顯示 pid/port。

### 已完成：Durable Result Artifact

Dirty checkout patch apply 會保存 durable patch artifact：

```text
.ait/results/<attempt-id>.patch
.ait/results/<attempt-id>.json
```

用途：

- dirty checkout apply 成功後，如果 patch artifact 已保存，可安全 cleanup workspace。
- recover 即使 workspace 被清理，也能指出 result 已 applied 或可重放。

已完成驗收：

- artifact 包含 base oid、head oid、patch sha、changed paths。
- cleanup 可因 durable patch artifact 移除 clean applied workspace。
- JSON/API 顯示 artifact ref。

### 已完成：Config Policy 完整化

已新增 minimal effective policy helper 與 `ait config show`。

支援 config：

```json
{
  "run": {
    "apply": "never",
    "auto_prune": true
  },
  "apply": {
    "dirty_strategy": "safe-patch",
    "integration_attempt": "ask",
    "cleanup_after_apply": "auto"
  },
  "recover": {
    "default_selector": "latest"
  }
}
```

支援值：

- `run.apply`: `never|ask|auto|current|branch`
- `apply.dirty_strategy`: `hold|safe-patch|integration`
- `apply.integration_attempt`: `never|ask|auto`
- `apply.cleanup_after_apply`: `never|auto`

已完成驗收：

- invalid config 顯示 warning 並 fallback safe default。
- `ait config show` 可顯示 effective policy。
- tests 覆蓋 CLI override > repo config > default。

### Future Work：Text/Error Copy 持續盤點

日常 smoke tests 已覆蓋主要命令。後續新增 CLI 時仍需避免 normal text 出現：

- `Commit or stash`
- `go into worktree`
- `.ait/workspaces/...`
- `git worktree remove`

日常替代表達：

- `AIT kept the result for recovery.`
- `Your local edits were left untouched.`
- `Run ait recover latest --debug for details.`
- `AIT could not apply safely because ...`

保留於：

- JSON。
- `--debug`。
- advanced `attempt` commands。
- historical docs/spec。

已完成基線：

- CLI text smoke tests assert no `.ait/workspaces` for daily commands。
- dirty errors 不要求 stash。
- debug text 可顯示 workspace path。

### Future Work：End-to-End Dogfood Matrix 擴充

主要 matrix 已由現有 unittest 覆蓋；可再擴充手動或自動 smoke script：

```text
clean run -> apply latest -> workspace cleaned
run --apply auto clean -> applied
dirty unrelated -> apply patch -> root edits preserved
dirty overlap -> hold -> recover latest
untracked target -> hold -> recover latest
non-current branch -> update branch, root untouched
target advanced -> auto rebase -> apply
target advanced conflict -> hold/recover
failed run -> recover latest
dev server active -> cleanup retain
orphan clean -> cleanup policy explain
orphan dirty -> cleanup retain
```

驗收：

- 每個 case 有 CLI test 或 smoke script。
- 每個 case 有 expected text output。
- 每個 unsafe case 驗證 root checkout 未被破壞。

## 分階段實作計畫

### Phase A：可解釋性補齊

目標：所有 hold/cleanup/recover decision 都有統一 report。

工作：

- 新增 `decision_report.py`。
- apply/recover/cleanup 產生 reason codes。
- `ait status --debug` 顯示 latest decision。
- 測試 reason code matrix。

完成標準：

- 任一保守 hold 都能回答「為什麼」「保留在哪」「下一步是什麼」。

### Phase B：Recovery 從查詢變修復

目標：`ait recover` 能重試 apply、建立 integration attempt、解釋失敗。

工作：

- `recover --retry-apply`。
- `recover --create-integration`。
- parent/integration attempt relation。
- conflict artifact/report。

完成標準：

- dirty overlap 不再只是 dead-end hold。
- 使用者不用進 worktree 手動修。

### Phase C：自動清理與 durable artifact

目標：成功結果不留下不必要 internal workspace，但不犧牲安全。

工作：

- durable patch/result artifact。
- dirty apply 後可安全 cleanup。
- run/status startup safe prune。
- dev server lease/report integration。

完成標準：

- Happy path 幾乎不累積 workspaces。
- 所有 retained workspace 都有明確 reason。

### Phase D：文件與產品語言全面收斂

目標：公開文件、help、error copy 都不再把 worktree 當日常概念。

工作：

- README/site-docs/command reference 全面更新。
- historical/spec docs 保留但標示 historical/advanced。
- `ait help`/subcommand help 補齊日常用語。

完成標準：

- 新使用者只需知道 `run/apply/recover/status/cleanup`。
- advanced users 仍能找到 `attempt` low-level commands。

## 安全不變量

1. 不自動 stash。
2. 不在 root dirty 時用 `update-ref` 移動目前 checked-out branch。
3. 不刪除含 uncommitted tracked changes 的 workspace。
4. 不刪除沒有 durable result 的成功 workspace。
5. 不覆蓋 root checkout 的 untracked files。
6. 非互動模式遇到 unsafe 情境時 hold，不詢問也不冒進。
7. 有 active dev server 時 retain。
8. orphan/DB 不一致時保守 retain，除非 policy 明確且 clean。
9. 所有 cleanup/apply/recover decision 都能被 report/debug 解釋。
10. JSON/API 相容性優先於 text output 簡化。

## 最終驗收標準

AIT 可被視為達到「最低干擾高度智能自動化」時，必須同時符合：

- 使用者日常只需 `ait run`、`ait apply`、`ait recover`、`ait status`、`ait cleanup`。
- 正常 text output 不出現 `.ait/workspaces`。
- dirty checkout 可正常 run。
- dirty unrelated apply 自動完成且不 stash。
- dirty overlap 能建立 integration attempt 或清楚 hold/recover。
- clean success 可自動 apply/cleanup。
- failed/interrupted/conflict 都能 `recover latest`。
- cleanup 不需要使用者理解 worktree。
- debug/report 可完整解釋 lease、workspace、cleanup、apply decision。
- 進階 Git 操作仍可透過 `ait attempt ...` 使用。
- 全量相關測試與 dogfood matrix 通過。
