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
ait run --adapter claude-code --intent "重構 query parser" -- claude
ait run --apply auto --adapter codex --intent "實作 parser edge cases" -- codex
ait apply latest
ait recover latest
ait recover latest --debug
```

`ait apply` 是日常套用成功結果的入口。`ait recover` 是 held、failed、
interrupted、conflicted 結果的日常復原入口。

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
