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
ait whereami --json
ait next --json
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --apply auto --adapter codex --intent "Implement parser edge cases" -- codex
ait apply latest
ait recover latest
ait recover latest --debug
ait resume latest
ait reconcile --json
ait merge --to main --dry-run --json
ait merge --to main --push --json
```

`ait apply` is the daily entry point for applying a successful result.
`ait recover` is the daily entry point for held, failed, interrupted, or
conflicted results.
`ait resume latest` opens a shell inside the recoverable attempt workspace so
you can continue interrupted work without manually copying workspace paths.

## Agent-first control plane

```bash
ait whereami --json
ait status --json
ait next --json
ait review report --format json
ait review report --format markdown --output docs/reviews/latest.md
ait merge --to main --mode auto --dry-run --json
```

Use these commands from Codex, Claude Code, or another coding agent. They
provide stable JSON state, legal next actions, dry-run merge operations, and
review evidence without interactive prompts.

## Review

```bash
ait review attempt latest-reviewable --mode light
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait run --review risk-based --review-adapter claude-code --adapter claude-code -- claude
```

`light` mode is a deterministic risk scan: changed-file count, sensitive paths,
dependency or lockfile changes, generated or binary files, and missing test
evidence. It does not call an LLM and does not block by itself.

`adversarial` mode calls the requested reviewer adapter. With
`--review-adapter claude-code`, AIT invokes the local `claude -p` CLI and strips
`ANTHROPIC_API_KEY` from the child environment so it does not silently use
provider API credits.

See [Review modes](review-modes.md) for the exact mode boundaries and
[Adversarial code review](adversarial-code-review.md) for the reviewer
workflow.

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

Memory is repo-local under `.ait/`. It combines prior attempts, commits,
curated notes, imported agent memory files, and accepted memory facts, then
recalls only policy-allowed context for future runs.

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
