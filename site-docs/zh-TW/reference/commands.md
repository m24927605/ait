---
title: ait 指令參考
description: >-
  常用 ait 指令參考 — init、run、apply、recover、status、doctor、
  adapter、attempt、intent、memory、graph、repair、upgrade、shell
  auto-activation。
---

# 指令參考

## 初始化與健檢

```bash
ait init
ait status
ait status claude-code
ait status codex
ait status --all
ait doctor
ait doctor --fix
```

跑真實 agent 前可以先用 `ait status <adapter>` 確認目前 shell 會進 AIT。
`Bypass detection: wrapped` 代表指令解析到 repo-local wrapper。
`Bypass detection: bypass_risk` 代表指令解析到真正的 agent binary，會繞過
attempt capture。

Wrapper 會 passthrough 已知的 long-lived stdio modes，因為這些不是 one-shot
AIT attempt。目前包含 `codex app-server`，它需要保留原始 JSONL stdin/stdout
給 Codex companion integrations。單次呼叫若要強制直接執行 real binary，可設
`AIT_WRAPPER_BYPASS=1`。

## Adapter

```bash
ait adapter list
ait adapter doctor claude-code
ait adapter setup claude-code
```

`claude-code` 可換成 `codex`、`aider`、`gemini`、`cursor`、`shell`。

## 日常 run / apply flow

```bash
ait whereami --json
ait next --json
ait run --adapter claude-code --intent "重構 query parser" -- claude
ait run --apply auto --adapter codex --intent "實作 parser edge cases" -- codex
ait apply latest
ait recover latest
ait recover latest --debug
ait resume latest
ait reconcile --json
ait merge --to main --dry-run --json
ait merge --to main --push --json
```

`ait apply` 是日常套用成功結果的入口。`ait recover` 是 held、failed、
interrupted、conflicted 結果的日常復原入口。
`ait resume latest` 會直接開一個 shell 到可復原 attempt workspace，讓你不用
手動複製 workspace path 就能續修。

## Agent-first control plane

```bash
ait whereami --json
ait status --json
ait next --json
ait review report --format json
ait review report --format markdown --output docs/reviews/latest.md
ait merge --to main --mode auto --dry-run --json
```

這些指令適合 Codex、Claude Code 或其他 coding agent 使用。它們提供穩定
JSON 狀態、合法下一步、dry-run merge operations，以及不需要互動 prompt
的 review evidence。

## 本機 multi-agent sessions

```bash
ait session start "重構 auth" --agents claude-code,codex
ait session start "重構 auth" --agents claude-code,codex \
  --claude-permission-mode plan \
  --codex-sandbox read-only \
  --codex-approval never
ait session ask latest "比較風險"
ait session run latest --mode panel
ait session attach latest
ait session attach latest --format json
ait session panes latest --format json
ait session send latest --to fake:one "追問"
ait session send latest --all "列出剩餘風險"
ait session kill latest --agent fake:one
ait session replay latest --turn latest
```

`ait session run --mode panel|council|sequential` 會呼叫 active participants。
對 `claude-code`，AIT 會執行本機 `claude -p --permission-mode plan` CLI。
對 `codex`，AIT 會執行 `codex exec --sandbox read-only -`。AIT 會把
`--codex-approval` 記錄為 session consent metadata，但 Codex CLI 0.130 已不再
接受 `--ask-for-approval`，所以 AIT 不會傳入這個已移除的 flag。其他已註冊
adapter 會在 `PATH` 上存在時 fallback 到真實 CLI；自訂 local command 仍可用
`--agent-command agent=command` 指定。這些 response 是 advisory session
artifacts，不會直接 apply changes。

目前限制：`ait session run --mode role` 已有 isolated attempt/review linkage
scaffold，但還不是真實外部 implementer/reviewer invocation。今天要做真實本機
adapter advisory fan-out，請使用 `panel|council|sequential`；要讓另一個 agent
審查已完成 attempt，請使用 `ait review attempt --mode adversarial
--review-adapter ...`。

權限 policy 應在 session start 時先由使用者決定。AIT 會把這份設定存在
session 裡，後續 panel/council invocation 都照這份設定執行：

```bash
ait session start "調查 auth" --agents claude-code,codex \
  --claude-permission-mode dontAsk \
  --codex-sandbox workspace-write \
  --codex-approval on-request
```

保守預設是 `claude=plan`、`codex_sandbox=read-only`、`codex_approval=never`。
對 Codex CLI 0.130+，`codex_approval` 會保留在 AIT session state 供稽核與未來
policy mapping 使用；runtime enforcement 目前透過 Codex 支援的 `--sandbox`。

