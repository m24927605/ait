# Multi-agent AI coding belongs on your laptop

> **Status:** draft for owner review. Founder voice. Edit freely.
> **Publishing blocked until:** `ait demo` ships (Task #1). The CTA promises a 60-second offline walkthrough that doesn't exist yet.
> **Open placeholders:** `[DOGFOOD-EVIDENCE]` — replace with the real bug-story captured by Task #2. Until then this article is unpublishable; abstract evidence reads like marketing fluff.
> **Tags:** ai, multi-agent, claudecode, codex, devtools, opensource
> **Target outlets:** personal blog, dev.to, Hashnode, optional Lobsters/Medium re-post

---

A few weeks ago, I shipped a patch to my own project using a workflow that wouldn't have been possible with any AI coding tool I used the year before.

[DOGFOOD-EVIDENCE]
> Replace this block with the real story from Task #2. Format reference:
>
> *Claude Code spent six minutes investigating a flaky test in our queue layer. It found the race window — two coroutines competing for the same lock — and handed the context to Codex. Codex wrote a fix using an `asyncio.Lock`. Then I asked Claude to read what Codex wrote, as a reviewer. The review flagged that the lock would deadlock if the wrapped function raised before releasing. Codex revised. Round two: clean. The patch landed in my repo. Total: 11 minutes. Three agent sessions, two different models, one local control plane.*

If you've used Claude Code or Codex or Aider on a real codebase, you know that workflow doesn't ship out of the box with any of them. You pick one. You run it. You hope it's good. That's not multi-agent — that's single-agent with chat history.

I think 2026 is the year that changes. And I think most teams will reach for cloud SaaS to do it, which is exactly the wrong call.

## The single-agent ceiling

Every AI coding workflow today centers on one model at a time. You boot Claude Code, or Cursor, or Aider, and you stay inside that agent's view of the world for the whole task. If the model is wrong about what "good" looks like, the agent is wrong. If the model has a blind spot — maybe it underweights memory safety, or it loves to write tests after the fact — the agent inherits it.

Prompting harder doesn't fix this. You're asking the same brain to check itself. The research on LLM self-evaluation keeps landing in the same place: a model is much weaker at finding its own mistakes than another model is at finding them. Cross-model review catches things self-review doesn't.

The honest description of single-agent AI coding is: it's a very fast junior engineer with one perspective. That's useful. It is not what you want shipping to your main branch unattended.

## What multi-agent buys you

Here is what changes when you let yourself use more than one model in the same loop:

**Diversification.** Claude's careful step-by-step reasoning compounds with Codex's pattern matching compounds with Aider's surgical edit discipline. They make different mistakes. When they agree, the answer is usually right. When they disagree, you've just discovered where the risk is.

**Adversarial review.** A second agent — different model, different prompt, different incentives — reads what the first one wrote and gets the power to block it. Not a comment. Not a suggestion. A blocker. The first agent has to address the finding before the code reaches your tree.

**Hand-off without re-learning.** When one agent finishes investigating, the next agent picks up the actual context — what was tried, what failed, what assumptions were ruled out. You stop paying the ramp-up cost twice.

**Specialization.** You stop asking the same agent to investigate, implement, test, and review. Each role gets the model best suited for it. That is how human engineering teams work. There is no good reason AI engineering should converge on a single omni-agent.

This is not theoretical. Multi-agent code generation papers keep getting better month over month. The interesting question is no longer "does multi-agent work." It is: *what infrastructure lets multi-agent work in practice, on a real codebase, today, with the agents you already use.*

## Why this can't live in someone else's cloud

The obvious move, if you are a founder selling AI dev tools in 2026, is to put the orchestration in your cloud. Serverless deployment. Web UI. SOC 2 logo on the homepage. That model is going to fail for technical teams. Three reasons.

**1. Your code is the IP you're trying to ship.** Sending every prompt, every diff, every retrieved snippet, every reviewer finding to a third-party SaaS — even one with the right paperwork — is a level of trust most engineering teams shouldn't extend lightly. The "we don't train on your data" clause doesn't address the basic question: where is the audit trail of which model saw what code, and who controls it. In cloud-orchestrated tools, the honest answer is "not you."

**2. Cloud control planes lock you into the vendor's choice of agents.** The whole point of multi-agent is model pluralism. The moment your orchestrator decides "we support Claude and our own model," you are back to single-vendor lock-in by a different name. Local control planes let you swap in whichever agents serve the task — including ones that don't exist yet.

**3. Latency adds up.** Every cross-agent handoff that round-trips through a SaaS adds seconds of network and queuing. That is fine for a chat tool. It is brutal for a 30-step workflow where each step needs context from the previous one. Local-first wins by an order of magnitude on tight feedback loops.

There is a fourth, less technical reason: planes, trains, offline coffee shops, air-gapped review environments, conference WiFi. All real situations where the SaaS option simply does not work and the local one does.

## What this actually takes (the boring infrastructure)

Multi-agent on your laptop is not a UX problem. It is an infrastructure problem. You need:

- A way to pass context between agents that isn't "paste the previous output." Each agent needs a structured handoff — what was decided, what was tried, what evidence was gathered.
- Isolation so one agent's mistakes don't corrupt another agent's view of the codebase. Git worktrees give this for free if you wrap them correctly.
- An audit ledger that records who did what, when, with which prompt, against which commit. SQLite is plenty for the local case.
- A review gate with the actual power to block, not just comment. With escalation policy: critical findings stop the apply, low findings get logged for visibility.
- Memory that persists across sessions, so the next agent on the same intent doesn't redo investigation you already paid for.
- Adapters for the AI coding agents you already use, not yet-another-tool to install.

None of this is glamorous. It is plumbing. It is also exactly the plumbing the current generation of AI coding tools doesn't ship.

## ait

That plumbing is what I have been building for the past few months. It's called `ait`. MIT, Python 3.14, zero runtime dependencies, no SaaS, no telemetry. It wraps Claude Code, Codex CLI, Aider, Gemini CLI, and Cursor — you keep your existing agents, you just give them shared infrastructure to work as a team.

A run looks like this:

```bash
pipx install ait-vcs
cd your-repo
ait init

ait demo                 # 60-second self-contained walkthrough, no API keys needed

ait run --adapter claude-code --intent "fix the flaky queue test"
# Claude investigates, writes a fix, ait spawns a reviewer agent,
# review gate decides if apply is allowed
```

Everything is real Git state. The attempt branch is a real branch you can `git log`. The reviewer's findings are a real row in a real SQLite database in `.ait/` next to `.git/`. There is no cloud. There is no daemon you did not start. There is no telemetry.

It is alpha. It has been dogfooded on real repos for several weeks. The pieces that work today — multi-agent attempt ledger, adversarial review gate, cross-agent context handoff, repo-local memory — work today.

## Where to start

If you only do one thing: `pipx install ait-vcs && ait demo`. The demo runs offline in 60 seconds and shows the full intent → attempt → review-caught-bug → apply-blocked flow with zero setup.

If you want the design and the source: https://github.com/m24927605/ait.

If you want to talk about it: open an issue, file a feature request, send me hate mail about the choice of Python 3.14. All welcome.

Multi-agent AI coding is going to happen in 2026 regardless of which tools win. The question is whether your team's control plane lives on your laptop, with your provenance, with your choice of agents — or in someone else's cloud, on their terms.

I know which one I want to ship on.

---

*If this resonated, the demo is one command away. If it didn't, I want to hear why — the comments are open, and so is the issue tracker.*
