---
title: ait vs agent managers, memory layers, and review bots
description: >-
  Where ait fits next to GUI-first agent managers, worktree managers,
  memory layers, review bots, and provenance tools: a local control plane
  and Git-native attempt ledger for AI coding agents.
---

# ait vs agent managers, memory layers, and review bots

ait is a **local control plane for AI coding agents**. The product center is
not the worktree, the memory file, the review comment, or the graph report by
itself. The center is the attempt ledger: an agent run becomes a reviewable
attempt linked to prompt, context, files, commits, memory evidence, review
findings, and an explicit apply/recover decision.

That makes ait overlap with several categories without being only one of them.
This page is the boundary map.

## Category Map

| Category | What users hire it for | Where ait overlaps | Where ait is different |
| --- | --- | --- | --- |
| GUI-first agent managers | Visual task boards, desktop workflows, queueing, and broad agent orchestration. | `ait graph --html` shows attempts, evidence, memory, hot files, and review state; `ait console --read-only` gives a loopback-only local console over the versioned `ait.work_graph` contract; `ait console action ... --dry-run` now records preflight/journal plans. | ait is CLI-first today. Browser mutation UI and action execution are not yet enabled. |
| Worktree managers | Keep parallel edits separated and clean up branches/worktrees. | Every wrapped run gets an isolated Git worktree and attempt lifecycle verbs such as apply, recover, and discard. | Worktrees are an implementation detail. ait also records prompt provenance, context, memory, review evidence, and outcomes. |
| Memory layers | Reuse project context across sessions and agents. | Live federated memory combines AIT-owned attempts, notes, accepted facts, review findings, and current repo memory files such as `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, and Cursor rules. | ait memory is attempt-derived and evidence-backed. It is not hidden chat memory, not a vector database product, and not automatic prompt stuffing. |
| Review bots | Challenge code before merge and leave findings. | `ait review` can run deterministic light checks or an adversarial reviewer adapter before apply. High-risk findings can hold the attempt, and the deterministic benchmark fixture now covers 10 cases. Explicit `--dogfood` real reviewer benchmark runs record adapter metadata. | ait review is local and attempt-aware. Public docs do not claim benchmark-proven defect detection yet; real Claude/Codex dogfood artifacts are still needed. |
| Provenance and audit tools | Answer who/what/why for AI-generated changes. | Attempts link intent, prompt, adapter, output, files, commits, status, memory, and review evidence under `.ait/`. | ait stays repo-local and Git-native. It does not require a SaaS dashboard, telemetry, or code upload. |

## The Shortcut

Use this test:

| If you mainly need... | Pick... |
| --- | --- |
| A visual desktop board to drive all agent work | A GUI-first agent manager, possibly with ait underneath later |
| Manual branch/worktree isolation for one-off runs | Raw `git worktree` or a small script |
| A cloud evaluation/observability platform | LLM observability tooling |
| Repo-local memory, attempt provenance, cross-agent handoff, and a review gate around existing CLIs | ait |

ait is most useful when you already use more than one coding agent, or when
the cost of losing prompts, context, review evidence, or failed attempts is
higher than the cost of one local control layer.

## Current State

| Surface | Current implementation | Do not claim yet |
| --- | --- | --- |
| Attempt ledger | Implemented through wrapped runs, attempt records, worktree isolation, and apply/recover flow. | That ait replaces Git review or human judgment. |
| Shared memory | Implemented through live federated recall from AIT-owned records and repo-local memory files. | That memory is a general vector database, hidden chat sync, or always-trusted context. |
| Graph/data model | `ait graph --html` produces a static local report. `ait graph --format json` includes `schema: ait.work_graph` and `schema_version`. `ait console --read-only` renders that data as a local daily console. `ait console action ... --dry-run` records preflight and journal entries. | That ait already ships browser mutation actions, action execution from the console, or a full GUI-first desktop console. |
| Review gate | Light deterministic review, adversarial reviewer workflows, a 10-case fixture, fake CI path, and real Claude/Codex dogfood artifacts exist. Current real artifacts are unavailable or failed. | That adversarial review has benchmark-proven quality across real projects. |
| Team adoption | Local metadata lives under `.ait/`; no SaaS, no telemetry. `.ait/policy.json` validation is fail-closed and runtime-enforced in apply, review, console action preflight, and context trust filtering. Metadata export/import dry-run plans exist. | Cross-machine metadata sync, non-dry-run import, or broad non-technical team readiness. |

## Roadmap Boundary

The next product step is still mutation hardening for the repo-local daily
console. The read-only surface exists, and the CLI action dry-run layer now has
preflight checks plus an append-only journal. Browser action controls and
execution should only appear after execution, retry, rollback, and recovery
tests described in
[`docs/console-mutation-recovery-design.md`](https://github.com/m24927605/ait/blob/main/docs/console-mutation-recovery-design.md)
exist. Public copy should keep calling `ait graph --html` a static report,
`ait graph --format json` a data contract, and `ait console --read-only` a
read-only console.

The next review step is running real reviewer dogfood artifacts. Stronger
review-quality claims require repeated Claude Code / Codex local reviewer
reports, false-positive reporting, latency/cost data, and fixture hashes
following
[`docs/review-benchmark-real-dogfood-design.md`](https://github.com/m24927605/ait/blob/main/docs/review-benchmark-real-dogfood-design.md).
Until then, public copy should frame adversarial review as an extra safety pass,
not proven defect-detection quality.

## Release Gate For Comparison Claims

Any new public comparison claim should pass this gate:

- It maps the claim to an implemented command, file, or documented roadmap
  item.
- It does not imply a finished GUI daily console or mutation surface.
- It does not claim benchmark-proven review quality without real reviewer
  dogfood and enough measurement data.
- It keeps local-only metadata, no telemetry, and Git as source of truth.
- It names the tradeoff where another category is better.

## Code Review Standard

Comparison-page changes should be reviewed as product claims, not only prose.
Reviewers should check whether every statement is backed by current code,
tests, or a clearly labeled roadmap item; whether category boundaries stay
specific; and whether the page avoids pretending that ait is a GUI product,
cloud memory layer, or proven review-quality benchmark today.

→ For worktree-specific tradeoffs, see
[Naked git-worktree vs ait](git-worktree-naked-vs-ait.md).