當 `ait session start` 在互動式 terminal 的 text mode 執行，且你沒有傳入
上述 flags 時，AIT 會在建立 session 前詢問缺少的 policy 值。`--format json`
與非 TTY automation 不會互動詢問；它們只會使用你傳入的 flags 或保守預設。

`ait session attach latest --format json` 只回傳 attach plan，不會啟動 PTY。
foreground attach 會替每個 active participant 建立一個本機 PTY，寫入
`.ait/sessions/<session-id>/streams/events.jsonl`，並為每個 response 保存
raw 與 redacted terminal transcript refs。互動輸入必須明確 routing：
`/to <agent-or-participant-id> <text>`、`/all <text>`、`/kill <agent>`、
`/detach`。

目前 terminal 實作是 foreground-owned。daemon-owned PTY detach/resume 尚未
啟用前，`send` 與可恢復的 `kill` 會用 machine-readable JSON 回報 blocking
reasons。Session terminal commands 不會 apply changes；`ait apply
<attempt-id>` 仍是唯一 apply gate。

## Review

```bash
ait review attempt latest-reviewable --mode light
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait run --review risk-based --review-adapter claude-code --adapter claude-code -- claude
```

`light` mode 是 deterministic risk scan：變更檔案數、敏感路徑、
dependency 或 lockfile、generated/binary 檔案、缺少 test evidence。它
不會呼叫 LLM，也不會自己 blocking。

`adversarial` mode 會呼叫指定 reviewer adapter。搭配
`--review-adapter claude-code` 時，AIT 會呼叫本機 `claude -p` CLI，並從
子行程環境移除 `ANTHROPIC_API_KEY`，避免 silent 使用 provider API credits。

精確邊界請看 [審查模式](review-modes.md)，完整 reviewer workflow 請看
[對抗式 code review](adversarial-code-review.md)。

## Attempts 與 intents

```bash
ait attempt list
ait attempt show <attempt-id>

ait intent show <intent-id>
ait context <intent-id>
```

需要低階 Git 控制時，仍可使用進階 attempt 指令：

```bash
ait apply <attempt-id> --mode current
ait attempt rebase <attempt-id> --onto main
ait attempt discard <attempt-id>
```

## Memory

```bash
ait memory
ait memory sources
ait memory sources --format json
ait memory sources --source claude
ait memory search "auth adapter"
ait memory recall "billing retry"
ait memory backfill --dry-run
ait memory backfill --import
ait memory lint
ait memory lint --fix
```

Memory 是 live federated repo view，也是 agent handoff channel。AIT-owned
memory 存在 `.ait/`，包含 prior attempts、commits、curated notes、accepted
memory facts、prior findings 與 review findings。`CLAUDE.md`、`AGENTS.md`、
`.claude/memory.md`、`.codex/memory.md`、`.cursor/rules` 等 live external
sources 會在 recall/run/review 當下即時讀取，並維持自己的 source of truth。

`ait memory sources` 與預設 `ait memory recall` 都是 zero-touch read：
不建立 `.ait/`，也不修改來源檔。`ait memory backfill --dry-run` 只預覽
repo-local agent memory，不會寫入。`backfill --import` 是明確 mutation /
deprecated path，會把 advisory memory 加到 `.ait/`。Global 或 repo 外部
memory 必須明確指定 `--global --path ...`。

## Graph

```bash
ait graph
ait graph --html
```

## 包裝指令

```bash
ait run --adapter claude-code --intent "重構 query parser" -- claude
ait run --adapter codex --intent "實作 parser edge cases" -- codex
ait run --adapter aider --intent "修 auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "重生 fixtures" -- \
  python scripts/regenerate_fixtures.py
```

當 `--adapter` 不是 `shell`，或使用者傳入 `--agent` 時，即使省略
`--intent`，`ait run` 仍會走 isolated agent-attempt path。AIT 會推斷一個
intent title，例如 `manual codex run`，並在 JSON output 裡標示
`intent_inferred`。舊的 no-intent shell path 仍保留給 dev-server commands；
這類 workflow 建議改用 `ait dev run ...`。

## 修復

```bash
ait repair
ait repair codex
```

## 升級

```bash
ait upgrade
ait upgrade --dry-run
ait --version
```

## Shell auto-activation

```bash
ait shell show --shell zsh
ait shell install --shell zsh
ait shell uninstall --shell zsh
```
