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
ait status --all
ait doctor
ait doctor --fix
```

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
ait reconcile --json
ait merge --to main --dry-run --json
ait merge --to main --push --json
```

`ait apply` 是日常套用成功結果的入口。`ait recover` 是 held、failed、
interrupted、conflicted 結果的日常復原入口。

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
ait attempt promote <attempt-id> --to main
ait attempt rebase <attempt-id> --onto main
ait attempt discard <attempt-id>
```

## Memory

```bash
ait memory
ait memory search "auth adapter"
ait memory recall "billing retry"
ait memory lint
ait memory lint --fix
```

Memory 是 repo-local，存在 `.ait/`。它整合 prior attempts、commits、
curated notes、匯入的 agent memory files，以及 accepted memory facts，
之後只召回 policy 允許的 context 給未來執行。

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
