# AIT Rebrand — Multi-Agent Dispatch Design

**Date:** 2026-05-21
**Status:** Approved by user, executing
**Owner:** Claude Code (orchestrator) + dispatched specialist agents

## Goal

Rework AIT's public surfaces (GitHub README × 2 languages, docs site, social
launch kit) so that an AI-power-user audience — engineers who already use
Claude Code, Codex CLI, Aider, Gemini CLI, or Cursor — can instantly answer:

1. What is AIT?
2. Why should I install it in the next five minutes?
3. How is it different from the tools I already pay for or self-host?

The existing surfaces fail (1) and (3) because they front-load infrastructure
jargon ("attempt ledger", "federated memory", "adversarial review") before any
concrete value lands.

## Non-goals

- Translate, copy-edit, or theme-tune existing copy. The goal is rewrite.
- Touch product code, tests, or the spec docs in `docs/ai-vcs-mvp-spec.md`,
  `docs/implementation-notes.md`, `docs/protocol-appendix.md`.
- Change examples in `examples/`, `tests/`, or `src/ait/`.
- Replace the mkdocs theme or restyle the entire site.
- Push to social channels — Phase 2 Track D produces drafts only.
- Auto-commit or auto-merge. All Phase 2 outputs land as `.draft` files.

## Audience and voice (locked decisions)

- **Audience:** AI power users already running Claude Code / Codex / Cursor /
  Aider / Gemini CLI. They know what an agent is. They have already had an
  agent break their repo, lose context across sessions, and rubber-stamp its
  own output. They do not need education on what an agent is; they need
  evidence that AIT solves problems they already feel.
- **Voice:** Linear / Vercel / Resend. Calm, engineer-soul, demo-heavy,
  zero slogans. Let the technology speak. High signal-to-noise. No "AI
  revolution" or "unleash your potential" language.

## Phase 1 — Positioning bible (sequential, blocking)

One agent, one document, blocking gate before any surface work begins.

**Agent:** Brand Guardian
**Inputs the agent must read:**

- `docs/ait-market-positioning-goal.md`
- `docs/ait-market-positioning-research.md`
- `docs/marketing/` (entire directory, including the manifesto)
- Current `README.md`, `README.zh-TW.md`
- Current `site-docs/index.md`, `site-docs/why-ait.md`,
  `site-docs/getting-started.md`, `site-docs/facts.md`
- `src/ait/__init__.py` and `src/ait/cli/main.py` for current command surface
- `examples/pain-point-demos/` directory listing for available demos
- `docs/aitbench-dogfood-report.md` for current benchmark posture

**Output:** `docs/ait-power-user-narrative-2026.md` containing:

1. One-line hero positioning, English (≤12 words) and Traditional Chinese
   (≤20 characters). Must avoid the banned phrases "Git workflow layer",
   "Git safety layer", "control plane" (per existing positioning goal doc).
2. Three power-user pain points written in their idiom (worktree-stomping
   collisions, lost cross-session context, agents lying about test passes).
3. Differentiation table against: Aider, Cursor, Cline, Continue.dev.
   Each row must cite a concrete AIT capability tied to a real CLI command
   or file in `src/ait/`.
4. Voice style guide: banned phrases, preferred phrases, sentence-length
   targets, paragraph-length targets, demo-to-prose ratio.
5. Hero demo recommendation. Pick exactly one of the existing pain-point
   demo directories (`examples/pain-point-demos/01-blast-radius` through
   `10-prompt-search`) and justify why it is the strongest first-impression
   demo for power users.
6. Three "would not say" lines — claims that current copy makes but the
   product cannot yet defend with evidence.

**Approval gate:** User reviews `docs/ait-power-user-narrative-2026.md`. No
Phase 2 work begins until explicit go signal.

## Phase 2 — Four surfaces in parallel (after Phase 1 approval)

All four tracks dispatched concurrently. Every track must read and quote from
the Phase 1 positioning bible. All outputs land as `.draft` files; no original
content is overwritten.

### Track A — English README

- **Agents:** Content Creator + Technical Writer (joint dispatch, Content
  Creator leads, Technical Writer fact-checks every claim against `src/ait/`)
