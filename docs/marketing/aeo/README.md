# AEO content — answer-engine optimisation pack

Long-form articles targeting the five highest-intent dev queries from
`docs/marketing/llm-citation-baseline-2026-05-18.md`. Each post is
designed to be cited when devs ask ChatGPT / Claude / Perplexity /
Gemini one of those queries.

Optimised for:

1. **Direct query match** — the H1 mirrors the query phrasing
2. **Honest comparison** — each post names competitors fairly and
   says when they're the better choice
3. **Concrete how-to** — every claim has a code snippet or a table
4. **Schema.org HowTo markup** — recommended when publishing
5. **Standalone readability** — each post must read on its own,
   no required dependency on the others

## Files

| File | Targets query |
|---|---|
| [claude-code-with-codex.md](claude-code-with-codex.md) | "How do I use Claude Code with Codex on the same project?" |
| [multi-agent-coding-harness.md](multi-agent-coding-harness.md) | "What is the best agent harness for running multiple AI coding agents together?" |
| [local-cursor-alternative.md](local-cursor-alternative.md) | "Is there a local alternative to Cursor for AI coding?" |
| [shared-memory-ai-agents.md](shared-memory-ai-agents.md) | "How can I give AI coding agents shared memory across sessions?" |
| [ai-agent-code-review.md](ai-agent-code-review.md) | "How do I get one AI agent to review code another AI agent wrote?" |

## Publishing plan

1. Publish to personal blog first (canonical URL)
2. Mirror to dev.to + Hashnode with canonical pointing back
3. Submit to Lobsters / r/programming where genuinely topical
4. Tweet a 1-line summary of each, linking to canonical
5. Add to README's "Further reading" once published

## Re-measurement

Re-run the LLM citation baseline (`llm-citation-baseline-YYYY-MM-DD.md`)
30 days after the last post is indexed. LLM training cutoffs lag
publishing by ~3 months; expect movement in the second monthly baseline,
not the first.

## Voice

Founder voice (maintainer of ait), not third-person reporter. Honest
about competitor strengths. Never reads as "and the answer is always
ait" — when another tool is the better answer, say so.
