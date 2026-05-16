# AIT Multi-Agent Session UX 優化實作計畫

Status: P0 implementation plan
Date: 2026-05-16
Scope: `ait session run --mode role`, session handoff context, reviewer
invocation, `ait run` command routing, and docs/site truthfulness.

## 背景

AIT 的產品主軸已經明確：不同 AI coding agents 應該能共享 repo-local
memory、長期記憶、互相溝通，並用另一個 agent 做對抗式審查。但目前實際
dogfood 暴露出一個 P0 體驗缺口：

- 使用者用 `ait session start` 建立 `claude-code + codex` session 後，
  `ait session run --mode role` 產生的是 placeholder 內容，例如
  `implemented by claude-code for package-1`，不是真正呼叫 Claude Code 或
  Codex。
- 使用者改用 `ait run --adapter claude-code -- claude -p ...` 嘗試直跑時，
  因為沒有 `--intent`，AIT 進入 dev server 啟動路徑，並被 unrelated project
  佔用的 default dev ports 擋住。
- 使用者最後只能使用 `AIT_WRAPPER_BYPASS=1 .ait/bin/claude` 與
  `AIT_WRAPPER_BYPASS=1 .ait/bin/codex exec`，繞開 AIT wrapper / worktree
  orchestration，並手動要求每個 agent 讀取上一輪檔案。
- 這代表目前體驗沒有達到「AIT 協調 agents 共同記憶、互相溝通、對抗式審查」
  的產品承諾。

這不是文件小瑕疵，而是核心使用路徑的可信度問題。只要 role mode 仍是
placeholder，AIT 就不能把「Claude implement、Codex review」描述成已完成的
session role invocation。

## 目前程式碼事實

以下是目前 tree 內可觀察到的事實，後續實作必須以這些為準：

- `src/ait/session_room.py::run_role()` 會建立 implementer / reviewer
  response，並把 turn 標成 `mode = "role"`。
- `src/ait/session_room.py::_run_implementer()` 目前用
  `python -c path.write_text('implemented by ...')` 產生 isolated attempt。
  它有 attempt/worktree/provenance，但沒有真實外部 agent invocation。
- `src/ait/session_room.py::_run_reviewer()` 目前使用 deterministic review
  substrate，不會依 `--reviewer codex` 或 `--reviewer claude-code` 呼叫對應
  reviewer adapter。
- `src/ait/session_room.py::_invoke_real_panel_agent()` 已經有 panel/council
  真實 adapter invocation 路徑，會使用 session start 時記錄的 permission
  policy。
- `src/ait/cli/run.py` 在 `args.intent` 缺失時會呼叫 `start_dev_server()`；
  因此 `ait run --adapter claude-code -- claude -p ...` 會被解讀為 dev server
  path，而不是 agent attempt path。
- `src/ait/dev_server.py` 的 default port guard 會檢查 `8003, 8004, 8010,
  8030`，這適合 dev-server workflow，但不應該阻擋 agent invocation。

## 產品目標

使用者應該可以用一條清楚命令讓 AIT 真的協調不同 agents：

```bash
ait session start "Implement and review package split" \
  --agents claude-code,codex \
  --claude-permission-mode plan \
  --codex-sandbox read-only \
  --codex-approval never

ait session run latest --mode role \
  --implementer claude-code \
  --reviewer codex
```

期望行為：

- AIT 自動產生 per-role `AIT_CONTEXT_FILE`，包含 user turn、prior session
  responses、accepted decisions、policy-allowed live memory、attempt/review refs。
- Implementer 真的呼叫 consented local adapter，例如 Claude Code 或 Codex CLI。
- Implementer 的任何 repo mutation 都在 isolated attempt workspace 內完成，
  root checkout 不被改動。
- Reviewer 真的透過 reviewer adapter 對 implementer attempt 做對抗式審查，
  不可直接寫 implementer workspace。
- Response、attempt、review、stdout/stderr、command、context manifest 都有
  attributed artifacts。
- Accepted memory / long-term memory promotion 必須透過 explicit decision
  gate，不因多 agent 共識自動提升。
- 使用者不需要 `AIT_WRAPPER_BYPASS=1`，也不需要手動要求 agents 讀取前面所有
  檔案。

## P0 工作項

### 1. 真實 Role Mode Implementer Invocation

目標：`ait session run --mode role --implementer claude-code` 必須真的呼叫
Claude Code，而不是 shell placeholder。

實作方向：

- 在 `SessionStore.run_role()` 下方拆出明確 role runner，例如
  `SessionRoleRunner` 或私有 helper。
- `_run_implementer()` 不再產生 placeholder Python script。它應該把
  assignment/package/scope/user turn/context manifest 組成 implementer brief，
  再呼叫既有 `run_agent_command()`。
