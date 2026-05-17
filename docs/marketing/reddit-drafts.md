# Reddit drafts

Three subreddits, three angles, same product. Read each subreddit's rules
before posting; some require flair or karma history. Space posts at least
one day apart per subreddit and never paste identical bodies — Reddit
spam-flags it.

**Publishing blocked until:** `ait demo` ships (Task #1). The CTA references it.

---

## r/ClaudeAI

**Title:** Run Claude Code, Codex, and Aider as a team — locally, with a review gate

**Body:**

I have been using Claude Code daily and kept hitting the same wall: Claude
is fast, but it's the only agent in the loop. If Claude misses something —
a missing edge case, a deadlock condition, a brittle assumption — nothing
else catches it before the code lands.

So I built `ait` (https://github.com/m24927605/ait). It's a local control
plane that lets Claude Code work with Codex, Aider, Gemini CLI, and Cursor
on the same task. A typical flow:

1. Claude investigates a bug
2. The context (what was tried, what failed, what files matter) hands off
   to Codex via `AIT_CONTEXT_FILE` — no re-paste, no re-learn
3. Codex implements a fix in an isolated git worktree (your main checkout
   stays untouched)
4. A reviewer agent — same or different model — reads what was written
   and can **block the apply** if it finds a critical issue
5. You only see the diff if it survives all of that

Everything runs locally. No SaaS, no telemetry. The attempt ledger, review
findings, and memory live in `.ait/` next to `.git/` in your repo.

Quick try (no API keys needed):

```
pipx install ait-vcs
cd your-repo
ait init
ait demo          # 60-second self-contained walkthrough
```

It's alpha. Looking for early users who run a lot of Claude sessions and
want a way to bring a second pair of eyes into the loop before code hits
their tree. Feedback welcome — especially on which agent combinations you
would want to see supported next.

---

## r/LocalLLaMA

**Title:** ait — local-first control plane for multi-agent AI coding (Claude Code, Codex, Aider, Gemini, Cursor)

**Body:**

If you run AI coding agents on your own machine — Aider, Continue, Codex
CLI, Claude Code with bypass-permissions — `ait` is a thin local layer that
lets you run them as a team rather than one-at-a-time.

Why r/LocalLLaMA might care:

- **100% local.** No SaaS, no telemetry, no third-party orchestration.
  Attempt ledger, review findings, and memory all live in `.ait/` in your
  repo. Works offline; the control plane never reaches the network.
- **Multi-model by design.** Different agents have different strengths and
  different blind spots. ait lets one agent investigate, hand context to
  another to implement, and a third to review with the actual power to
  block the apply on critical findings.
- **Cross-agent context handoff.** Structured handoff via
  `AIT_CONTEXT_FILE`, not "paste the previous chat."
- **Wraps the agents you already use.** Adapters for Aider, Codex, Claude
  Code, Gemini CLI, Cursor. Bring your own model. The plumbing is the
  product.
- **Python 3.14, zero runtime deps, MIT.** Install via `pipx install
  ait-vcs` or `npm install -g ait-vcs`.

Quick try (no API keys needed):

```
pipx install ait-vcs && ait demo
```

`ait demo` is a 60-second self-contained walkthrough that runs offline and
shows the full multi-agent + review-gate flow against a real SQLite ledger.

GitHub: https://github.com/m24927605/ait

Alpha quality. Looking for feedback from people running local agents on
real codebases — especially on how the multi-agent handoff and review gate
hold up under your actual workflow.

---

## r/programming

**Title:** ait: local control plane for multi-agent AI coding — Claude + Codex + Aider work as a team

**Body:**

Open source. Today's single-agent AI coding tools (Claude Code, Codex,
Cursor, Aider) are fast individually, but none of them lets you put a
second agent in the loop — either to hand off context or to review what
the first agent wrote.

`ait` is the missing infrastructure. It wraps the agent CLIs you already
use, captures each run as a reviewable attempt with provenance, hands
context between agents via `AIT_CONTEXT_FILE`, and lets a separate reviewer
agent block the apply if it finds a critical issue. All local.

The boring bits:

- Each agent run gets an isolated git worktree (no working-copy stomping,
  no parallel-agent interference)
- Attempts are first-class: prompt, files, exit status, commits, all in
  SQLite under `.ait/`
- The review gate uses a separate agent with a different model and prompt
  — cross-model evaluation catches what self-evaluation misses
- Repo-local memory persists across sessions so the next agent on the
  same intent doesn't re-investigate

```
pipx install ait-vcs
cd your-repo
ait init
ait demo            # 60-second walkthrough, no API keys needed
```

Python 3.14, zero runtime deps, MIT. Alpha.

Code: https://github.com/m24927605/ait
