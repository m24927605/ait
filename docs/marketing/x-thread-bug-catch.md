# X (Twitter) thread — bug-catch story

A 6-tweet thread anchored on a real bug a reviewer agent caught that an
implementer agent missed. The thread is the X-shaped version of the
manifesto's hook story. Optimised for scroll-stop in tweet 1, retention
through tweet 4, and a sticky close in tweet 6.

**Publishing blocked until:**
- `ait demo` is shipped (commit 44c6351 — done) AND released to PyPI/npm
- Real dogfood bug story is captured (Task #2) — tweet 1 leans on the
  screenshot; without it the thread reads like marketing fluff

## Posting rules

- **Time:** Tuesday or Wednesday, 09:00–10:00 Pacific. Same window as
  the Show HN. Don't post on a Monday (weekend backlog drowns it) or
  Friday (attention drops after Thursday).
- **Cadence:** Post all 6 tweets in one continuous thread within ~60
  seconds. Don't drip them across hours.
- **Engagement:** Stay on the thread for the first 2 hours. Reply to
  every substantive question within 5 minutes. The X algorithm rewards
  author dwell-time on a thread heavily.
- **No KOL tags in the thread.** Tagging Big 5 KOLs en masse looks
  try-hard. Reach them via DM (`docs/marketing/kol-outreach.md`); if
  the thread is good, organic retweets carry it.
- **Cross-link from the Show HN comments** once both are live: a single
  "X thread with screenshots" link in the first hour of HN traffic.

## Variant strategy

Run the **primary variant** below first. If engagement (likes,
quote-RTs, reply quality) is below `1k impressions / 50 likes / 5
quote-RTs` in the first 6 hours, the thread is not landing — pull
back, do not boost. Revise the hook (Variant B in §"Variant B") and
re-post 2-3 days later.

---

# PRIMARY VARIANT — 6 tweets

## Tweet 1 — hook + screenshot

**Body (≤280 chars):**

```
Claude implemented a fix.
Codex reviewed what Claude wrote.
Codex caught a deadlock Claude missed.
Claude revised. Round two was clean.
11 minutes total, all on my laptop, no SaaS.

The diff + the review finding 👇
```

**Image (required):** Single composed PNG showing, side-by-side:
- LEFT: the implementer agent's original diff (with the bug)
- RIGHT: the reviewer agent's finding output (severity + message
  pointing at the buggy line)
- BOTTOM CAPTION: "captured live with `ait` — 2026-05-XX"

Source: the Task #2 dogfood case. **Do not post this thread without
the real screenshot.** A staged screenshot ages badly.

## Tweet 2 — the "why this matters" context

**Body:**

```
Single-agent coding tools (Cursor, Aider, just Claude alone) are
fast. But they're one model's view of the code.

If that model has a blind spot, the bug ships.

A second agent with a different model is structurally less likely
to share the blind spot.
```

(~265 chars)

No image. Pure text retention beat.

## Tweet 3 — the mechanics

**Body:**

```
The tool that did this is `ait`. Local control plane:

— one agent investigates
— one implements in an isolated git worktree
— a third reviews, with the power to block apply
— everything in .ait/ next to .git/

No SaaS. Wraps the agents you already use.
```

(~278 chars)

No image. Or optional: a 1-line architecture diagram. Skip if unsure.

## Tweet 4 — the 60-second try

**Body:**

```
Try the 60-second walkthrough (no API keys needed):

  pipx install ait-vcs
  ait demo

Runs implementer + reviewer end-to-end against a scripted task in a
tmp dir. Real SQLite ledger you can query afterwards. Shows the
review gate actually blocking a bug.
```

(~275 chars)

