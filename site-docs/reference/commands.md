---
title: ait command reference
description: >-
  Reference of common ait commands — init, run, apply, recover, status,
  doctor, adapter, attempt, intent, memory, graph, repair, upgrade, and shell
  auto-activation.
---

# Command reference

## Initialization and health

```bash
ait init
ait status
ait status --all
ait doctor
ait doctor --fix
```

## Adapters

```bash
ait adapter list
ait adapter doctor claude-code
ait adapter setup claude-code
```

Replace `claude-code` with `codex`, `aider`, `gemini`, `cursor`, or
`shell` as needed.

## Daily run and apply flow

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --apply auto --adapter codex --intent "Implement parser edge cases" -- codex
ait apply latest
ait recover latest
ait recover latest --debug
```

`ait apply` is the daily entry point for applying a successful result.
`ait recover` is the daily entry point for held, failed, interrupted, or
conflicted results.

## Attempts and intents

```bash
ait attempt list
ait attempt show <attempt-id>

ait intent show <intent-id>
ait context <intent-id>
```

Advanced attempt commands remain available when you need low-level Git
control:

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

## Wrapping commands

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

## Repair

```bash
ait repair
ait repair codex
```

## Upgrade

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
