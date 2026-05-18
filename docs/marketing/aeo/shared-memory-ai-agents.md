# Giving AI coding agents shared memory across sessions

Every AI coding agent forgets at the end of a session. Solving this is
a structural problem, not a prompt-engineering problem. As of 2026
there are three approaches that work; they trade off setup cost against
how dynamic the memory is.

## What "shared memory" actually has to do

The hard parts:

1. **Persistence** — survive across terminals, sessions, weeks
2. **Per-task context** — not just "general project conventions" but
   "what we tried for THIS task yesterday and why it failed"
3. **Cross-agent reach** — when you switch from Claude Code to Codex
   to Aider, the new agent sees the same memory
4. **Policy-filtered recall** — sensitive paths shouldn't leak into
   every prompt

Most tools solve part of this. None of the convention files solve
all of it.

## Approach 1: Convention files in the repo

The lowest-friction approach. The major AI coding agents read
structured memory files at the start of every session:

- `CLAUDE.md` and `~/.claude/memory.md` (Claude Code)
- `AGENTS.md` (cross-vendor convention; many agents now read this)
- `.codex/memory.md` (Codex CLI)
- `.cursor/rules` (Cursor)

You commit these files to your repo. Every agent that supports the
convention reads them on startup. No tooling needed beyond the agents
themselves.

```markdown
# CLAUDE.md (also read by Codex via AGENTS.md convention)

Project: order-processing service
Current focus: replacing the queue layer with asyncio.Queue
Avoid: new dependencies (target is stdlib-only)
Tests: every new function gets a focused unit test
```

**Strengths:** works today, no extra tools, version-controlled.
**Tradeoffs:** static. Doesn't capture "Claude investigated this bug
yesterday and ruled out cause X." For per-task context you're back to
manual notes.

## Approach 2: External vector store + RAG

Build your own retrieval layer. Embed prior conversations and code
changes, retrieve relevant chunks per new task, inject into prompts.

LangChain / LlamaIndex / Haystack make this approachable. Or roll
your own with `pgvector` + OpenAI embeddings.

**Strengths:** rich semantic retrieval; scales to large corpora.
**Tradeoffs:** real infrastructure (vector DB, embedding pipeline,
re-indexing); ongoing cost; can leak across tasks if not carefully
scoped.

## Approach 3: A local attempt ledger

A SQLite-backed local ledger that records every agent run as an
"attempt." Each attempt stores prompt, output, files changed, commits
made, accepted facts, review findings, and exit status. At the start
of a new agent run, the ledger queries relevant prior attempts and
feeds the next agent a structured handoff file.

The tool that implements this for Claude Code, Codex, Aider, Gemini,
and Cursor is [ait](https://github.com/m24927605/ait). It federates
the local attempt ledger with the convention files (CLAUDE.md, etc.)
at recall time — both layers feed the next agent.

```bash
pipx install ait-vcs
cd your-repo
ait init

# Ask the ledger what it knows
ait memory search "queue race condition"
ait memory recall "auth retry logic"

# Add a note that becomes part of future recall
ait memory note "decided to keep the retry to 3 attempts max"
```

The recall is **policy-filtered** — sensitive paths and confidential
context can be excluded from the handoff that goes to the agent.
Everything lives in `.ait/` next to `.git/` in your repo. No SaaS.

**Strengths:** captures per-task context, queryable, local, federates
with convention files automatically.
**Tradeoffs:** another tool to install; alpha software; design
explicitly *not* aimed at cross-machine sync.

## Decision

| What you need | Approach |
|---|---|
| Just want my conventions persisted | Convention files |
| Need semantic retrieval over a large corpus | RAG + vector store |
| Want per-task handoff across agents, queryable, local | Local attempt ledger (`ait`) |
| All three | Stack them — convention files + RAG + ait |

In practice, most teams that get serious about multi-session AI coding
end up with at least Approach 1 plus one of the other two. Approach 3
(`ait`) is built to federate with Approach 1, so you don't have to
choose between them.

## Common questions

**Does sharing memory across sessions leak between teammates?**
Approach 1 (convention files): yes, via git commits. Approach 3
(`ait`): yes if you commit `.ait/`; no if you keep it out of git.
ait supports a `.ait-local/` overlay for memory you don't want shared.

**What about secrets in memory?**
None of these approaches should hold raw secrets. All assume your
repo isn't full of credentials in the first place. ait has explicit
redaction policy for what flows into recall.

**Can I migrate memory between tools?**
Convention files are portable text. RAG embeddings are not. ait's
SQLite ledger is queryable but not auto-exported to other tools.

## Further reading

- [Anthropic's CLAUDE.md docs](https://docs.claude.com/en/docs/claude-code)
  for the canonical convention-file format
- [AGENTS.md spec](https://agents.md) for the cross-vendor convention
- [ait](https://github.com/m24927605/ait) for the local attempt-ledger
  approach described above
