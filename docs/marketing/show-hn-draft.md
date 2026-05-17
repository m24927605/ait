# Show HN — draft

> Submission target: https://news.ycombinator.com/submit
> Format: title + URL, then post the first comment immediately as own reply.
> **Publishing blocked until:** `ait demo` ships (Task #1). The first comment
> references it as the 30-second try. **Also:** capture a real review-caught bug
> from Task #2 before launch — comment threads will ask for one.

## Title

`Show HN: ait — Claude, Codex, and Aider as a team, on your laptop`

(64 chars — under the 80-char soft limit. Names competitor agents as allies,
not enemies. "On your laptop" signals local-first without saying SaaS.)

Alt titles for A/B if first doesn't take:

- `Show HN: ait — local control plane for multi-agent AI coding`
- `Show HN: ait — let one AI agent review what another wrote, locally`

## URL

`https://github.com/m24927605/ait`

## First comment (post immediately as own reply)

I built `ait` because the AI coding agents I use daily — Claude Code, Codex
CLI, Aider — are fast individually, but no tool lets me put two of them in
the same loop. You pick one. It runs. You hope it's right. That's not
multi-agent — that's single-agent with chat history.

`ait` is a local control plane that runs Claude Code, Codex, Aider, Gemini
CLI, and Cursor as a team on the same task. One agent investigates, hands
the context (what was tried, what failed) to a second agent via
`AIT_CONTEXT_FILE`, a third reviews what was written, and the review gate
can block the apply if it finds a critical issue. Everything runs on your
machine.

Why this might be interesting:

- **Multi-model, not multi-tool.** Different models catch different bugs.
  A reviewer agent with a different model and a different prompt catches
  what self-review misses. The reviewer can block the apply, not just
  comment.
- **Cross-agent context handoff.** When Claude finishes investigating,
  Codex picks up actual context, not a paste of the previous chat. Stops
  the "ramp-up cost twice" problem.
- **Local control plane.** No SaaS. No telemetry. Attempt ledger, review
  findings, and memory all live in `.ait/` next to `.git/` in your repo.
  Works offline. Your prompts and diffs never leave the machine.
- **Wraps agents you already use.** Adapters for Claude Code, Codex CLI,
  Aider, Gemini CLI, Cursor. Not yet-another-agent.
- **30-second try, no setup:** `pipx install ait-vcs && ait demo` runs a
  self-contained 60-second walkthrough with no API keys needed. Shows the
  full intent → multi-agent attempt → review-blocked-apply flow against a
  real SQLite ledger.

Alpha. Dogfooded daily on real repos with Claude Code and Codex for the
past several weeks. Python 3.14, zero runtime deps, MIT.

Happy to answer questions about the design, why local-first, how the review
gate works, how attempts and memory are stored, or why two agents with
different prompts catch things one agent with a longer prompt doesn't.

- GitHub: https://github.com/m24927605/ait
- PyPI: https://pypi.org/project/ait-vcs/
- npm: https://www.npmjs.com/package/ait-vcs

## Posting timing

Tuesday or Wednesday, 08:00–09:00 Pacific. Avoid Mondays (HN front page is
crowded with weekend backlog) and Fridays (attention drops after Thursday).

## Active hours after submission

Stay on-thread for the first 3–4 hours. Reply to every substantive comment
within 5 minutes. HN front-page placement weights early author activity
heavily; absence in the first hour is the most common reason a strong Show
HN doesn't take off.
