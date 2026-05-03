---
title: ait command reference
description: >-
  Reference of common ait commands — init, status, doctor, adapter, attempt,
  intent, context, memory, graph, repair, upgrade, and shell auto-activation.
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

## Attempts and intents

```bash
ait attempt list
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
ait attempt discard <attempt-id>

ait intent show <intent-id>
ait context <intent-id>
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
