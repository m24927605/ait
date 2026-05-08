# AIT 最低干擾高度智能 Integration Strategy 設計實作文件

狀態：設計待實作
關聯文件：
- `docs/minimal-interruption-worktree-design-zh.md`
- `docs/minimal-interruption-intelligent-automation-design-zh.md`

## 目標

AIT 的 integration strategy 要把「使用者 checkout 有 local edits，但 agent result 也想 apply」這件事，從要求使用者手動 commit/stash/進 worktree，升級成 AIT 可安全自動化的 recovery flow。

核心產品合約：

> AIT 可以很智能，但所有高風險整合都必須發生在 internal integration attempt 裡；root checkout 不被 stash、不被覆蓋、不被拿來試 merge。

成功狀態：

- 使用者不需要理解 `.ait/workspaces/...`。
- root dirty 時不要求 commit/stash。
- unrelated dirty changes 可直接 safe apply。
- tracked-file overlap 可建立 integration attempt 自動嘗試 merge。
- merge 成功後回到一般 `ait apply <integration-attempt>` path。
- merge 失敗時保留可 recover 狀態，而不是污染 root。
- 所有 decision 都有 stable reason code 與 debug metadata。

## 非目標

- 不做 root checkout 上的自動 stash。
- 不在 root checkout 上試 conflict merge。
- 不覆蓋 root untracked files。
- 不把 AI semantic merge 的結果直接寫回 root。
- 不保證所有 conflict 都能自動解；不安全時 hold。

## 安全不變量

1. 不自動 stash。
2. 不修改 root checkout 來嘗試 integration。
3. 不覆蓋 root untracked files。
4. 不在 root dirty 時用 `update-ref` 移動目前 checked-out branch。
5. 不刪除含 uncommitted tracked changes 的 workspace。
6. 不刪除沒有 durable result artifact 的 integration workspace。
7. 非互動模式遇到 unsafe 情境時 hold，不詢問也不冒進。
8. binary/delete/rename overlap 預設 hold，除非 policy 明確允許。
9. AI semantic merge 只能在 integration workspace 內執行。
10. cleanup/apply/recover/status 必須能解釋每個 decision。

## 新增模組

新增：

```text
src/ait/integration.py
```

主要責任：

- 建立 dirty snapshot。
- 建立 integration plan。
- 建立 integration attempt workspace。
- replay 使用者 dirty tracked changes。
- replay agent result。
- 執行多階段 merge strategy。
- 產生 durable artifacts。
- 更新 lease / decision report。

不要把 integration logic 塞進 `recovery.py`。`recovery.py` 只負責 CLI action orchestration。

## 資料模型

### DirtySnapshot

```python
@dataclass(frozen=True, slots=True)
class DirtySnapshot:
    branch: str | None
    head_oid: str
    tracked: tuple[DirtyPath, ...]
    untracked: tuple[UntrackedPath, ...]
    index_dirty: bool
    created_at: str
```

### DirtyPath

```python
@dataclass(frozen=True, slots=True)
class DirtyPath:
    path: str
    status: str
    mode: str | None
    blob_oid: str | None
    worktree_sha256: str | None
    binary: bool
```

### IntegrationPlan

```python
@dataclass(frozen=True, slots=True)
class IntegrationPlan:
    attempt_id: str
    base_attempt_id: str
    strategy: str
    classification: str
    root_modified: bool
    safe_to_auto_run: bool
    user_paths: tuple[str, ...]
    agent_paths: tuple[str, ...]
    overlap_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    reason_code: str
    reason: str
```

### IntegrationResult

```python
@dataclass(frozen=True, slots=True)
class IntegrationResult:
    attempt_id: str
    base_attempt_id: str
    status: str
    plan: IntegrationPlan
    changed_files: tuple[str, ...]
    commit_oid: str | None
    workspace_ref: str | None
    result_artifact_ref: str | None
    patch_artifact_ref: str | None
    decision_report: DecisionReport
    debug: dict[str, object]
```