- **Output:** `README.md.draft`
- **Constraints:**
  - Top of file: hero block matches Phase 1 English one-liner exactly.
  - First fold (above the install snippet): no jargon, no acronyms beyond
    "AI agent" and "Git".
  - Keep the cross-agent session GIF and the work-graph PNG if they remain
    accurate; replace with placeholders otherwise.
  - All capability claims must be runnable today. If a feature is in
    `ait-intelligence-runtime-*` work-orders but not yet shipped, it does
    not appear in the README.

### Track B — Traditional Chinese README

- **Agent:** Content Creator (Chinese mode)
- **Output:** `README.zh-TW.md.draft`
- **Constraints:**
  - Not a translation of Track A. A native rewrite for 中文工程師.
  - Same factual surface as Track A; same hero claim; same demo references.
  - Use Traditional Chinese throughout; do not slip into Simplified.

### Track C — Docs site hero pages

- **Agents:** Technical Writer (lead) + Visual Storyteller (info architecture
  and demo selection)
- **Outputs:**
  - `site-docs/index.md.draft`
  - `site-docs/why-ait.md.draft`
  - `site-docs/getting-started.md.draft`
  - `site-docs/zh-TW/index.md.draft`
- **Constraints:**
  - Index page mirrors README hero but expands the differentiation table.
  - `why-ait.md` walks through the three Phase 1 pain points with a runnable
    demo link for each.
  - `getting-started.md` must be a five-minute path: install, wrap one agent,
    inspect the attempt, apply. No optional sections above the fold.
  - Chinese index follows Track B's voice, not Track A's.

### Track D — Social launch kit

- **Agents:** Growth Hacker (lead) + Twitter Engager + Reddit Community
  Builder
- **Output:** `docs/launch-kit-2026.md`
- **Contents:**
  - HN Show post: title (≤80 chars), body (≤2000 chars), top-comment author
    response template.
  - X / Twitter launch thread: 6–10 tweets, English, with demo embed slots.
  - Reddit r/ClaudeAI post draft.
  - Reddit r/LocalLLaMA post draft (lean into "no telemetry, no SaaS" angle).
  - Threads / X Chinese post.
- **Constraints:**
  - Every post quotes the Phase 1 hero line verbatim.
  - No post is published in this phase. Drafts only.

## Phase 3 — Quality gates (parallel after Phase 2)

Three parallel audits before any draft can be promoted to live.

| Agent | Task | Output |
|---|---|---|
| Reality Checker | Walk every capability claim in every Phase 2 draft. For each, name the file path in `src/ait/` or `examples/` that proves the claim. Flag every claim that lacks evidence. | `docs/ait-rebrand-qa-report.md` § Reality |
| UX Researcher | Read all four surfaces as a first-time power user. Time to comprehend the hero line. Time to identify the differentiator. Time to find the install command. Pain-point empathy check. | `docs/ait-rebrand-qa-report.md` § UX |
| Brand Guardian | Cross-surface consistency: hero line, pain points, voice, claim wording. Flag any drift between README, docs, and launch kit. | `docs/ait-rebrand-qa-report.md` § Brand |

User reviews `docs/ait-rebrand-qa-report.md`. Drafts are promoted to live
files only after all three audits pass and the user signs off.

## Deliverables

```
docs/superpowers/specs/2026-05-21-ait-rebrand-agent-dispatch-design.md
docs/ait-power-user-narrative-2026.md
README.md.draft
README.zh-TW.md.draft
site-docs/index.md.draft
site-docs/why-ait.md.draft
site-docs/getting-started.md.draft
site-docs/zh-TW/index.md.draft
docs/launch-kit-2026.md
docs/ait-rebrand-qa-report.md
```

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Agents invent capabilities AIT does not yet ship | Reality Checker phase, explicit "would not say" list in Phase 1 |
| Four tracks drift into four different voices | Single Phase 1 bible quoted by every Phase 2 dispatch |
| User reviews 8 drafts and loses track of what changed | Each draft committed as `.draft` next to its live file; diff is one command |
| Chinese surface becomes a literal translation | Track B has its own Content Creator dispatch with explicit non-translation rule |
| Launch posts go live before docs are ready | Track D outputs to `docs/launch-kit-2026.md` only; no posting tool is invoked |

## Out of scope (recorded for later)

- Theme redesign of the mkdocs site (`overrides/`, custom CSS).
- New diagrams, screen recordings, or GIFs beyond what already exists.
- Pricing, sponsorship, or commercial positioning.
- Translation into Simplified Chinese, Japanese, or Korean.
- Updating `CHANGELOG.md` (this is a marketing rebrand, not a release).