- `run_agent_command()` 的 `command` 必須來自 agent adapter resolution，而不是
  test fixture script：
  - `claude-code`: `claude -p --permission-mode <session policy>`
  - `codex`: `codex exec --sandbox <session policy> -`
  - custom/local command participant: 使用 explicit `--agent-command`
  - fake agent: 保留 deterministic test path
- Role implementer 必須把 `AIT_CONTEXT_FILE` 傳入 child process。
- Response artifact 必須記錄：
  - `command_ref`
  - `context_manifest_ref`
  - `stdout_ref`
  - `stderr_ref`
  - `attempt_id`
  - `workspace_ref`
  - `changed_files`
  - `exit_code`
  - `permission_policy_ref`

Acceptance tests：

- `test_role_mode_invokes_real_implementer_adapter`
- `test_role_mode_records_command_and_context_manifest`
- `test_role_mode_implementer_writes_only_isolated_attempt_workspace`
- `test_role_mode_fake_agent_path_remains_deterministic`

### 2. 真實 Reviewer / 對抗式審查 Invocation

目標：`--reviewer codex` 或 `--reviewer claude-code` 必須真的跑 reviewer
adapter，不只是 deterministic review。

實作方向：

- `_run_reviewer()` 應支援 reviewer adapter execution：
  - default deterministic review 可保留給 `--reviewer deterministic` 或 tests。
  - `claude-code` / `codex` 應走既有 adversarial review substrate。
  - reviewer brief 必須包含 target attempt id、changed files、diff summary、
    verification evidence、accepted memory baseline、policy constraints。
- Reviewer process 不應寫 implementer workspace；如果需要 sandbox，應使用
  read-only target evidence 或 reviewer-local temp workspace。
- Review result 必須維持 AIT review contract，包含 `review_id`、findings、
  risk level、artifact refs、blocking status。

Acceptance tests：

- `test_role_mode_reviewer_invokes_requested_adapter`
- `test_role_mode_reviewer_cannot_mutate_implementer_workspace`
- `test_role_mode_adversarial_review_links_to_attempt`
- `test_role_mode_review_failure_fails_closed`

### 3. Session Handoff Context Automation

目標：agent 之間的溝通應由 AIT 的 context artifact 自動承接，不能靠使用者
手動說「先讀前面所有檔案」。

實作方向：

- 擴充 `_write_context()`，把 role mode 所需 context 分層輸出：
  - trusted baseline: accepted decisions、allowed live memory、review-gated facts
  - advisory responses: prior agent replies, clearly attributed
  - attempt evidence: linked attempt ids, changed files, verification status
  - review evidence: linked review ids, findings, risk level
  - current assignment: package name, scope paths, role, success criteria
- Context manifest 必須保留 trust classes，不可把 advisory response 當成 fact。
- 加入 explicit memory promotion gate：只有
  `ait session decision --accept ... --promote-memory` 可升級長期記憶。

Acceptance tests：

- `test_session_role_context_includes_prior_response_refs`
- `test_session_role_context_marks_advisory_vs_accepted_memory`
- `test_session_role_context_includes_assignment_scope`
- `test_session_decision_is_required_for_memory_promotion`

### 4. 修正 `ait run` 與 Dev Port Preflight 的路由

目標：agent invocation 不應被 dev server port guard 擋住。

目前問題是 `ait run` 在沒有 `--intent` 時預設進入 dev server path。這讓
`ait run --adapter claude-code -- claude -p ...` 被誤判為 dev server 啟動。

實作方向：

- 明確區分 agent run 與 dev server run：
  - `ait dev run ...` 是 dev server path。
  - `ait run --adapter <agent> -- <command>` 是 agent attempt path。
  - `ait run --agent <agent> -- <command>` 是 agent attempt path。
  - `ait run -- <known-agent-command>` 可以推斷為 agent attempt path，或給出
    actionable error 要求 `--intent`。
- 若使用者省略 `--intent` 但已提供 agent hint，AIT 應採用安全 default
  intent title，例如 `manual claude-code run`，並在 JSON/text output 裡標示
  `intent_inferred: true`。
- Dev port guard 只在明確 dev command 下執行，不得檢查 unrelated ports 來阻擋
  agent attempt。
- 保留 backward compatibility：舊的 `ait run -- <server command>` 可以先維持，
  但 docs 應引導使用 `ait dev run`。

Acceptance tests：

- `test_ait_run_adapter_without_intent_does_not_start_dev_server`
- `test_ait_run_agent_hint_infers_intent_title`
- `test_ait_run_dev_server_preflight_only_for_dev_path`
- `test_ait_dev_run_keeps_port_guard`

### 5. 消除 Dogfood 對 `AIT_WRAPPER_BYPASS` 的需求

目標：使用 AIT 安裝的 `.ait/bin/claude` / `.ait/bin/codex` 時，不需要繞過
AIT orchestration。

實作方向：