## Dirty Snapshot

Snapshot 來源：

```bash
git status --porcelain=v1 -z
git diff --name-only
git diff --cached --name-only
git ls-files --others --exclude-standard
git ls-files -s -- <path>
```

規則：

- tracked dirty 可以 replay 到 integration workspace。
- untracked 預設不 replay，因為 ownership 不明。
- 如果 agent result 會 create/modify 與 root untracked 相同 path，必須 hold。
- index dirty 必須記錄；v1 可以把 staged + unstaged 都視為 tracked dirty snapshot。
- snapshot 不可透過 stash 建立。

## Path Classification

AIT 必須建立 overlap matrix：

```text
safe_non_overlap
  user touched A, agent touched B

text_overlap
  user touched A, agent touched A, both text

binary_overlap
  user touched A, agent touched A, at least one binary

delete_overlap
  one side deletes, other side edits

rename_overlap
  one side renames, other side edits/renames

untracked_conflict
  root untracked path conflicts with agent result path

unsafe_status
  submodule, mode-only, unresolved, unsupported status
```

Reason codes：

```text
integration.safe_non_overlap
integration.text_overlap
integration.binary_overlap
integration.delete_overlap
integration.rename_overlap
integration.untracked_conflict
integration.unsafe_status
integration.no_agent_patch
integration.replay_user_failed
integration.replay_agent_failed
integration.merge_file_conflict
integration.semantic_merge_failed
integration.created
integration.succeeded
integration.held
```

## Integration Attempt Flow

入口：

```bash
ait recover latest --create-integration
ait recover latest --auto-integrate
ait recover latest --auto-integrate --test "pytest ..."
```

流程：

```text
1. resolve base attempt
2. verify base attempt has durable result or workspace
3. snapshot root checkout
4. classify user dirty paths vs agent touched paths
5. unsafe classification -> hold with DecisionReport
6. create integration intent + attempt
7. replay tracked dirty snapshot into integration workspace
8. replay agent result into integration workspace
9. run merge strategy
10. if successful: commit integration result
11. write .ait/results/<integration-attempt>.patch/json
12. mark lease state succeeded/conflict/held
13. return next step: ait apply <integration-attempt>
```

Root checkout must be unchanged after every step.

## Replay 使用者 Dirty Changes

V1 支援 tracked files：

- modified file：copy root working file into integration workspace。
- deleted file：delete same path in integration workspace。
- staged-only change：讀 index blob，寫入 integration workspace。
- mixed staged + unstaged：v1 可以以 working tree final content 為準，debug metadata 必須標記 `index_semantics_collapsed=true`。

V1 不自動 replay untracked files。

如果 policy 未來允許 replay untracked，也必須：

- 只 replay 到 integration workspace。
- 不覆蓋 integration workspace 中 agent/base 已存在 path。
- DecisionReport 明確列出 replayed untracked paths。

## Agent Result Replay

Agent result patch 優先來源：

1. `.ait/results/<attempt-id>.patch`
2. attempt workspace `git diff --binary <base_ref_oid>..HEAD`
3. attempt commits from DB

若無 patch：

- status = `held`
- reason_code = `integration.no_agent_patch`

## Merge Strategy Ladder

### Strategy 0：safe non-overlap apply

條件：

- no overlap
- no untracked conflict
- no unsafe status

動作：

```bash
git apply --3way --whitespace=nowarn <agent.patch>
```

成功後 commit。

### Strategy 1：git apply --3way

條件：

- text overlap allowed
- patch status only A/M

動作：

```bash
git apply --3way --check --whitespace=nowarn
git apply --3way --whitespace=nowarn
```

如果產生 conflict 或 conflict markers，進入 Strategy 2 或 hold。

### Strategy 2：file-level three-way merge

針對每個 `text_overlap` path：

```text
base   = file at root HEAD / base_ref_oid
ours   = root dirty snapshot content
theirs = agent result file content
```

可用：

```bash
git merge-file -p ours base theirs
```

