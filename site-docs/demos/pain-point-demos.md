---
title: Pain-point demos
description: >-
  Executable Claude Code and Codex demos aligned with
  examples/pain-point-demos: one folder per AIT pain point, each with its own
  workspace, run script, and AIT verification flow.
---

# Pain-point demos

The runnable demo suite lives in
[`examples/pain-point-demos`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos).
Each numbered folder owns its own Node.js demo project under `workspace/`, so
the files being changed are visible inside the same pain-point folder.

The shell scripts are scenario launchers. The evidence should come from AIT CLI
output: `ait query`, `ait attempt show`, `ait memory list`, `ait review
status`, `ait review report`, and `ait apply`.

## Prerequisites

- `ait` on `PATH`
- `git`
- Node.js and `npm`
- `python3`
- Claude Code CLI installed and logged in
- Codex CLI installed and logged in

## Prepare all workspaces

```bash
cd examples/pain-point-demos
./setup.sh
```

This creates or resets each folder's local project:

```text
examples/pain-point-demos/01-blast-radius/workspace/
examples/pain-point-demos/02-provenance/workspace/
...
examples/pain-point-demos/10-prompt-search/workspace/
```

## Run one demo

```bash
cd examples/pain-point-demos/01-blast-radius
./run.sh
cd workspace
```

Then use that folder's AIT verification flow. Do not explain the result from
private script state or ad-hoc filesystem checks; explain it from AIT metadata
and AIT CLI output.

## Run the full suite

```bash
cd examples/pain-point-demos
./run-all.sh
```

`run-all.sh` resets every workspace and runs every scenario.

## Folder map

| Folder | Pain point | What it demonstrates |
| --- | --- | --- |
| [`01-blast-radius`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/01-blast-radius) | Blast radius | Claude Code makes a broad risky edit, but AIT keeps it in an isolated attempt worktree. |
| [`02-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/02-provenance) | Provenance | AIT records the intent, agent, changed files, prompt/trace references, and attempt metadata. |
| [`03-failed-run-isolation`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/03-failed-run-isolation) | Failed-run isolation | Codex breaks a test; the failure is inspectable without polluting the main workspace. |
| [`04-memory-reuse`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/04-memory-reuse) | Memory reuse | Claude records an investigation; Codex later receives it through AIT context/memory. |
| [`05-parallel-agents`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/05-parallel-agents) | Parallel agents | Claude Code and Codex both edit `approach.txt` in separate attempt worktrees. |
| [`06-explicit-promotion`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/06-explicit-promotion) | Explicit apply | Multiple candidate attempts exist; only the selected result is accepted into the current branch. |
| [`07-cross-agent-handoff`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/07-cross-agent-handoff) | Agent-to-agent communication | An accepted Claude decision becomes repo memory that Codex can consume later. |
| [`08-local-only-provenance`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/08-local-only-provenance) | Local-only provenance | AIT metadata is inspectable locally through AIT commands, without a hosted dashboard. |
| [`09-verification-evidence`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-verification-evidence) | Adversarial review | A risky Claude result is challenged by an AIT adversarial review and recorded as blocked. |
| [`09-1-codex-reviewer`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/09-1-codex-reviewer) | Claude implementation, Codex review | Claude Code implements unsafe `divide`; Codex reviews it; review gate holds `ait apply`. |
| [`10-prompt-search`](https://github.com/m24927605/ait/tree/main/examples/pain-point-demos/10-prompt-search) | Prompt search | AIT query recovers an old attempt by intent text or changed file. |

## AIT verification flows

Each case README contains the exact commands. The common pattern is:

```bash
ait query --on attempt '<selector>' --format table
ait attempt show <attempt-id>
```

For memory cases:

```bash
ait memory list --format table
ait attempt show <claude-attempt-id>
ait attempt show <codex-attempt-id>
```

For adversarial review cases:

```bash
ait query --on attempt 'review.mode="adversarial"' --format table
ait query --on attempt 'review.status="blocked"' --format table
ait review finding list --severity high --format text
ait review report --attempt <attempt-id> --format json
```

For the `09-1-codex-reviewer` apply-gate evidence:

```bash
ait config show --format json
ait apply <attempt-id> --mode current
```

Expected result:

```text
AIT held the result because this repo requires review before apply.
Status: held
Reason: review gate: required review is blocked
```

## Talk track

Use the scripts to create the scenario, then switch to AIT commands for the
explanation. The audience should leave with one idea: AIT turns agent work into
isolated, queryable, reviewable Git attempts instead of asking people to trust
terminal scrollback.
