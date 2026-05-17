# Show HN response bank — 30 pre-drafted answers

Use during the first 4 hours after the Show HN goes live. HN front-page
placement weights early author activity heavily; missing the first hour is
the most common reason a strong Show HN doesn't take off.

## How to use

- Pre-load this file in a tab on launch day.
- For each comment, find the closest match below; lightly customise to the
  specific phrasing the commenter used; reply within 5 minutes.
- If a question isn't covered, draft a reply fresh — better silence than
  using a near-match that misses the point.
- Stay in the thread for the full 4 hours minimum. Set a timer.
- Voice: **first person, the maintainer's**. Honest about limitations.
  Confident about design choices. No marketing-speak.

## Anti-patterns to avoid in real-time

- Don't argue. Acknowledge the point, state your view, move on.
- Don't promise features mid-thread. "Filed as an issue" is the answer.
- Don't dunk on competitors. Position by design choice, not by attack.
- Don't disclose anything about model pricing/costs you don't have data for.
- If you don't know — say so. Honest "I haven't tested that" beats made-up
  numbers, which someone will catch.

---

# Q&A — 30 pre-drafted answers

## Category 1 — "Why does this exist?"

### Q1. Isn't this just Cursor / Continue / Aider with extra steps?

Each of those is a single-agent tool — you pick one model and stay inside
its view of the codebase. ait is a control plane that lets multiple of
them work as a team on the same task: one investigates, another
implements, a third reviews. The reviewer can block the apply on critical
findings. None of the tools you named do that today.

### Q2. Why not use Conductor / Sketch.dev / OpenHands?

Those are cloud-orchestrated. Your code, prompts, and provenance go to a
third party. ait is local — everything sits in `.ait/` next to `.git/`.
Different tradeoff: ait gives up the polished web UI; you keep the IP
boundary. Some teams want one, some want the other.

### Q3. Why local instead of cloud?

Three reasons. (1) Your code is the IP you're trying to ship; sending
every prompt and diff through a SaaS is a level of trust most engineering
teams shouldn't extend by default. (2) Cloud orchestrators lock you into
the vendor's choice of agents — local control plane lets you swap freely.
(3) Latency: every cross-agent handoff that round-trips through SaaS adds
seconds. Brutal in a 30-step workflow.

### Q4. What's wrong with one good model running a long context?

Cross-model evaluation catches what self-evaluation misses. Take any
non-trivial Claude output and ask Codex to review it as a skeptic — the
findings are different from Claude's own self-critique. Self-critique
is real but bounded by the same blind spots that produced the output.
Cross-model is structurally less prone to that.

### Q5. Isn't multi-agent just an excuse to burn tokens?

Sometimes. The honest framing: you spend roughly 2-3x the tokens of a
single-agent run, but you cut the rate at which broken code reaches your
tree by a much larger factor. Pays off when the cost of a bad merge
(debug + revert + customer impact) is much higher than a few extra model
calls. For trivial fixes, single-agent is still right.

---

## Category 2 — "How does it actually work?"

### Q6. How is the review different from Claude's own self-critique?

Different model, different prompt, different incentives. Self-critique by
the same model tends to rubber-stamp because the implementation already
passed the model's internal "is this good" check. A reviewer agent is
briefed as a skeptic; no investment in defending the implementation. In
practice catches a meaningfully different set of issues.

### Q7. How is context handed off between agents?

Via `AIT_CONTEXT_FILE` — a structured handoff containing relevant prior
attempts, accepted facts, decisions, and review findings (filtered by
policy). The next agent reads this file at startup. Not "paste the last
chat" — structured, queryable, reproducible. The schema is in
`src/ait/runner_context.py`.

### Q8. What if the review gate is wrong (false positive blocks apply)?

The block holds the attempt; it doesn't destroy it. You can inspect the
finding, override the gate (`ait apply` has flags for that), or send the
attempt back to the implementer for revision. The honest tradeoff:
tighter gate means more friction, looser gate means more bad code slips
through. The default is opinionated; tune to your team.

### Q9. How does cost compare to single-agent?

Roughly 2-3x model spend per task if all agents are paid models. Local
control plane itself is free (no SaaS subscription). For teams where the
bottleneck is "agent shipped bad code that took 2 hours to debug,"
multi-agent spend pays back fast. For trivial cases, it doesn't — and
ait lets you skip the review gate when you want.

