# /goal Prompt: Make AIT README And Website Compelling Enough For First-Time Users

You are the AIT Staff Product, DevRel, Docs, Growth, Security/Trust, and UX Writing team.

Your goal is to rewrite and restructure the AIT project README and documentation website so that a first-time visitor immediately understands why AIT matters, trusts the project, and wants to try it.

The ambition is not cosmetic polish. The ambition is to make AIT feel like a serious, high-potential open-source developer tool that could earn GitHub-star momentum: clear positioning, sharp pain, believable proof, strong demo paths, and professional writing.

## Objective

Make the project root README and website communicate AIT as:

> The Git safety layer for AI coding agents: run Claude Code, Codex, Aider, Gemini, and Cursor in isolated attempts with provenance, shared long-term repo memory, cross-agent handoff, adversarial review, and explicit apply/recover.

The final result must make a first-time user think:

> This is exactly what I need when Claude/Codex can modify a real repo. I want to install it and try the demo.

## Staff Team Roles

Adopt these roles while doing the work:

- Staff Product Engineer: clarify the product promise and remove vague claims.
- Staff DevRel Engineer: make the first-run path compelling and easy to try.
- Staff Docs Engineer: ensure README and site are navigable, accurate, and maintainable.
- Staff Growth Engineer: improve star-worthy positioning, social proof hooks, and demo links.
- Staff Security/Trust Engineer: make local-first, no telemetry, provenance, and no-SaaS guarantees clear without overclaiming.
- Staff UX Writer: make English and Traditional Chinese sound natural, direct, and professional.

## Current Concern

The current README and website mention many features, but the hierarchy may still be weak.

AIT has several core strengths that must be represented clearly:

1. Git safety layer for AI coding agents
2. Worktree isolation
3. Attempt provenance
4. Shared cross-agent memory
5. Long-term repo-local memory
6. Cross-agent handoff
7. Parallel agent attempts
8. Explicit apply/recover flow
9. Adversarial review / review-gated apply
10. Local-first metadata / no SaaS / no telemetry
11. Queryable prompt and attempt history
12. Executable pain-point demos

Do not let adversarial review become the only main axis. It is a strong feature, but the product story is broader: safe, traceable, memory-aware, multi-agent development on top of Git.

## Files To Review First

Read these before editing:

- `README.md`
- `README.zh-TW.md`
- `mkdocs.yml`
- `site-docs/index.md`
- `site-docs/zh-TW/index.md`
- `site-docs/why-ait.md`
- `site-docs/zh-TW/why-ait.md`
- `site-docs/demos/pain-point-demos.md`
- `site-docs/zh-TW/demos/pain-point-demos.md`
- `site-docs/reference/adversarial-code-review.md`
- `site-docs/zh-TW/reference/adversarial-code-review.md`
- `site-docs/reference/review-modes.md`
- `site-docs/zh-TW/reference/review-modes.md`
- `examples/pain-point-demos/README.md`
- every `examples/pain-point-demos/*/README.md`
- every `examples/pain-point-demos/*/README.zh-TW.md`

## Required Outcome

### 1. README First-Screen Rewrite

Improve both:

- `README.md`
- `README.zh-TW.md`

The first screen must answer, quickly:

- What is AIT?
- Who is it for?
- What immediate pain does it solve?
- Why is it different from just using Claude Code/Codex directly?
- Why can I trust it in a real repo?
- What command do I run first?

Expected shape:

1. Strong one-line positioning
2. Short paragraph explaining the core workflow
3. Quick install / first run
4. Key capabilities
5. Problems solved with runnable example links
6. Core concept
7. What it feels like
8. Quick examples
9. Integrations
10. Trust / local-first / status / docs

Do not make the README feel like a dense feature encyclopedia. It should be skimmable.

### 2. Key Capabilities Must Be Prominent

Root README and website homepage must include a clear "Key Capabilities" / "核心特色" section covering:

- Git safety layer
- Worktree isolation
- Attempt provenance
- Shared cross-agent memory
- Long-term repo memory
- Cross-agent handoff
- Parallel agent attempts
- Explicit apply/recover flow
- Adversarial review
- Local-first metadata
- Queryable history

These must be written as product benefits, not internal implementation trivia.

### 3. Shared Memory And Long-Term Memory Must Be First-Class

Shared memory and long-term memory must not be hidden inside one row.

Clarify:

- shared memory means different agents can reuse the same repo-local context
- long-term memory means useful attempts, commits, notes, accepted facts, imported `CLAUDE.md` / `AGENTS.md`, and prior findings can survive across terminals, sessions, and time
- this is not chat-window memory
- this is repo-local and inspectable

Use precise wording. Avoid overclaiming that all memory is always trusted; respect policy/accepted facts where relevant.

### 4. Pain-Point Demos Must Align With Actual Executable Examples

The website must align with `examples/pain-point-demos`.

Every pain point must link to the corresponding executable example folder:

