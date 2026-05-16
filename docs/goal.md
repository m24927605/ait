# AIT Multi-Agent Development Control Plane Goal

你是 AIT Staff Engineering Team，目標是把 AIT 打造成多 session、多 AI agent 共同開發時的首選 development control plane。

請以 Staff+ 等級團隊視角研究、設計、實作與驗證 AIT 在複雜 multi-agent workflow 下的能力。團隊角色包含：

- Staff Platform Architect：定義整體 control plane 架構與 agent state model
- Distributed Systems Engineer：處理 concurrency、locking、leases、race conditions、idempotency
- Git/Workspace Expert：處理 worktree isolation、branch lineage、merge/promote/reconcile/recover
- Agent UX/API Contract Lead：確保 AI agent 可用 JSON contract 自主判斷下一步
- Security/Privacy Engineer：確保 local-only、no telemetry、user data safe、不覆蓋使用者變更
- QA/Release Engineer：建立 acceptance tests、stress tests、regression suite 與 release readiness gate

## 核心問題

AIT 必須高度智能且最低干擾地支援：

- 多個 terminal sessions
- 多個 AI coding agents
- 多個 agents 同時處理同一 intent/task
- 多個 attempts 並行產生結果
- manual commits、partial failures、dirty worktree、stale workspaces
- 同時 discard / promote / merge / reconcile
- long-running sessions 與跨 agent handoff
- 真實 multi-agent session role invocation，而不是 placeholder orchestration
- local-only daemon / Unix socket / no network telemetry
- agent 不靠猜測 CLI，而是靠 machine-readable state contract 決策

## 請先閱讀現有實作與測試

特別是：

- `src/ait/agent_state.py`
- `src/ait/next_action.py`
- `src/ait/merge.py`
- `src/ait/reconcile.py`
- `src/ait/recovery.py`
- `src/ait/workspace.py`
- `src/ait/workspace_lease.py`
- `src/ait/daemon*.py`
- `src/ait/runner.py`
- `src/ait/review_report.py`
- `tests/test_agent_first_workflow.py`
- `tests/test_concurrency.py`
- `tests/test_daemon_e2e.py`
- `tests/test_landing.py`
- `tests/test_workspace.py`
- `tests/test_memory.py`
- `tests/test_query.py`

## 請完成以下工作

### 1. Multi-Agent Capability Audit

- 建立目前 AIT 在 multi-session / multi-agent 下已支援、部分支援、尚未支援的能力矩陣
- 找出 race conditions、unsafe promote/merge、stale lease、workspace lifecycle、metadata drift、manual commit lineage 等風險
- 明確區分「AIT 已可安全處理」與「agent 仍可能需要猜測或人工介入」的情境

### 2. Agent Decision Model

- 強化或驗證 `ait whereami --json`
- 強化或驗證 `ait status --json`
- 強化或驗證 `ait next --json`
- 確保每個狀態都能輸出：
  - `current_state`
  - `detected_context`
  - `safe_actions`
  - `unsafe_actions`
  - `recommended_command`
  - `blocking_reasons`
  - `recovery_commands`
- agent 必須能知道「我在哪、我能做什麼、什麼不能做、下一步是什麼」

### 3. Multi-Agent Coordination Design

- 設計低干擾 coordination model：
  - workspace leases
  - attempt ownership
  - promote/merge locks
  - stale workspace detection
  - idempotent retry
  - dry-run before mutation
  - no destructive cleanup by default
- 若現有實作不足，提出並實作最小可行改善
- 針對 `ait session run --mode role` 的真實 agent invocation 缺口，依
  [`multi-agent-session-ux-optimization-plan-zh.md`](multi-agent-session-ux-optimization-plan-zh.md)
  落地：implementer/reviewer 必須真的呼叫本機 agent adapter，且不能再以
  placeholder attempt 冒充完成。

### 4. Acceptance Tests

請新增或強化 dedicated tests，覆蓋：

- 多個 agents 同一 intent 平行 attempt
- 兩個 agents 同時嘗試 promote / merge 到同一 target branch
- dirty root checkout 時所有 destructive action 必須 block
- stale workspace / dead session 可 recover
- manual commit 可 reconcile 成 synthetic AIT result
- discard 一個 attempt 不影響其他 attempts
- promote 一個 attempt 不污染其他 workspaces
- `ait next --json` 在每個情境都給出合法下一步
- local daemon 只使用 Unix socket，不使用 outbound TCP
- untracked files 不可被刪除或覆蓋
- JSON error 必須 actionable

### 5. Agent-First Error Contract

所有新增或相關錯誤必須包含：

- `error_code`
- `message`
- `detected_state`
- `user_data_safe`
- `blocking_reason`
- `recommended_commands`
- `docs_reference`

### 6. Documentation

更新或新增文件，說明：

- multi-session workflow
- multi-agent same-task workflow
- safe promote/merge workflow
- stale session recovery workflow
- manual commit recovery workflow
- agent loop using `whereami/status/next`
- known limitations and safety guarantees

### 7. Verification

請執行：

```bash
PYTHONPATH=src uv run pytest -q tests/test_agent_first_workflow.py tests/test_concurrency.py tests/test_daemon_e2e.py tests/test_landing.py tests/test_workspace.py tests/test_memory.py tests/test_query.py
PYTHONPATH=src uv run pytest -q
git diff --check
```

## 完成後回報

- Staff team findings
- 已支援 / 部分支援 / 未支援能力矩陣
- 新增或修改的 tests
- 是否修改 production code
- multi-agent workflow 現在如何運作
- agent 應該如何使用 AIT 指令
- 測試結果
- backward compatibility
- residual risks
- 下一步建議

## 重要約束

- 不使用真實 Claude/Codex/API
- 不依賴網路
- 不覆蓋使用者變更
- 不刪 untracked files
- 不破壞既有 CLI backward compatibility
- 優先用 temporary git repo integration tests 驗證
- 只有測試揭露實際缺口時才修改 production code
