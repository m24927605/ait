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
ait status claude-code
ait status codex
ait status --all
ait doctor
ait doctor --fix
```

Use `ait status <adapter>` before a real agent run when you want to confirm
that this shell will enter AIT. `Bypass detection: wrapped` means the command
resolves to the repo-local wrapper. `Bypass detection: bypass_risk` means the
command resolves to the real agent binary and will bypass attempt capture.

Wrappers pass through known long-lived stdio modes that are not one-shot AIT
attempts. Today that includes `codex app-server`, which must keep raw JSONL
stdin/stdout for Codex companion integrations. Set `AIT_WRAPPER_BYPASS=1` to
force direct execution of the real binary for a specific invocation.

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
With agent wrappers installed, a bare interactive agent command such as
`codex` or `claude` first tries to continue the latest active recoverable AIT
worktree. Commands that include a new task, such as `claude -p ...` or
`codex exec ...`, still start a fresh AIT attempt.

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

## Local multi-agent sessions

```bash
ait session start "Refactor auth" --agents claude-code,codex
ait session start "Refactor auth" --agents claude-code,codex \
  --claude-permission-mode plan \
  --codex-sandbox read-only \
  --codex-approval never
ait session ask latest "Compare the risks"
ait session run latest --mode panel
ait session attach latest
ait session attach latest --format json
ait session panes latest --format json
ait session send latest --to fake:one "follow up"
ait session send latest --all "list remaining risks"
ait session kill latest --agent fake:one
ait session replay latest --turn latest
```

`ait session run --mode panel|council|sequential` invokes active participants.
For `claude-code`, AIT runs the local `claude -p --permission-mode plan` CLI.
For `codex`, AIT runs `codex exec --sandbox read-only -`. AIT records
`--codex-approval` as session consent metadata, but Codex CLI 0.130 no longer
accepts `--ask-for-approval`, so AIT does not pass that removed flag. Other
registered adapters fall back to their real CLI command when present on `PATH`;
explicit `--agent-command agent=command` remains available for custom local
commands. Responses are advisory session artifacts, not applied changes.

Role mode can invoke real local implementer adapters inside isolated attempt
workspaces, with per-role `AIT_CONTEXT_FILE` handoff and command provenance.
Role reviewers run the adversarial review substrate against the implementer
attempt: `claude-code` uses local `claude -p`, `codex` uses local
`codex exec --sandbox read-only -`, and fake reviewers remain deterministic for
tests. Role outputs remain reviewable session artifacts; applying changes still
requires an explicit `ait apply`.

Choose the consented permission policy at session start. AIT stores that policy
on the session and reuses it for later panel/council invocations:

```bash
ait session start "Investigate auth" --agents claude-code,codex \
  --claude-permission-mode dontAsk \
  --codex-sandbox workspace-write \
  --codex-approval on-request
```

The conservative defaults are `claude=plan`, `codex_sandbox=read-only`, and
`codex_approval=never`. For Codex CLI 0.130+, `codex_approval` is preserved in
AIT session state for auditability and future policy mapping; runtime
enforcement is through Codex's supported `--sandbox` flag.

When `ait session start` runs in an interactive terminal in text mode and you
did not pass those flags, AIT asks for the missing policy values before creating
the session. `--format json` and non-TTY automation never prompt; they use the
flags you passed or the conservative defaults.

`ait session attach latest --format json` returns an attach plan only; it does
not start PTYs. Foreground attach starts one local PTY per active participant,
records `.ait/sessions/<session-id>/streams/events.jsonl`, and writes raw plus
redacted terminal transcript refs per response. Input routing is explicit with
`/to <agent-or-participant-id> <text>`, `/all <text>`, `/kill <agent>`, and
`/detach`.

The current terminal implementation is foreground-owned. `send` and resumable
`kill` report machine-readable blocking reasons until daemon-owned PTY
detach/resume is enabled. Session terminal commands do not apply changes;
`ait apply <attempt-id>` remains the apply gate.

## Review

```bash
ait review attempt latest-reviewable --mode light
ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code
ait run --review risk-based --review-adapter claude-code --adapter claude-code -- claude
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json --fake-reviewer fake:case --format json
ait review benchmark run --fixture tests/fixtures/review_benchmark/cases.json --reviewer-adapter claude-code --dogfood --permission-profile read-only --format json
ait review benchmark report --input benchmark.json --format markdown
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

