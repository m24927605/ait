# Local Multi-Agent Terminal Orchestration Goal Prompt

Use this prompt with `/goal` when asking an AI coding agent to implement the
AIT Local Multi-Agent Terminal Orchestration direction.

```text
請以 Staff+ Product、Platform Architect、DevRel、Security/Trust、Docs、Open Source Maintainer、Senior Python Engineer 團隊視角，依照：

  - `docs/local-multi-agent-session-room-design-zh.md`
  - `docs/local-multi-agent-terminal-orchestration-design-zh.md`

  完整實作 AIT Local Multi-Agent Terminal Orchestration，也就是互動式 multi-agent session room 的 terminal / PTY 層。

  背景：

  AIT 已有 Local Multi-Agent Session Room 基礎能力：
  - `.ait/sessions/` repo-local session artifacts
  - `ait session start/ask/show/list/responses/export`
  - panel/council/sequential real adapter / fake / local command fan-out
  - Role Mode implementer attempt + reviewer evidence
  - per-agent context manifest
  - participant add/remove/list
  - adaptive allocation dry-run
  - split implementation integration plan / overlap hold
  - no auto apply，repo mutation 仍走 isolated attempt + review/apply gate

  現在要補完整互動式 terminal orchestration：

  核心目標：

  讓使用者可以在同一個 AIT session 裡 attach 到多個互動式 local agent CLI，例如 Claude Code、Codex、Aider、Gemini、Cursor 或 shell/fake PTY agents。每個 agent 必須有獨立 PTY、獨立 response
  id、獨立 transcript/event stream、獨立 context manifest、獨立 lifecycle。使用者可以明確 routing input 給單一 agent 或全部 agents；AIT 必須保留 attribution、redaction、provenance，且任何
  repo mutation 仍然必須走 isolated attempt + review/apply gate。

  請先讀現有 repo 架構與目前實作，尤其是：
  - `src/ait/session_room.py`
  - `src/ait/cli/session.py`
  - `src/ait/runner_pty.py`
  - `src/ait/daemon_transport.py`
  - `src/ait/daemon.py`
  - `src/ait/runner.py`
  - `src/ait/runner_context.py`
  - `src/ait/redaction.py`
  - `tests/test_cli_session.py`

  請不要重寫既有 session room；以 additive、backward-compatible、phase-by-phase 方式落地。

  請依序完成：

  1. Phase 5a：Foreground attach MVP
     - 新增 `ait session attach latest`
     - 新增 `ait session attach latest --format json`，只輸出 attach plan，不啟動互動 UI
     - 每個 active participant 可擁有一個 PTY process
     - 支援 fake/local PTY agents 用於 deterministic tests
     - 每個 PTY 都有 `pty_id`、`participant_id`、`response_id`、pid、state、context_manifest_ref
     - 建立 streaming event store：
       - `.ait/sessions/<session-id>/streams/events.jsonl`
       - events 包含 `pty_started`、`pty_output`、`pty_input`、`pty_resize`、`pty_exited`、`pty_cancelled`、`attach_started`、`attach_detached`、`route_changed`
     - 支援簡單 stacked/prefix renderer，不需要完整 curses UI
     - 支援 explicit input routing：
       - `/to <agent-or-participant-id> <text>`
       - `/all <text>`
       - `/kill <agent>`
       - `/detach`
     - `/to` 只能送到指定 participant
     - `/all` 必須為每個 participant 建立獨立 input event
     - agent output 不能自動送進其他 agent stdin
     - detach MVP 可以保守處理：若 PTY 仍在跑，可拒絕 detach 或需要 explicit `--terminate-on-detach`
     - transcript 必須能在 exit/cancel 後組成 raw + redacted refs

  2. Phase 5b：Session panes/send/kill/replay
     - 新增：
       - `ait session panes latest --format json`
       - `ait session send latest --to <agent> "message"`
       - `ait session send latest --all "message"`
       - `ait session kill latest --agent <agent>`
       - `ait session replay latest --turn latest`
     - 若 Phase 5a 尚未做 daemon-owned PTY，`send/kill` 可以先限制在可恢復的 foreground/recorded state，但 JSON 必須明確回報 blocking reasons
     - `panes --format json` 必須 machine-actionable，包含 PTY state、pid、participant_id、response_id、last_output_at、provenance refs
     - `replay` 必須從 event stream deterministic replay，不混 attribution

  3. Phase 5c：Daemon-owned PTY / detach-resume 設計或最小實作
     - 若可行，實作 local Unix-socket session terminal daemon ownership，讓 `attach` 可 detach/resume active PTYs
     - 若太大，至少完成可執行 scaffold + docs + tests 明確標示 pending
     - 不得留下 orphan process without recovery metadata
     - stale PTY 必須能標記 crashed/cancelled
     - kill one agent 不得 kill siblings

  4. Attempt / review integration
     - advisory PTY participant 不得在 root checkout mutation
     - implementer PTY 必須跑在 isolated attempt workspace
     - reviewer PTY 不得寫 implementer workspace
     - `AIT_CONTEXT_FILE` 必須 per PTY / per participant
     - 若有 `AIT_WORKSPACE_REF`，必須指向 isolated attempt
     - terminal session command 不得 apply changes
     - `ait apply <attempt-id>` 仍是唯一 apply gate

  5. Safety / trust requirements
     - no SaaS dependency
     - no telemetry
     - no hidden network by AIT orchestration
     - provider CLI network behavior must be visible as invoked local command provenance
     - raw terminal payload local-only
     - redaction before replay/export/context reuse
     - terminal escape sequences sanitized for export/replay
     - output from different agents never stored without attribution
     - one agent cannot write another agent’s PTY/input stream
     - input/resize/cancel events attributable to user or AIT actor
     - policy-blocked memory must not enter PTY context
     - agent output is advisory unless explicitly accepted through session decision/memory gate

  請同步更新必要 docs / command reference，但不要做無關大改。

  測試至少覆蓋：

  - attach JSON plan does not start PTY and does not mutate root checkout
  - foreground attach starts two fake PTY agents with separate `pty_id` / `response_id`
  - interleaved output remains attributed in event store
  - `/to agent message` only reaches that agent stdin
  - `/all message` creates separate input events per participant
  - `/kill codex` cancels only Codex, sibling keeps running or exits independently
  - `/detach` behavior is explicit and safe
  - timeout/cancel stores partial output
  - raw + redacted terminal transcript refs are written
  - redaction removes secret fixture from replay/export
  - terminal escape sequence is sanitized for replay/export
  - `panes --format json` includes machine-actionable state
  - `replay` deterministic and attributed
  - advisory PTY leaves root checkout unchanged
  - implementer PTY uses isolated attempt workspace
  - reviewer PTY evidence remains separate from implementer attempt
  - no auto apply
  - existing `ait session run --mode panel/role`, `ait run`, `ait review`, `ait apply`, `ait recover` targeted tests still pass

  實作時請注意：
  - 不要 revert 使用者既有未提交變更
  - 優先使用現有 patterns，不要大改 CLI 架構
  - 優先 fake/local PTY tests，避免測試依賴真 Claude/Codex/Aider
  - 每個 phase 完成後跑相關 tests
  - 若全量測試太慢，至少跑新測試與受影響既有 tests，並清楚回報未跑項目

  最終回報請包含：
  - 完成的 phases
  - 修改檔案
  - CLI examples
  - JSON examples
  - event schema examples
  - 測試結果
  - 已知限制
  - 後續建議
```
