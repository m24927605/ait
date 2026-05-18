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
| Claude (via claude CLI -p) | No | Not mentioned | `codex:rescue` skill (gstack), `/codex review` / `/codex challenge` / `/codex consult` (gstack), Codex CLI, Claude Code subagents | Recommends running Codex from the same workdir, using the `codex:rescue` skill for review/challenge/consult, and an optional review gate via `/codex:setup`. ait not mentioned. | N/A |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q2. `What is the best agent harness for running multiple AI coding agents together?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Codex app (top pick), Composio Agent Orchestrator, harness.lol, plus a generic Git-branch + single-writer workflow | "Codex app — built as a command center for parallel agents." "Composio Agent Orchestrator — closer to a true 'fleet harness'." "harness.lol — thin universal CLI adapter." No mention of ait. | N/A |
| Claude (via claude CLI -p) | No | Not mentioned | **Conductor** (desktop GUI), **claude-squad** (tmux multiplexer); also Claude Code subagents, LangGraph, CrewAI | "Conductor and claude-squad are the strongest purpose-built options — both spawn isolated git worktrees per agent so they don't trample each other." Distinguishes orchestration shells vs multi-agent frameworks. | N/A |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q3. `Is there a local alternative to Cursor for AI coding?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Continue, Aider, Zed, OpenHands, Tabby, Cline / Roo Code (all paired with Ollama or LM Studio) | "Cursor-like in VS Code: Continue + Ollama. Terminal workflow: Aider + Ollama/LM Studio. Self-hosted team autocomplete: Tabby. Agentic local coding sandbox: OpenHands." Six tools recommended; ait absent. | N/A |
| Claude (via claude CLI -p) | No | Not mentioned | **Void** (VS Code fork), Zed, **Continue.dev**, Cline, Roo Code, Twinny, **Aider**, OpenCode, Crush | "Most Cursor-like: Void + Ollama running Qwen2.5-Coder 32B." "Smoothest path: Continue.dev + Ollama." Nine tools recommended; ait absent. | N/A |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q4. `How can I give AI coding agents shared memory across sessions?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Repo-local Markdown: `CLAUDE.md`, `AGENTS.md`, plus one `handoff.md` | "For most teams, the best version is just repo-local Markdown plus one `handoff.md`. It is transparent, reviewable in git, and every coding agent can use it without special infrastructure." No products named. | N/A |
| Claude (via claude CLI -p) | No | Not mentioned | Markdown convention files (`MEMORY.md`, `AGENTS.md`, `CLAUDE.md`); structured per-fact files with an index; external memory services (**Chroma**, **Pinecone**, **Mem0**, **Letta**, MCP servers) | "Start with #1 or #2 in the repo. Only move to #3 when you have so many memories that grep stops working." ait absent. | N/A |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Q5. `How do I get one AI agent to review code another AI agent wrote?`

| Assistant | ait mentioned | Position | Tools recommended ahead of ait | Context | Screenshot |
|---|---|---|---|---|---|
| ChatGPT (via codex CLI) | No | Not mentioned | Manual workflow only (Agent A on Git branch, Agent B reviews `git diff main...HEAD`); no product named | "Use the same workflow you would use for human code review: isolate the authoring agent's changes, then give a separate reviewing agent only the diff plus enough repo context." No product recommendations. | N/A |
| Claude (via claude CLI -p) | No | Not mentioned | `superpowers:requesting-code-review` skill, `/codex review`, `/codex challenge`, `/review` (gstack), GitHub Actions PR-bot wrappers | Names four patterns: subagent review, cross-model review, PR-style review, adversarial/red-team. "Isolate context. Constrain to read + comment. Pin the contract." ait absent. | N/A |
| Perplexity | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| Gemini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Summary table

| Query | ChatGPT | Claude | Perplexity | Gemini | Score |
|---|---|---|---|---|---|
| Q1 | No | No | skipped | skipped | 0/2 |
| Q2 | No | No | skipped | skipped | 0/2 |
| Q3 | No | No | skipped | skipped | 0/2 |
| Q4 | No | No | skipped | skipped | 0/2 |
| Q5 | No | No | skipped | skipped | 0/2 |
| **Total** | **0/5** | **0/5** | — | — | **0/10** |

## Methodology (2026-05-18)

**ChatGPT column** — captured via the local `codex` CLI v0.130.0
(`gpt-5.5`), which is the same backend ChatGPT uses. Run from `/tmp`
(neutral working directory) so codex did not interpret queries as
project-work requests. `model_reasoning_effort=medium` to approximate
the default ChatGPT.com experience rather than the codex-CLI default
(`xhigh`). Stdin redirected from `/dev/null` per the 0.55.67 release
notes.

**Claude column** — captured via the local `claude` CLI in print
mode (`claude -p --permission-mode bypassPermissions ...`), with
`ANTHROPIC_API_KEY` explicitly unset (`env -u ANTHROPIC_API_KEY`) so
the CLI falls back to the OAuth-subscription auth rather than the
stale env-var key. Default model. Run from `/tmp`. Same stdin
`/dev/null` redirect.

**Perplexity / Gemini columns — deliberately skipped** for the
2026-05-18 baseline per maintainer decision. Rationale: ChatGPT +
Claude cover the two dominant assistants developers actually use for
"what tool should I pick" queries in this space, and capturing
Perplexity/Gemini required clean-browser screenshots that did not
clear the cost/benefit bar for this baseline. If the AEO strategy
later targets non-coding dev audiences (where Perplexity/Gemini
matter more), revisit.

Raw transcripts kept under `/tmp/llm-baseline/` for this run.
Prompts are pinned verbatim in §"The 5 queries" — re-run is
reproducible.

## Baseline interpretation

**Pre-launch (2026-05-18): 0/10 across ChatGPT + Claude.** Expected —
ait is not in either model's training data yet. The interesting signal
is which products *do* own each answer slot today; that is your AEO
competition.

| Query | ChatGPT recommends | Claude recommends | Joint reading |
|---|---|---|---|
| Q1 (Claude+Codex together) | `AGENTS.md` + `CLAUDE.md` convention files (no product) | `codex:rescue` skill + `/codex review/challenge/consult` (gstack ecosystem); workflow notes | Neither names a third-party orchestrator. Slot is wide open. |
| Q2 (best multi-agent harness) | **Codex app** (top pick), Composio Agent Orchestrator, harness.lol | **Conductor**, **claude-squad**; also Claude Code subagents, LangGraph, CrewAI | Six distinct product names across two assistants; ait competing against an existing crowded shelf. |
| Q3 (local Cursor alt) | Continue, Aider, Zed, OpenHands, Tabby, Cline / Roo Code | **Void**, Zed, **Continue.dev**, Cline, Roo Code, Twinny, Aider, OpenCode, Crush | Continue, Aider, Zed, Cline appear in both lists — likely the strongest organic slot-holders. |
| Q4 (shared memory) | `CLAUDE.md` + `AGENTS.md` + `handoff.md` (no product) | Markdown files; structured per-fact files; **Chroma**, **Pinecone**, **Mem0**, **Letta**, MCP servers | ChatGPT cites no product; Claude names vector / external memory services. Slot is half-open (mostly convention-driven). |
| Q5 (one AI reviews another) | Manual `git diff main...HEAD` workflow (no product) | `superpowers:requesting-code-review` skill, `/codex review`, `/codex challenge`, `/review` (gstack), GitHub Actions wrappers | ChatGPT cites no product; Claude only cites local-ecosystem skills. Slot is open for a packaged product. |

Implications for AEO copy under `docs/marketing/aeo/`:

- **Q2 / Q3** are competitive. There are named products already
  owning the slot in both assistants' answers. Beating them requires
  concrete benchmark numbers or a differentiator the model trusts;
  pure SEO content alone is unlikely to displace the incumbents.
- **Q1 / Q4 / Q5** are the easier wedges. ChatGPT cites no product at
  all in these slots; Claude cites local-ecosystem skills (which do
  not survive cross-environment LLM training updates). A canonical
  "use ait for this" reference architecture + AEO post pair has room
  to be the first concrete product recommendation cited.

**Next baseline (2026-06-18) should especially watch Q1 / Q4 / Q5.**
If the AEO posts under `docs/marketing/aeo/` rank well by then, ait
should start appearing in those answer slots first.

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