`ait review benchmark run` is a local deterministic measurement path when used
with `fake:*` reviewers. It does not call a real LLM, network, login state, API
key, or paid credits. The Markdown report command formats a previously written
JSON benchmark payload; it is dogfood evidence, not proof of review
quality.

Real reviewer benchmark dogfood is opt-in. Passing `--reviewer-adapter` without
`--dogfood` fails closed. With `--dogfood`, AIT records adapter metadata,
resolved binary path when known, redacted command argv, local-auth assumptions,
permission profile, fixture hash, latency, and token/cost placeholders. A single
local dogfood run is not a benchmark-proven quality claim.

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

Memory is a live federated repo view and agent handoff channel. AIT-owned memory
under `.ait/` includes prior attempts, commits, curated notes, accepted memory
facts, prior findings, and review findings. Live external sources such as
`CLAUDE.md`, `AGENTS.md`, `.claude/memory.md`, `.codex/memory.md`, and
`.cursor/rules` are read at recall/run/review time and remain their own source
of truth.

`ait memory sources` and default `ait memory recall` are zero-touch reads:
they do not create `.ait/` and do not mutate source files. `ait memory backfill
--dry-run` previews repo-local agent memory files without writing. `backfill
--import` is an explicit mutation/deprecated path that adds advisory memory
under `.ait/`. Global or out-of-repo memory requires an explicit
`--global --path ...`.

## Graph

```bash
ait graph
ait graph --format json
ait graph --html
ait console --read-only
ait console --read-only --serve-local --host 127.0.0.1 --port 0
ait console action apply --attempt latest --dry-run --format json
ait console action recover --attempt latest --dry-run --format json
ait console action discard --attempt latest --dry-run --format json
```

`ait graph --format json` emits the versioned `ait.work_graph` schema used as
the data contract for the repo-local daily console. `ait graph --html` writes a
static local report under `.ait/report/graph.html` by default.

`ait console --read-only` writes a temporary read-only daily console HTML page
from the same graph data without creating `.ait/` in an uninitialized repo. The
optional `--serve-local` mode only accepts loopback hosts such as `127.0.0.1`
or `localhost`.

`ait console action ... --dry-run` is the preflight and journal contract for
future console mutation. It writes an append-only local journal entry under
`.ait/actions/console-actions.jsonl` and returns `schema: ait.console_action`.
It does not execute apply/recover/discard; real mutation still goes through the
existing CLI/domain paths.

## Team readiness

```bash
ait policy validate --format json
ait policy show --format json
ait metadata export --dry-run --output ait-metadata.bundle.json --format json
ait metadata import --input ait-metadata.bundle.json --dry-run --format json
```

`.ait/policy.json` uses `schema: ait.team_policy`. Invalid policy fails closed
in `ait policy validate` and in runtime paths that consume team policy: apply,
review, console action preflight, and context trust filtering. The current
metadata commands are local dry-run planning tools: export omits raw traces,
absolute paths, memory bodies, and review finding bodies by default; import
writes nothing and reports a `schema: ait.metadata_import_plan` payload. There
is no SaaS sync, telemetry, automatic push, or automatic merge.

## Wrapping commands

```bash
ait run --adapter claude-code --intent "Refactor query parser" -- claude
ait run --adapter codex --intent "Implement parser edge cases" -- codex
ait run --adapter aider --intent "Fix auth expiry" -- aider src/auth.py
ait run --adapter shell --intent "Regenerate fixtures" -- \
  python scripts/regenerate_fixtures.py
```

When `--adapter` is not `shell`, or when `--agent` is provided, `ait run` stays
on the isolated agent-attempt path even if `--intent` is omitted. In that case
AIT infers an intent title such as `manual codex run` and reports
`intent_inferred` in JSON output. The legacy no-intent shell path remains for
dev-server commands; prefer `ait dev run ...` for that workflow.

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

The shell hook shows a one-time `ait continue` reminder when interrupted work
is recoverable. Agent-wrapper continuation can be disabled with
`AIT_CONTINUE_ON_AGENT=0`; the reminder can be disabled with
`AIT_CONTINUE_REMINDER=0`.
