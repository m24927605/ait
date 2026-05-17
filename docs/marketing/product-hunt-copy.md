# Product Hunt launch copy

Submit at: https://www.producthunt.com/posts/new

**Publishing blocked until:**
- `ait demo` ships (Task #1) — the maker comment references it
- The manifesto's dogfood evidence is captured (Task #2) — PH launches attract
  press and KOLs; "is anyone actually using this" is the first question. Both
  pieces of proof must be live before the post goes up
- Show HN is already 3–5 days past peak (`docs/marketing/README.md` ordering)

## Tagline (60 chars max)

`Multi-agent AI coding, on your laptop`

(38 chars — fits with room.)

Alt taglines for A/B comparison:

- `Claude, Codex, and Aider — as a team, locally` (46 chars)
- `Local control plane for multi-agent AI coding` (47 chars)

## Description (260 chars max)

```
ait is a local control plane for multi-agent AI coding. Claude
investigates, Codex implements, a reviewer agent blocks the apply if it
finds a critical bug — all on your machine. Wraps Claude Code, Codex,
Aider, Gemini CLI, Cursor. No SaaS. MIT.
```

(254 chars — confirm with `wc -c` before posting.)

## Topics

- Developer Tools
- Artificial Intelligence
- Open Source
- GitHub
- Productivity

## First comment (Maker comment)

Hi PH — I built `ait` because the AI coding agents I use daily (Claude
Code, Codex CLI, Aider) are fast individually, but no tool lets me put two
of them in the same loop. You pick one. It runs. You hope it is right.
That's not multi-agent — that's single-agent with chat history.

`ait` makes them work as a team:

- **Multi-agent flow.** One agent investigates, hands the context (what
  was tried, what failed) to a second agent via `AIT_CONTEXT_FILE`, a
  third agent reviews what was written, and the review gate can **block
  the apply** if it finds a critical issue. Cross-model review catches
  what self-review misses.
- **Local control plane.** No SaaS, no telemetry. Attempt ledger, review
  findings, and memory live in `.ait/` next to `.git/` in your repo.
  Works offline; nothing about your code leaves your machine.
- **Wraps the agents you already use.** Adapters for Claude Code, Codex
  CLI, Aider, Gemini CLI, Cursor. Bring your own model.
- **30-second try, no API keys:** `pipx install ait-vcs && ait demo` runs
  a self-contained 60-second walkthrough that shows the full multi-agent
  + review-gate flow against a real SQLite ledger.

Python 3.14, zero runtime deps, MIT. Alpha — looking for feedback from
people who run agent sessions on real repos. Happy to answer anything
about the design, the choice to go local-first, or the roadmap.

## Gallery assets needed

- **1270x760 hero image** — terminal screenshot showing a multi-agent run:
  two distinct agent IDs in the attempt log, a review finding with severity,
  the apply gate decision. Use real ait output, not a mockup.
- **Short looping demo (≤30s, 1280x720, mp4)** — captured from `ait demo`.
  Same source as Task #3.
- **Logo (240x240 png, transparent background)** — reuse repo logo if it
  exists; otherwise commission one in the week before launch.
- **Optional second screenshot** — `ait query "review severity=critical"`
  output to show the queryable provenance angle.