- Role runner 應從 adapter resolution 找到 real binary，避免 wrapper recursion。
- 若必須呼叫 wrapper path，必須在 AIT 管理的 child env 中清楚標記 current
  attempt/session context，不能要求使用者手動設 `AIT_WRAPPER_BYPASS=1`。
- CLI output 應說明實際執行的 binary、cwd、workspace ref、permission policy。

Acceptance tests：

- `test_role_mode_does_not_require_wrapper_bypass`
- `test_role_mode_avoids_wrapper_recursion`
- `test_role_mode_records_resolved_binary_provenance`

### 6. 文件與網站誠實邊界

目標：AIT 可以用吸引人的方式凸顯願景，但不能把 placeholder 寫成已完成能力。

立即修正：

- 工程文件必須明確標示：目前 `role` mode 已有 attempt/review linkage scaffold，
  但真實 implementer/reviewer invocation 是 P0 缺口。
- 網站 command reference 應說明：`panel|council|sequential` 目前支援 real local
  adapter invocation；`role` 的真實外部 agent invocation 尚未完成。
- README 可以繼續主打 shared memory、agent handoff、adversarial review，但避免
  暗示 `session run --mode role` 已能完成 Claude implement / Codex review。

Acceptance tests：

- `test_docs_mark_role_mode_truthfully_until_real_invocation_lands`
- `mkdocs build --strict`

## P1 工作項

- `ait session run --mode role --dry-run`：輸出 command plan、permission
  policy、context refs、workspace plan，不啟動 agents。
- `ait session run --mode role --plan-only --format json`：給 AI agent 或 IDE
  deterministic 讀取。
- `ait session handoff latest --from <response-id> --to <agent>`：把某個
  response/attempt/review 組成下一個 agent 的 context。
- `ait session compare latest`：比較不同 implementer attempts 的 changed
  files、tests、review findings。
- `ait session debate latest --agents claude-code,codex --rounds 2`：只產生
  advisory responses，不直接 mutation。
- `ait session decision --accept <attempt-or-response> --require-review`：把
  session decision 與 apply/review gate 連起來。

## 建議實作順序

1. 文件誠實化與 failing tests
   - 更新 docs/site，清楚標示 role 真實 invocation 是 P0。
   - 先補 regression tests，固定 placeholder 不能再被當成完成行為。
2. `ait run` 路由修正
   - 讓 explicit `--adapter` / `--agent` 不再誤入 dev server path。
   - 確保 dev port guard 只屬於 dev command。
3. Role implementer real invocation
   - 先支援 `claude-code` 與 `codex`。
   - 保留 fake/local command deterministic test path。
4. Role reviewer real invocation
   - 接上 adversarial review adapter。
   - reviewer failure fail closed。
5. Handoff context artifact
   - 加強 `AIT_CONTEXT_FILE` 與 manifest trust classes。
   - 確保 accepted memory 才能進長期記憶。
6. End-to-end dogfood
   - 用一個真實 session 跑 Claude implement / Codex review。
   - 驗證不需要 bypass、不碰 root checkout、不被 port guard 擋住。
7. Release
   - `mkdocs build --strict`
   - targeted pytest
   - full pytest
   - bump PyPI/npm versions
   - PyPI deploy；npm deploy 仍由使用者手動處理。

## 不可接受狀態

- `role` mode 繼續輸出 placeholder，卻在文件或網站宣稱是真實 invocation。
- Agent invocation 仍需要使用者手動設 `AIT_WRAPPER_BYPASS=1`。
- Agent-to-agent handoff 仍需要使用者手動叫每個 agent 讀取前一輪檔案。
- `ait run --adapter ...` 被 unrelated dev ports 擋住。
- Reviewer 可以修改 implementer workspace。
- 多個 agents 同意後自動 apply 或自動 promote memory。
- Advisory response 未經 decision gate 被寫成 trusted long-term memory。

## 完成定義

P0 完成時，下面流程必須成立：

```bash
ait session start "Add package split and review it" \
  --agents claude-code,codex \
  --claude-permission-mode plan \
  --codex-sandbox read-only \
  --codex-approval never

ait session ask latest "Claude implement, Codex review. Keep root checkout clean."

ait session run latest --mode role \
  --implementer claude-code \
  --reviewer codex \
  --package package-a=src/package_a,tests/test_package_a.py
```

驗收條件：

- Claude Code child process 真的被呼叫，command/provenance 可查。
- Codex reviewer child process 真的被呼叫，review/provenance 可查。
- Implementer changes 只存在 isolated attempt workspace。
- Root checkout 維持乾淨，直到使用者明確 `ait apply`。
- `AIT_CONTEXT_FILE` 自動包含 prior turns / accepted decisions / live memory /
  attempt evidence。
- 不需要 `AIT_WRAPPER_BYPASS=1`。
- 不會碰 dev server port guard。
- `ait session responses latest` 能列出 implementer response、reviewer response、
  linked attempt id、linked review id。
