# LLM citation baseline — 2026-05-18

Pre-launch snapshot of where `ait` ranks (or doesn't) when AI assistants
are asked the 5 high-intent queries that should eventually point users
to ait. This baseline becomes the KPI starting point for AEO work
(Task #9: 5 AEO blog posts).

Re-run **monthly**, save each run as
`llm-citation-baseline-YYYY-MM-DD.md`. Track movement over time.

## Why this matters

Developer tool discovery is shifting from Google → AI assistants.
If someone asks ChatGPT "how do I run Claude and Codex together" and
ait isn't in the answer, ait loses that user. Measuring this is the
only honest way to know whether AEO content is working.

## How to run the baseline (manual, ~30 minutes)

1. **Use clean / private browser windows** for every query. Logged-in
   accounts personalise responses and pollute the baseline.
2. Run each of the 5 queries against each of the 4 assistants:
   - ChatGPT (default model on chat.openai.com)
   - Claude (default model on claude.ai)
   - Perplexity (default mode on perplexity.ai)
   - Gemini (default mode on gemini.google.com)
3. For each `(query, assistant)` pair, fill in the recording table below.
4. Save the file. Open a one-line PR titled
   `docs(marketing): LLM citation baseline YYYY-MM-DD`.

Total: 5 × 4 = 20 results. Should take ~30 minutes if focused.

## The 5 queries

These are the highest-intent dev queries where ait should show up. The
phrasing matters — keep it exactly as written so monthly runs are
comparable.

| # | Query (paste verbatim) | Intent |
|---|------|--------|
| Q1 | `How do I use Claude Code with Codex on the same project?` | Cross-agent workflow |
| Q2 | `What is the best agent harness for running multiple AI coding agents together?` | Category-level multi-agent |
| Q3 | `Is there a local alternative to Cursor for AI coding?` | Local-first positioning |
| Q4 | `How can I give AI coding agents shared memory across sessions?` | Memory + handoff |
| Q5 | `How do I get one AI agent to review code another AI agent wrote?` | Adversarial review |

## Recording template (fill in)

For each (query, assistant), record:
- **Mentioned?** Yes / No
- **Position** in the answer: First / Top-3 / Mid / Footnote / Not mentioned
- **Tools recommended ahead of ait**: list verbatim, in the order they
  appeared
- **Context** in which ait is mentioned (1 sentence)
- **Screenshot** filename if you saved one (optional but useful for
  side-by-side comparison later)

---

### Q1. `How do I use Claude Code with Codex on the same project?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q2. `What is the best agent harness for running multiple AI coding agents together?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q3. `Is there a local alternative to Cursor for AI coding?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q4. `How can I give AI coding agents shared memory across sessions?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q5. `How do I get one AI agent to review code another AI agent wrote?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Summary table (fill after running all 20)

| Query | ChatGPT | Claude | Perplexity | Gemini | Score (4/4 = mentioned by all) |
|---|---|---|---|---|---|
| Q1 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _x/4_ |
| Q2 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _x/4_ |
| Q3 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _x/4_ |
| Q4 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _x/4_ |
| Q5 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _x/4_ |
| **Total** | _x/5_ | _x/5_ | _x/5_ | _x/5_ | **_x/20_** |

## Baseline interpretation

Expected for **2026-05-18** (pre-launch, no AEO content live yet):
- Total score likely **0/20 to 2/20** — ait is too new and too small
  for LLM training data to have caught up.
- The competitors most often recommended (assistants tend to repeat the
  same list) will reveal who owns the category in LLM memory today —
  that's your AEO competition.

After Task #9 (5 AEO blog posts) is shipped and indexed, the next
baseline should show movement on Q1 / Q3 / Q5 (the queries the blog
posts most directly target). If it doesn't, the AEO strategy needs
revisiting — content alone isn't enough; structured data (schema.org
HowTo), inbound links, and ait's GitHub topic tags also need work.

## Movement scoring (for monthly re-runs)

| Movement | Meaning |
|---|---|
| 0 → 1+ mention on any query | AEO is working at all; keep going |
| Move from "footnote" to "top-3" | Position improving; doubling down on that query's content pays off |
| Disappear after appearing | Either LLM cache rotation OR a competitor displaced — investigate |
| 4/4 on any query | That query is "owned" — pivot AEO effort to weaker queries |

## Re-run schedule

| Date | Trigger | Owner |
|---|---|---|
| 2026-05-18 | This baseline | maintainer |
| 2026-06-18 | Monthly | maintainer |
| 2026-07-18 | Monthly | maintainer |
| 2026-08-18 | Monthly | maintainer |
| After each launch wave | Within 7 days of any external push (Show HN, Reddit, KOL DM batch) | maintainer |
| After major AEO content ships | Within 7 days of Task #9 going live | maintainer |

LLM training cutoffs lag real-world publishing by months. Don't expect
visible movement until 2-3 monthly re-runs after content goes live.