成功條件：

- exit code 0
- no conflict markers
- output is valid text

失敗：

- lease state = conflict
- reason_code = `integration.merge_file_conflict`
- preserve integration workspace

### Strategy 3：hunk-level non-overlap merge

如果同檔 overlap 但 hunks 不重疊，可以自動合併。

V1 可延後；若實作，必須使用 parser 或 Git diff hunk metadata，不要 ad hoc substring merge。

### Strategy 4：semantic AI merge

入口：

```bash
ait recover latest --auto-integrate
```

條件：

- repo policy 允許。
- 只處理 text files。
- no binary/delete/rename overlap。
- integration workspace 已建立。
- root checkout 不會被修改。

動作：

1. 寫 conflict bundle：

```text
.ait/integration/<attempt-id>/conflicts.json
.ait/integration/<attempt-id>/files/<path>.base
.ait/integration/<attempt-id>/files/<path>.user
.ait/integration/<attempt-id>/files/<path>.agent
```

2. 啟動 adapter 在 integration workspace 內修復。
3. 執行 configured validation。
4. 成功後 commit。
5. 回傳 `ait apply <integration-attempt>`。

AI merge 絕不可直接改 root checkout。

### Strategy 5：hold

任何 unsafe case：

- status = `held` 或 `conflict`
- workspace retained
- DecisionReport 包含 blocked paths
- next steps 不要求使用者進 worktree

建議 next steps：

```text
ait recover latest --debug
ait recover latest --auto-integrate
ait apply <integration-attempt>
```

## CLI 設計

### recover

新增/強化：

```bash
ait recover [latest|attempt-id] --create-integration
ait recover [latest|attempt-id] --auto-integrate
ait recover [latest|attempt-id] --auto-integrate --test "pytest ..."
ait recover [latest|attempt-id] --format json
ait recover [latest|attempt-id] --debug
```

Text output normal：

```text
AIT created an integration attempt.
Status: integration_created
Changed: 3 files
Next:
- ait apply latest
```

Debug output 可以顯示：

- base attempt id
- integration attempt id
- workspace_ref
- lease path
- strategy
- classification
- blocked paths
- exact git commands

### apply

`ait apply` 不需要知道 attempt 是普通 attempt 或 integration attempt。

成功 integration result 必須走相同 LandingPlan：

```bash
ait apply <integration-attempt>
```

## Config Policy

新增/補齊：

```json
{
  "apply": {
    "dirty_strategy": "safe-patch",
    "integration_attempt": "manual",
    "semantic_integration": "off",
    "cleanup_after_apply": true
  },
  "integration": {
    "allow_untracked_replay": false,
    "allow_binary_merge": false,
    "allow_delete_merge": false,
    "auto_test_command": null,
    "semantic_adapter": null
  }
}
```

Policy semantics：

- `integration_attempt=manual`：overlap 時 hold，提示 `--create-integration`。
- `integration_attempt=auto`：safe text overlap 可自動建立 integration attempt。
- `semantic_integration=off`：不啟動 AI merge。
- `semantic_integration=manual`：只有 `--auto-integrate` 才啟動。
- `semantic_integration=auto`：只在 safe text conflict 且 validation configured 時可自動啟動。

## Durable Artifacts

每個 integration attempt 成功後寫：

```text
.ait/results/<attempt-id>.patch
.ait/results/<attempt-id>.json
```

JSON payload：

```json
{
  "schema_version": 1,
  "attempt_id": "...",
  "base_attempt_id": "...",
  "kind": "integration",
  "strategy": "merge-file",
  "classification": "text_overlap",
  "root_modified": false,
  "commit_oid": "...",
  "changed_files": ["src/a.py"],
  "decision_report": {}
}
```

cleanup 只有在以下皆成立才可刪 integration workspace：

- lease terminal。
- result artifact exists。
- workspace clean。
- no dev server active。
- no preserve_reason。

## Decision Report

所有 integration result 必須包含：