**Image (recommended):** the 60-second demo gif (Task #3). If the gif
isn't ready yet, replace this tweet with a still terminal screenshot
of `ait demo` output.

## Tweet 5 — links + license

**Body:**

```
Source: https://github.com/m24927605/ait

Why this should be local, not cloud:
[MANIFESTO URL]

MIT. Python 3.14. Zero runtime deps. Alpha.

If you build with AI agents and want a second pair of eyes in the
loop, this is the loop.
```

(~270 chars)

No image. Links must include https:// (no shortlinks — X auto-cards
clean URLs and shortlinks dilute the preview card).

## Tweet 6 — close

**Body:**

```
2026 is the year multi-agent coding goes mainstream.

The question isn't whether it happens.

It's whether your team's control plane runs on your laptop or in
someone else's cloud.

I built ait because I want it to be the laptop one.
```

(~265 chars)

No image. Sticky declarative close — quotable on its own. This is the
tweet most likely to be screenshotted and re-shared independently.

---

# VARIANT B — single-screen "before/after" hook (use if Primary fails)

Replace tweet 1 with:

```
Two AI agents on the same coding task.
One wrote a deadlock.
The other caught it before it touched my repo.

Single-agent tools can't do this. Multi-agent cloud tools want
your code in their database.

ait does this on your laptop. MIT.
```

Same image as Primary. Same tweets 2-6.

The Variant B hook is more declarative and less narrative; useful if
the story format isn't landing for the audience that day.

---

# Anti-patterns — things NOT to do

- **Don't tag Cursor / Aider / Continue / Claude Code accounts in
  the thread.** Either they engage and steal the conversation, or
  they don't and it looks needy. Reach those teams via DM instead.
- **Don't quote your own tweet later in the thread to "boost it."**
  X penalises self-quoting in the same thread.
- **Don't include `🚀` or `🔥` or "Just shipped:" prefixes.** Those
  signals get downranked by the dev audience that matters.
- **Don't write tweet 1 in the past 24 hours.** Polish, sit on it
  for a day, re-read. The hook tweet has 30x the leverage of the
  others; getting it slightly wrong loses the whole thread.
- **Don't reply to your own thread with "if you liked this, RT for
  reach."** Vendor culture; doesn't fit the dev audience.

---

# Pre-flight checklist

Before posting:

- [ ] `[DOGFOOD-EVIDENCE]` from Task #2 is captured and the
      screenshot is composed (left: diff, right: review finding)
- [ ] `[MANIFESTO URL]` in tweet 5 is a live URL on the personal
      blog (not the repo file path)
- [ ] `pipx install ait-vcs && ait demo` was tested on a clean
      machine the morning of the post — make sure the demo still
      works in the version that's live on PyPI right now
- [ ] All 6 tweets fit under 280 characters (Twitter still rejects
      over-length tweets even in the thread composer)
- [ ] Images compressed (≤ 4 MB per image) and have alt text
      describing the contents for accessibility
- [ ] Calendar block reserved for engagement: 2 hours after post,
      no other meetings
- [ ] Show HN post (`show-hn-draft.md`) is queued for the same day
      or 24 hours prior, so the cross-link in HN comments can point
      to a live thread

---

# After posting — measurement window

Capture at +6 hours, +24 hours, +7 days:

| Metric | +6h | +24h | +7d |
|---|---|---|---|
| Impressions | _TBD_ | _TBD_ | _TBD_ |
| Likes | _TBD_ | _TBD_ | _TBD_ |
| Quote-RTs | _TBD_ | _TBD_ | _TBD_ |
| Replies (substantive) | _TBD_ | _TBD_ | _TBD_ |
| New GitHub stars (net of baseline) | _TBD_ | _TBD_ | _TBD_ |
| `ait demo` runs reported in replies | _TBD_ | _TBD_ | _TBD_ |

If +6h numbers are below the abort threshold in "Variant strategy",
pull engagement back and reset for Variant B in 2-3 days. If +24h
shows traction, push the same content to LinkedIn (different network,
same audience) and to Mastodon (FOSS/Linux crowd that cares about
local-first).