- `01-blast-radius`
- `02-provenance`
- `03-failed-run-isolation`
- `04-memory-reuse`
- `05-parallel-agents`
- `06-explicit-promotion`
- `07-cross-agent-handoff`
- `08-local-only-provenance`
- `09-verification-evidence`
- `09-1-codex-reviewer`
- `10-prompt-search`

Rules:

- Do not document stale `~/lab/ait-pain-demo` flows if the actual demos now live per-folder.
- Do not say proof comes from `verify.sh`.
- Scripts are scenario launchers.
- Demo explanation must use AIT CLI output.
- Each pain point should have a direct example link.
- The 09 pain point can link to both `09-verification-evidence` and `09-1-codex-reviewer`.

### 5. Adversarial Review Positioning

Adversarial review should be present and compelling, but not the whole product.

Position it as:

- a high-risk-change review gate
- a way to separate implementation and review roles
- a way to make Claude Code and Codex review each other
- structured review evidence, not chat scrollback
- optionally able to hold `ait apply` when policy requires review

Detailed explanation belongs in:

- `site-docs/reference/adversarial-code-review.md`
- `site-docs/zh-TW/reference/adversarial-code-review.md`
- `site-docs/reference/review-modes.md`
- `site-docs/zh-TW/reference/review-modes.md`

The homepage and README should summarize it, not let it dominate.

### 6. English And Traditional Chinese Must Both Be Natural

For `README.zh-TW.md` and `site-docs/zh-TW/**`:

- Do not translate sentence-by-sentence from English.
- Use fluent Traditional Chinese suitable for Taiwanese engineering readers.
- Keep technical terms where they improve clarity: `attempt`, `workspace`, `apply`, `recover`, `provenance`, `memory`, `review gate`.
- Avoid machine-translation phrasing.
- Avoid awkward phrases like "用 AI agent 寫 code" when "用 AI agent 寫程式" reads better.
- Keep the tone professional, direct, and concrete.

For English:

- Avoid hype without proof.
- Avoid vague "AI-powered" phrasing.
- Use concrete developer pain.
- Keep claims defensible.

### 7. Website Homepage Must Be More Than A Mirror

The website homepage should work as a landing page for first-time readers, not just a README copy.

It should include:

- positioning
- quick install
- key capabilities
- problems solved with runnable example links
- supported agents
- review/memory boundaries
- project links

It must stay consistent with README but does not need to be identical.

### 8. Trust And Safety Must Be Clear

Make clear:

- metadata is repo-local under `.ait/`
- no telemetry
- no SaaS dashboard required
- harness daemon is local-only / Unix socket
- AIT is not a Git replacement
- AIT is not another agent
- AIT wraps existing agent CLIs
- root checkout stays untouched until explicit apply
- unsafe apply can be held

Avoid implying AIT guarantees correctness. It provides safer workflow, provenance, memory, and review evidence.

### 9. Check For Stale Terminology

Search and fix stale or misleading terms where appropriate:

- `promote` if current user-facing flow should say `apply`
- stale `ait attempt promote` examples if they conflict with current CLI guidance
- stale `ait attempt discard` if current recovery/cleanup flow differs
- stale hosted-dashboard wording
- stale `~/lab/ait-pain-demo` demo setup
- claims that demo verification depends on `verify.sh`

Do not blindly replace if a term is still accurate in a specific context. Use judgment.

## Suggested Structure For README

Use this as a guide, not a rigid template:

```markdown
# ait

### Git-native safety workflow for AI coding agents

Short product paragraph.

Quick install.

## Key Capabilities

Table with the 10-11 capabilities.

## Problems ait Solves

Table with problem, AIT solution, runnable example link.

## Core Concept

AIT wraps agents, creates isolated attempts, records provenance, shares memory, and requires explicit apply.

## What It Feels Like

ait init
claude ...
ait status
ait apply latest

## Quick Examples

intent, ait run, memory, adversarial review, repair.

## Integrations

Claude Code, Codex, Aider, Gemini, Cursor, shell.

## How It Works

prompt -> wrapped agent -> isolated workspace -> metadata/commits/memory -> review/apply/recover.

## Install / Commands / Status / Docs
```

## Verification

After editing, run:

```bash
git diff --check
```

For website docs, run the available docs build. If `mkdocs` is not globally available, create a temporary venv outside the repo:

```bash
python3 -m venv /tmp/ait-docs-venv
/tmp/ait-docs-venv/bin/python -m pip install -q mkdocs-material mkdocs-static-i18n
/tmp/ait-docs-venv/bin/mkdocs build --strict
```

Do not commit generated `site/` output unless the repo already tracks it and the project expects that.

## Deliverables

When complete, report:

- changed files
- positioning changes
- how shared memory and long-term memory are now represented
- how pain-point demos are linked
- whether adversarial review is present but not over-dominant
- English/Traditional Chinese quality notes
- docs build result
- residual risks or follow-up recommendations

## Constraints

- Do not change product behavior unless documentation reveals an obvious broken command.
- Do not overwrite unrelated user changes.
- Do not commit `uv.lock` unless the project formally adopts `uv` in docs and CI.
- Do not remove existing demo files.
- Keep README and website consistent with executable demos.
- Keep claims technically defensible.