### Q10. What about latency?

Agents run sequentially in the current design. Total wall-clock is the
sum of agent times. A task single-agent takes 30s might take 90s in
multi-agent. Faster than human PR review by ~100x; slower than
single-agent by 3x. Tunable per workflow.

### Q11. How does it integrate with CI/CD?

Today: it doesn't, directly. ait is a local-first tool. Natural pattern:
run ait locally for in-loop quality, push to CI as you do now. Adding a
"review gate" step in CI is a separate idea worth exploring; not what
ait does today.

### Q12. Does it work with offline LLMs (Ollama, LM Studio, llama.cpp)?

It can. The `shell` adapter accepts any command, including local-model
wrappers. No dedicated Ollama adapter today; ~30 lines if anyone needs
one. PR welcome.

### Q13. What's the SQLite schema?

Eight migrations covering intents, attempts, events, reviews, memory,
and review findings with proper foreign keys. Schema is in
`src/ait/db/schema.py`. Stable enough that you can query it directly with
`sqlite3` CLI; the `ait query` DSL is a convenience layer.

### Q14. How are attempts isolated?

Each attempt gets its own git worktree under `.ait/workspaces/<n>-<id>/`.
Real git worktree — you can `cd` into it and run git commands as normal.
Apply moves the attempt's commit onto your main checkout via git merge /
cherry-pick.

### Q15. Who picks the implementer vs reviewer model?

You do — no automatic routing today. Config pins specific adapters to
specific roles. Default review uses a fake reviewer (for the demo) or
whatever you configure. Smarter routing based on task type is a future
direction, not a current claim.

---

## Category 3 — Trust & honesty

### Q16. It's alpha. What does that actually mean?

Schema may break (with migrations). API may change. Documentation lags
features. Specific known limitations: no multi-machine sync, no semantic
merge, agent-to-agent review is asynchronous per attempt (not within a
single run). Daily dogfooded by me on real repos. No production users
yet that I know of.

### Q17. What benchmarks do you have?

None published yet, intentionally. I don't trust my own benchmarks of my
own tool. Waiting for outside users to run real comparisons. If anyone
in this thread wants to do a SWE-bench-style comparison, I'll help set
it up.

### Q18. What's broken right now?

Off the top of my head: (1) memory recall can be slow on repos with
>10k attempts, (2) daemon doesn't recover gracefully from `kill -9`,
(3) Cursor adapter is the least-tested of the five, (4) no Windows
support — Linux/macOS only. Issues tracker has more.

### Q19. Why Python 3.14? That alienates users on older Pythons.

Fair point. I use 3.14-only features in a few places (`tomllib`, type
syntax improvements). For most users, `pipx install ait-vcs` handles
this automatically via a managed Python — they don't notice. If you
want me to drop the requirement to 3.11, file an issue with what you're
trying to do. Not philosophically attached.

### Q20. Why no telemetry, really?

I'd like to know which features people use. But "we don't train on your
data" doesn't address what I actually want addressed (control over the
audit trail), and telemetry erodes the local-first promise. Instead:
there's an explicit `ait export` for users who want to share usage data
with me; I rely on the issue tracker. Slower learning loop, honest
tradeoff.

---

## Category 4 — Comparison

### Q21. vs Conductor?

Conductor is hosted, ait is local. Conductor has the nicer UI today; ait
has more agent integrations and no SaaS lock-in. Different audiences —
Conductor for teams that want a managed multiplayer experience, ait for
individuals/teams that want everything on the laptop.

### Q22. vs Sketch.dev?

Sketch is one polished AI coding agent with an opinionated UI. ait wraps
Sketch alongside Claude/Codex/Aider/Cursor/Gemini and adds the review
gate. Complementary, not competitive — Sketch could be one of the
agents in an ait loop if there's demand for a Sketch adapter.

### Q23. vs OpenHands?

OpenHands is an agent (the actor). ait is the control plane (the
orchestrator). You could run OpenHands as one of ait's agents via the
shell adapter. Different layers of the stack.

### Q24. vs Claude Code's own worktrees?

