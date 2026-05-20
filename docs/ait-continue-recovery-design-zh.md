# AIT Continue Recovery Design

## 背景

使用者可能在三種狀態下失去 terminal：

1. 正在 `ait session attach latest` 的 multi-agent session UI 裡。
2. 正在某個 AIT attempt worktree 裡修改或檢查結果。
3. 正在 Claude Code、Codex、Aider 等 agent CLI 自己的互動 session 裡。

這三種狀態不能用同一個底層動作處理：

- `ait session attach latest` 回到 AIT session room，負責 session panes、PTY、input routing。
- `ait resume latest` 回到單一 attempt worktree，負責 worktree 環境與 finish hints。
- `ait continue` 是使用者層的自然恢復入口，負責判斷目前最合理的恢復點，再轉交給 attach 或 resume。

## 設計

`ait continue [selector]` 產生一份 `continue_plan`，再依互動狀態決定是否執行：

- JSON 或 non-interactive：只印 plan，不啟動 shell 或 PTY。
- interactive 且 target 是 `session_attach`：執行 `ait session attach <session_id>` 等效流程。
- interactive 且 target 是 `attempt_resume`：進入 `ait resume <attempt_id>` 的 worktree shell。
- 找不到可恢復目標：印出原因與限制。

`latest` 選擇規則：

1. 同時蒐集最新 session candidate 與 recoverable attempt candidate。
2. 以 session `updated_at` 與 attempt `heartbeat_at/ended_at/started_at` 比較時間。
3. 同一時間下，優先順序是 `session_attach`、`attempt_resume`、`session`。

Target types：

| target_type | 意義 | 下一步 |
| --- | --- | --- |
| `session_attach` | session 有 current turn 且有 active participants | `ait session attach <session_id>` |
| `attempt_resume` | 有 recoverable attempt worktree | `ait resume <attempt_id>` |
| `session` | session 存在但不能直接 attach | `ait session show <session_id>` |
| `none` | 沒有可恢復目標 | 顯示 blocking reason |

## 實作

新增檔案：

- `src/ait/continue_flow.py`
  - `build_continue_result()` 建立 continue plan。
  - `ContinueResult` 定義 JSON contract。
  - `AgentHint` 提供 agent-native resume 提示。
  - 從 saved Codex raw trace 擷取 `codex resume <id>`。

- `src/ait/cli/continue_cmd.py`
  - 處理 `ait continue` CLI。
  - JSON/non-interactive 只輸出 plan。
  - interactive session target 呼叫 `run_foreground_attach()`。
  - interactive attempt target 呼叫 `launch_resume_shell()`。

修改檔案：

- `src/ait/cli_parser.py`
  - 新增 top-level `continue` parser。

- `src/ait/cli/main.py`
  - 註冊 `continue` handler。

## Agent Resume Hint

AIT 只能保證恢復 AIT 自己管理的 session metadata 與 attempt worktree，不能保證 agent CLI 的原生 conversation 還存在。

目前 hint 策略：

| Agent harness | Hint |
| --- | --- |
| `claude-code` | `cd <workspace> && claude --continue` |
| `codex` | 若 trace 有 `codex resume <id>`，顯示該 native resume command |
| `codex` | 若 trace 沒有 resume id，提示回到 AIT worktree |
| `aider` | `cd <workspace> && aider` |
| other | `cd <workspace>` |

## 測試

新增 `tests/test_cli_continue.py`：

1. `test_continue_json_prefers_attachable_latest_session`
   - 建立 session 與 turn。
   - 驗證 `ait continue --format json` 回傳 `session_attach`。
   - 驗證 command 是 `ait session attach ...`。

2. `test_continue_no_interactive_falls_back_to_resume_attempt`
   - 建立 Claude Code attempt。
   - 驗證 non-interactive text 顯示 workspace、`ait resume`、`claude --continue`。

3. `test_continue_latest_uses_newer_attempt_over_older_session`
   - 建立較舊 session 與較新 attempt。
   - 驗證 `latest` 會選擇較新的 recoverable attempt。

4. `test_continue_json_reports_codex_native_resume_from_trace`
   - 建立 Codex attempt。
   - 寫入 raw trace：`codex resume 019dd9ba-fc1a`。
   - 驗證 JSON agent hint 擷取 native Codex resume command。

5. `test_continue_interactive_launches_resume_shell_for_attempt`
   - mock TTY 與 `launch_resume_shell()`。
   - 驗證 interactive attempt target 會進入 resume shell path。

既有 `tests/test_cli_resume.py` 保持通過，確保 `ait resume latest` 沒被改壞。

執行命令：

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_cli_continue.py tests/test_cli_resume.py -q
```

目前結果：

```text
9 passed
```

## 驗收

功能驗收：

- `ait continue --format json` 不啟動 PTY、不開 shell。
- 有 attachable session 時，`target_type=session_attach`。
- 沒有 session 但有 recoverable attempt 時，`target_type=attempt_resume`。
- attempt target 的 plan 包含 `ait resume <attempt_id>`、workspace path、finish steps。
- Claude Code attempt 顯示 `claude --continue` hint。
- Codex trace 有 native resume id 時，顯示 `codex resume <id>` hint。
- Aider attempt 顯示回到 worktree 並啟動 `aider` 的 hint。
- 找不到目標時，回傳 `target_type=none` 與 blocking reason。

安全驗收：

- JSON/non-interactive 模式不可啟動 PTY 或 shell。
- `ait resume latest` 原行為不改變。
- `ait session attach latest` 原行為不改變。
- `ait continue` 不直接 apply、commit、discard 或 mutate root checkout。
- 若 OS terminal process 已被 kill，文件與 CLI plan 必須明確說明 AIT 不能 resurrect process，只能恢復 metadata/worktree 或提供 agent-native hint。

## Code Review Checklist

獨立 code review note: `docs/code-review-ait-continue-2026-05-20.md`。

Review focus：

- `continue` 是否只是 router，沒有混淆 session attach 與 attempt resume 的責任。
- `latest` 選擇是否使用可比較的時間欄位，且同時間有穩定 priority。
- JSON contract 是否包含 `schema_version`、`kind`、`target_type`、`command`、`safe_actions`、`blocking_reasons`、`limitations`。
- interactive path 是否只在 stdin/stdout 都是 TTY 時啟動。
- non-interactive path 是否永遠只印 plan。
- agent-native hints 是否只是 hint，不被當成 AIT 可以保證恢復的能力。
- Codex resume id 擷取是否只讀 local raw trace，且缺 trace 時 graceful fallback。
- `ait resume latest` 測試仍通過。
- 未納入 `.envrc`、`.claude/`、`.codex/` 等 unrelated local files。

目前 self-review 結論：

- 無 blocking issue。
- 主要殘留風險是不同 agent CLI 的 native resume command 可能隨版本變動；因此 CLI 只將它們列為 hint，AIT 的保證邊界維持在 session metadata 與 attempt worktree。
