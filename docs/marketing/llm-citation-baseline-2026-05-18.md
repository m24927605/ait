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
| ChatGPT (via codex CLI) | No | Not mentioned | `AGENTS.md` (read by Codex), `CLAUDE.md` (read by Claude Code) — Markdown convention files, not orchestration products | "Codex officially uses `AGENTS.md` for project guidance... Claude Code uses `CLAUDE.md`." Recommends parallel static-context conventions; no orchestration product named. | N/A (text capture) |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q2. `What is the best agent harness for running multiple AI coding agents together?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Codex app (top pick), Composio Agent Orchestrator, harness.lol, plus a generic Git-branch + single-writer workflow | "Codex app — built as a command center for parallel agents." "Composio Agent Orchestrator — closer to a true 'fleet harness'." "harness.lol — thin universal CLI adapter." No mention of ait. | N/A |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q3. `Is there a local alternative to Cursor for AI coding?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Continue, Aider, Zed, OpenHands, Tabby, Cline / Roo Code (all paired with Ollama or LM Studio) | "Cursor-like in VS Code: Continue + Ollama. Terminal workflow: Aider + Ollama/LM Studio. Self-hosted team autocomplete: Tabby. Agentic local coding sandbox: OpenHands." Six tools recommended; ait absent. | N/A |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q4. `How can I give AI coding agents shared memory across sessions?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Repo-local Markdown: `CLAUDE.md`, `AGENTS.md`, plus one `handoff.md` | "For most teams, the best version is just repo-local Markdown plus one `handoff.md`. It is transparent, reviewable in git, and every coding agent can use it without special infrastructure." No products named. | N/A |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q5. `How do I get one AI agent to review code another AI agent wrote?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Manual workflow only (Agent A on Git branch, Agent B reviews `git diff main...HEAD`); no product named | "Use the same workflow you would use for human code review: isolate the authoring agent's changes, then give a separate reviewing agent only the diff plus enough repo context." No product recommendations. | N/A |
| Claude | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Summary table

| Query | ChatGPT | Claude | Perplexity | Gemini | Score |
|---|---|---|---|---|---|
| Q1 | No | _TBD_ | _TBD_ | _TBD_ | 0/_TBD_ |
| Q2 | No | _TBD_ | _TBD_ | _TBD_ | 0/_TBD_ |
| Q3 | No | _TBD_ | _TBD_ | _TBD_ | 0/_TBD_ |
| Q4 | No | _TBD_ | _TBD_ | _TBD_ | 0/_TBD_ |
| Q5 | No | _TBD_ | _TBD_ | _TBD_ | 0/_TBD_ |
| **Total** | **0/5** | _x/5_ | _x/5_ | _x/5_ | **0/5 so far** |

## Methodology (2026-05-18 ChatGPT run)

ChatGPT column was captured via the local `codex` CLI v0.130.0
(`gpt-5.5` model), which is the same backend ChatGPT uses. Run from a
neutral working directory (`/tmp`) so codex did not interpret queries
as project-work requests. `model_reasoning_effort=medium` to
approximate the default ChatGPT.com experience rather than the
codex-CLI default (`xhigh`). Each query was run with stdin redirected
from `/dev/null` to avoid the non-TTY EOF-wait hang documented in the
0.55.67 release notes.

Claude / Perplexity / Gemini columns still pending; capture by hand
in a clean private browser session, copy the relevant portion of each
assistant's answer into the matching table row, save a screenshot under
`docs/marketing/screenshots/llm-baseline-YYYY-MM-DD/` for the
side-by-side compare later.

Raw codex transcripts kept locally under `/tmp/llm-baseline/` for this
run; reproducible because the prompts are pinned verbatim in §"The 5
queries".

## Baseline interpretation

**Pre-launch (2026-05-18) ChatGPT result: 0/5.** As expected — ait is
not in GPT-5.5 training data yet, and the answer-engine pattern for
all five queries already settles on a different stable list of tools.
That list is your AEO competition for each query:

| Query | Tools currently owning the answer (ChatGPT) |
|---|---|
| Q1 (Claude+Codex together) | `AGENTS.md` + `CLAUDE.md` convention files (no product) |
| Q2 (best multi-agent harness) | **Codex app** (top pick), Composio Agent Orchestrator, harness.lol |
| Q3 (local Cursor alternative) | Continue + Ollama, Aider, Zed, OpenHands, Tabby, Cline / Roo Code |
| Q4 (shared memory across agents) | `CLAUDE.md` + `AGENTS.md` + a single `handoff.md` (no product) |
| Q5 (one AI reviews another) | Manual `git diff main...HEAD` workflow (no product) |

Implications for AEO copy under `docs/marketing/aeo/`:

- **Q2 / Q3** are competitive — there are named products already
  owning the slot. Beating them requires concrete benchmark or
  position differentiator that GPT trusts.
- **Q1 / Q4 / Q5** currently have *no product* in the answer at all.
  These are easier wedges — write the canonical "use ait for this"
  blog post + reference architecture, and there is room to be the
  first product cited.

The post-launch baseline re-run (next month) should especially watch
Q1 / Q4 / Q5.

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