Claude Code's worktrees are great but single-agent. ait gives Claude
Code worktrees AND lets a Codex/Aider reviewer challenge the work before
apply. That's the multi-agent + review-gate piece Claude Code doesn't
have on its own.

### Q25. vs Aider's commit-then-review flow?

Aider commits incrementally as it works; you review the commits after.
ait holds the commit on an attempt branch and lets a reviewer agent
challenge it BEFORE it reaches your main checkout. Different timing —
Aider is "ship fast, review after"; ait is "review first, then ship."

### Q26. vs GitHub Copilot Workspace?

Copilot Workspace is cloud-hosted, single-vendor (Microsoft/GitHub), and
assumes GitHub as the source of truth. ait is local, multi-vendor, works
on any git repo. Audience overlap is real but different centre of
gravity.

---

## Category 5 — Adoption

### Q27. Can I use just one agent (e.g., just Claude)?

Yes. The review gate is optional and can be disabled. With one agent,
ait still gives you the attempt ledger, worktree isolation, and memory.
It's overkill for that use case — you might prefer Claude Code directly.
The value compounds when you add a second agent.

### Q28. How do I migrate from Aider?

You don't have to. Aider is one of the supported agents.
`ait run --adapter aider --intent "your task" -- aider src/file.py`
wraps your existing Aider invocation. Your Aider config, your prompts,
your habits all keep working.

### Q29. Team usage — shared memory across teammates?

Memory lives in `.ait/` which can be committed to the repo, so yes —
git-mediated sharing. No live cross-teammate memory (that's a non-goal
in v1). For private notes that shouldn't be in git, ait supports a
`.ait-local/` overlay.

### Q30. License — commercial use? Enterprise? SOC2?

MIT, fully commercial-use permitted, no CLA. Provenance is there:
every diff tied to prompt, agent, model, and review record in SQLite —
the raw evidence an SOC2 audit needs. No formal compliance attestation
today; the tool gives you the data, your org gets the cert.

---

# Anti-FAQ — questions to NOT engage with

Some questions on HN are designed to provoke or derail. Acknowledge,
give a one-line response, do not get pulled in:

| Bait pattern | Suggested reply |
|---|---|
| "This is just LangGraph but worse" | "Different design constraint (local vs cloud); both can be right." Move on. Don't relitigate. |
| "Why didn't you use [niche framework X]?" | "Considered it; chose Y for [one reason]. PR welcome if you want X." Don't relitigate. |
| "You're going to fail because [generic startup death prediction]" | "Possibly! Time will tell." Don't engage further. |
| Vim vs emacs / Python vs Rust / MIT vs GPL | Don't engage. Not relevant to the post. |
| "What about [competitor that just launched]?" | If you haven't tried it, say so. Never pretend opinions on tools you haven't used. |
| "Why are you doing this when [bigger company] already exists?" | "Different design centre. Both can exist." Don't compare line-by-line. |

---

# One-line ready responses

| Question | Reply |
|---|---|
| Demo? | `pipx install ait-vcs && ait demo` |
| Source code? | https://github.com/m24927605/ait |
| Pricing? | Free, MIT, no SaaS tier planned. |
| Roadmap? | `docs/implementation-plan.md` in the repo. |
| Twitter/Mastodon? | No project account yet. |
| Discord? | No. GitHub issues. |
| Roadmap for [feature X]? | "Filed as issue #N if not already there. Bumping depends on demand." |
| Windows support? | "Not yet. Linux + macOS only. PR welcome." |
| Privacy? | "No telemetry, no SaaS. The control plane is your laptop." |
| Telemetry? | "None." |
| Self-hosted option? | "It is self-hosted by default — local-first. There is no hosted option." |
| How long have you been working on it? | "Few months full-time. Daily dogfooded on real repos." |
| Are you hiring? | "No. Solo project." |
| VC funding? | "Not seeking. Open source forever." |
| When v1.0? | "When dogfood feedback says it's ready. No date." |

---

# Closing the thread

After the first 4 hours of active engagement, post a single end-of-shift
comment so visitors know the author has stepped away (sets expectations,
doesn't leave silence):

> Stepping away for a few hours. Will keep reading and replying as
> questions come in — just slower. Thanks everyone who tried `ait demo`
> already; the feedback is going straight into the issue tracker.

Resume engagement next day. Don't disappear without a marker.