```json
{
  "schema_version": 1,
  "subject": "integration",
  "subject_id": "<integration-attempt-id>",
  "decision": "integration_created",
  "safety_level": "recoverable",
  "reasons": [
    {
      "code": "integration.text_overlap",
      "message": "AIT created an integration attempt for overlapping tracked edits."
    }
  ],
  "next_steps": [
    {
      "command": "ait apply <integration-attempt>",
      "description": "apply the integrated result"
    }
  ],
  "metadata": {
    "base_attempt_id": "...",
    "strategy": "merge-file",
    "root_modified": false,
    "overlap_paths": ["src/a.py"],
    "blocked_paths": []
  }
}
```

## Status Dashboard

`ait status --debug` 應顯示 integration state：

```text
Latest result: integration_created
Next: ait apply latest

Recovery debug:
  Base attempt: ...
  Integration attempt: ...
  Strategy: merge-file
  Classification: text_overlap
  Workspace: ...
  Reason code: integration.text_overlap
```

Normal `ait status` 不顯示 workspace path。

## 測試矩陣

新增 `tests/test_integration.py`。

### Snapshot

- clean root -> no dirty paths。
- tracked modified -> snapshot path/hash/status。
- tracked deleted -> snapshot delete。
- staged-only -> snapshot index dirty。
- untracked -> listed but not replayed by default。

### Classification

- user A / agent B -> `safe_non_overlap`。
- same text file -> `text_overlap`。
- same binary file -> `binary_overlap` hold。
- agent creates path matching root untracked -> `untracked_conflict` hold。
- delete/edit -> `delete_overlap` hold。
- rename/edit -> `rename_overlap` hold。

### Integration

- safe non-overlap creates integration attempt and commit。
- text overlap with non-conflicting hunks auto merges。
- text overlap with conflict preserves integration workspace。
- untracked conflict does not modify root。
- binary overlap holds。
- root checkout content unchanged after every integration attempt。
- integration success can be `ait apply`-ed。
- integration success writes `.ait/results/*.patch/json`。
- cleanup removes integration workspace only after durable artifact exists。
- dev server active retains integration workspace。

### CLI/Text

- `ait recover latest --create-integration` normal text does not show `.ait/workspaces`。
- `--debug` shows workspace and strategy。
- JSON includes `workspace_ref` and `decision_report`。
- daily errors never say `Commit or stash`。

## 實作順序

### Slice 1：Integration module skeleton

- 新增 `src/ait/integration.py`。
- 新增 dataclasses。
- 實作 dirty snapshot。
- 實作 path classification。
- 補 snapshot/classification tests。

### Slice 2：Create integration attempt

- 從 `recovery.py` 搬出現有 `create_integration_attempt()`。
- replay tracked dirty files。
- replay agent patch。
- 不支援的情境 hold。
- 補 root unchanged tests。

### Slice 3：Merge strategy ladder v1

- Strategy 0 safe non-overlap。
- Strategy 1 `git apply --3way`。
- Strategy 2 text file `git merge-file`。
- conflict markers detection。
- lease state succeeded/conflict。

### Slice 4：Durable artifacts + cleanup

- 寫 `.ait/results/<attempt-id>.patch/json`。
- cleanup 只刪 terminal + durable + clean + no dev server。
- status dashboard 顯示 integration decision。

### Slice 5：Semantic AI merge

- conflict bundle。
- adapter invocation in integration workspace。
- validation command。
- policy gate。
- 成功後 commit，失敗 hold。

## 驗收條件

1. `ait recover latest --create-integration` 不修改 root checkout。
2. root dirty tracked overlap 可建立 integration attempt。
3. simple text overlap 可自動 merge。
4. binary/untracked/delete/rename overlap 會 hold。
5. 成功 integration 可透過 `ait apply` apply。
6. normal text 不顯示 `.ait/workspaces`。
7. debug/json 保留 low-level details。
8. 所有 decision 有 stable reason code。
9. cleanup 不刪 unsafe integration workspace。
10. 全量測試通過。
