# KOL outreach — Big 5 + second tier

Customised one-to-one messages to a small number of influential developers
in the AI coding space. The strategy is not "ask for a retweet" — it is
**"ask for a brutally honest critique"**. Critique requests get engagement;
retweet requests get ignored.

## Sending rules

1. **Personalisation is non-negotiable.** Each opener references something
   specific the recipient has published recently. Templates that look
   recycled get archived in 3 seconds.
2. **Send via their preferred channel.** Some prefer email over X DM. Get
   this wrong and you signal you don't know them.
3. **Don't follow up more than once.** A second message after silence is a
   reasonable nudge. A third is spam.
4. **Send all 5 Big 5 within the same 48-hour window** — if one starts
   talking publicly, the others benefit from the social proof of being
   "next in line."
5. **Publishing prerequisite:** the manifesto must be live (i.e. Tasks #1
   and #2 done), or the link in the DM goes to a draft and erodes
   credibility. **Hold all DMs until then.**

## Replace before sending

- `[YOUR NAME]` — your actual first name
- `[YOUR LINK]` — your personal site or GitHub profile (optional but
  raises reply rate — gives them a way to check who you are in 5 seconds)
- `[MANIFESTO URL]` — once published, the canonical URL of the manifesto
  on your personal blog (not the draft path in the repo)

---

# Big 5

## 1. Simon Willison

- **Preferred channel:** email — `simon@simonwillison.net` (publicly
  listed on his site)
- **Alt channel:** Mastodon `@simon@fedi.simonwillison.net`
- **Avoid:** X DM (he is on X but does not prioritise DMs there)
- **Hook:** SQLite-first design, local-only, well-documented CLI. His
  `llm` tool stores state in SQLite — `ait` does the same thing for
  attempts.

**Subject line:** `ait — a Python CLI that runs Claude/Codex/Aider as a team, stores everything in SQLite`

**Body:**

```
Hi Simon,

Long-time reader of your weeknotes. Your work on `llm` and the way
you've written about Claude Code with hooks shaped how I thought about
what I ended up building: `ait`, a local control plane that runs
Claude Code, Codex CLI, Aider, Gemini CLI, and Cursor as a team on
the same task. One agent investigates, another implements, a third
reviews — and the review gate can block the apply if it finds a
critical issue.

Three things I think you'd notice:

1. Everything lives in SQLite under `.ait/` next to `.git/` —
   queryable, inspectable, no SaaS
2. Python 3.14, zero runtime dependencies, MIT
3. Wraps the agent CLIs you already use; no new agent

`pipx install ait-vcs` if you want to poke at it.

  GitHub:    https://github.com/m24927605/ait
  Manifesto: [MANIFESTO URL]

No expectation of a write-up. If you do find time, would love a
brutally honest take — especially on the SQLite schema and the choice
to skip vector storage entirely.

— [YOUR NAME]
[YOUR LINK]
```

---

## 2. Geoffrey Huntley

- **Preferred channel:** X DM (`@GeoffreyHuntley`) — DMs are open
- **Alt channel:** his blog has a contact form at https://ghuntley.com/
- **Hook:** He has written about multi-agent setups, agentic coding, and
  built his own harnesses. Acknowledge that lineage — don't pitch him
  like he's never seen this.

**Body:**

```
Hi Geoffrey,

Your posts on multi-agent coding loops over the past year shaped what
I ended up building. `ait` is a local control plane that orchestrates
Claude Code, Codex, Aider, Gemini CLI, and Cursor on the same task —
investigator → implementer → reviewer, with the reviewer able to
block the apply on critical findings. Cross-agent context handoff via
AIT_CONTEXT_FILE, attempt ledger in SQLite, MIT, no SaaS.

You've shipped your own version of this idea, so the most valuable
ask I have is your critique: what would you change about the model?

  pipx install ait-vcs && ait init
  https://github.com/m24927605/ait
  Manifesto: [MANIFESTO URL]

No expectation of promotion — want the honest read.

— [YOUR NAME]
```

---

## 3. swyx

- **Preferred channel:** X DM (`@swyx`) — open. Latent Space contact
  works too but slower.
- **Alt channel:** LinkedIn
- **Hook:** Latent Space podcast covers AI dev tool positioning
  regularly. swyx is good at taxonomy. Pitch him as a thinker, not just
  a promoter.

**Body:**

```
Hi swyx,

Long-time Latent Space listener — the conversations on dev tool
positioning are the most useful ones I've found anywhere. They got
me thinking about how to name what I built: `ait`, a local control
plane that runs Claude Code, Codex, Aider, Gemini CLI, and Cursor as
a team — handoff, review gate, attempt ledger, all on the machine.

I think there's a real category here that doesn't have a name yet:
"local AI coding control plane." Different from Conductor (cloud
orchestration), different from Aider (single agent), different from
LangGraph (cloud orchestration framework). Curious whether you see it
that way too, or whether I'm over-fitting.

If it fits Latent Space's lens at all, would love to talk. Otherwise
just want the taxonomy take.

  pipx install ait-vcs && ait init
  https://github.com/m24927605/ait
  Manifesto: [MANIFESTO URL]

— [YOUR NAME]
```

---

## 4. Mitchell Hashimoto

- **Preferred channel:** X DM (`@mitchellh`) — open but he is selective
- **Alt channel:** GitHub issues on https://github.com/m24927605/ait
  (he often interacts via repos rather than DMs)
- **Hook:** He cares about CLI craft, terminal-native, zero deps. Ghostty
  has the same aesthetic — fast, dependency-light, file-config. Pitch
  ergonomics, not features.

**Body:**

```
Hi Mitchell,

Built a CLI I think might match your taste: `ait`, a local control
plane for running multiple AI coding agents (Claude Code, Codex,
Aider, Gemini CLI, Cursor) as a team on the same task. Python 3.14,
**zero runtime dependencies**, MIT. State in SQLite under .ait/. No
SaaS, no telemetry, no daemon you didn't explicitly start. Works
offline.

It wraps the agent CLIs you already use rather than asking you to
install yet-another-agent.

  pipx install ait-vcs && ait init
  https://github.com/m24927605/ait

No pitch beyond that. If you ever poke at it, the kind of CLI
ergonomic feedback you give Ghostty would be gold.

— [YOUR NAME]
```

---

## 5. Theo (t3.gg)

- **Preferred channel:** X DM (`@t3dotgg`) — he does check
- **Alt channel:** YouTube channel "About" page contact, but slower
- **Hook:** Theo makes fast videos with strong takes. "Two agents
  adversarially reviewing each other" is video-shaped content. Make
  the work easy for him.

**Body:**

```
Hi Theo,

Built `ait` because I got tired of single-agent coding loops: Claude
alone, or Codex alone, but never together with a second model
challenging the first. `ait` runs Claude Code, Codex, Aider, Gemini
CLI, and Cursor as a team — one investigates, one implements, one
reviews, with the reviewer able to **block the apply** if it finds a
critical issue. All local. MIT.

I think the "two agents adversarially review each other in real time"
thing makes good video — show a bug Codex missed that Claude caught,
side by side. Happy to give you whatever pre-recorded footage or
scenario setups would help.

  pipx install ait-vcs && ait init
  https://github.com/m24927605/ait
  Manifesto: [MANIFESTO URL]

If it's not your thing, no worries.

— [YOUR NAME]
```

---

# Second tier — 5 candidates to research and customise

These are higher-effort because they need more customisation per person.
Templates below are starting points only. **Do not send the template
verbatim.** Read the person's recent 5 posts before personalising the
opener.

## 6. Paul Gauthier (Aider creator)

- **Channel:** GitHub issue or discussion on `paul-gauthier/aider`, or
  X DM `@paulgauthier`
- **Angle:** Aider is one of the agents ait wraps. Make the wrap
  concrete — show him the adapter file. Ask for integration feedback,
  not promotion.

```
Hi Paul,

Heads up — Aider is one of the agents `ait` wraps. ait is a local
multi-agent control plane: one agent investigates, hands context to
Aider to implement via AIT_CONTEXT_FILE, a reviewer agent reads the
diff and can block apply on critical findings. Aider's edit-locality
model is what makes it the right "implementer" role in the loop.

The adapter is small: src/ait/adapter_registry.py. Would love any
integration feedback if you have a moment.

  https://github.com/m24927605/ait

— [YOUR NAME]
```

## 7. Harrison Chase (LangChain)

- **Channel:** X DM `@hwchase17`
- **Angle:** LangGraph is the cloud-shaped version of multi-agent
  orchestration. ait is the local-shaped version. Same problem, different
  wedge. Frame it as adjacent, not competitive.

```
Hi Harrison,

Built a local-first version of what LangGraph does for multi-agent:
`ait`, a CLI control plane that runs Claude Code, Codex, Aider,
Gemini, Cursor as a team. Orchestration lives in SQLite under .ait/,
no cloud control plane. Different design constraints than LangGraph
but adjacent space — would value your perspective on whether the
local-first wedge holds.

  https://github.com/m24927605/ait

— [YOUR NAME]
```

## 8. Amjad Masad (Replit)

- **Channel:** X DM `@amasad`
- **Angle:** Replit Agent is the polished cloud version. ait is the
  local complement. Position as complementary, not competitive.

```
Hi Amjad,

Replit's agent UX is the polished cloud version of what I think can
also exist locally. Built `ait`, a local control plane for running
multiple AI coding agents (Claude Code, Codex, Aider, Gemini, Cursor)
as a team — investigator/implementer/reviewer loop, review gate that
can block apply, attempt ledger in SQLite. Different audience than
Replit, complementary direction.

Curious how you see the local-first niche from inside Replit.

  https://github.com/m24927605/ait

— [YOUR NAME]
```

## 9. Dex Horthy (HumanLayer)

- **Channel:** X DM `@dexhorthy`
- **Angle:** HumanLayer is "human in the loop" for agents. ait is
  "agent in the loop" for code review. Same gate pattern, different
  reviewer. Frame as complementary.

```
Hi Dex,

HumanLayer's "human in the loop for agents" is the right gate
pattern; `ait` is "agent in the loop for code review" — one agent
reviews what another wrote, with power to block apply. Local control
plane, runs Claude/Codex/Aider/Gemini/Cursor as a team. Adjacent
problem, different reviewer.

Curious how you think about the boundary between human gates and
agent gates.

  https://github.com/m24927605/ait

— [YOUR NAME]
```

## 10. Ben Kuhn (@benskuhn)

- **Channel:** email via his blog https://www.benkuhn.net/, or X DM
- **Angle:** He writes thoughtful pieces on AI engineering practice
  with strong empirical bent. Don't pitch features — pitch the
  underlying claim ("multi-model review beats single-model self-
  review") and let him decide if it's testable.

```
Hi Ben,

Your essays on AI engineering practice have been some of the most
careful empirical writing I've found in the space. I built `ait` on a
specific bet: that cross-model review (a different model with a
different prompt) catches things single-model self-review misses, and
that this matters more than people currently treat it as mattering.

ait is the infrastructure to test that — it runs Claude Code, Codex,
Aider, Gemini, Cursor as a team on the same task locally, with a
reviewer agent that can block apply.

Not asking for a writeup. Would love your take on whether the
underlying claim is testable in a way you'd respect.

  https://github.com/m24927605/ait

— [YOUR NAME]
```

---

# Send sequence

**Day 0 (manifesto live):**
1. Simon Willison — email
2. Geoffrey Huntley — X DM
3. swyx — X DM
4. Mitchell Hashimoto — X DM
5. Theo — X DM

(All 5 in one ~2-hour window.)

**Day 2:**
- If 2+ of Big 5 have replied positively, send second tier in same
  cadence
- If <2 replies, wait. Don't broaden when the top didn't bite — fix
  the message first

**Day 7:**
- One soft nudge to silent Big 5 recipients: "in case it got buried —
  no follow-up needed if not interesting"
- Never nudge twice

**Day 14:**
- Retrospective. Who replied, who didn't, what worked, what to change
  for the next launch wave.

# What to track

Per recipient: sent date, channel, reply (Y/N), reply sentiment, follow-up
action taken. A simple table at the bottom of this file is fine. Update as
you send.

| KOL | Channel | Sent | Reply | Notes |
| --- | --- | --- | --- | --- |
| Simon Willison | email | — | — | — |
| Geoffrey Huntley | X DM | — | — | — |
| swyx | X DM | — | — | — |
| Mitchell Hashimoto | X DM | — | — | — |
| Theo | X DM | — | — | — |
| Paul Gauthier | GH issue | — | — | — |
| Harrison Chase | X DM | — | — | — |
| Amjad Masad | X DM | — | — | — |
| Dex Horthy | X DM | — | — | — |
| Ben Kuhn | email | — | — | — |
