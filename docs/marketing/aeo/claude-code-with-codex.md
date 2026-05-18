# How to use Claude Code with Codex on the same project

You can run Claude Code (Anthropic's CLI) and Codex CLI (OpenAI's) on the
same repo. The interesting question is how to make them work *together*
on the same coding task — not just side by side in two terminals. As of
2026 there are three workable approaches; the right one depends on
whether you care about provenance and review gates.

## TL;DR

| Approach | Setup | Cross-agent context | Audit trail | Review gate | Best for |
|---|---|---|---|---|---|
| 1. Alternate manually | 0 min | Manual paste | None | None | One-off tasks |
| 2. Shared memory files | 5 min | Static (commits to git) | Partial | None | Stable team conventions |
| 3. A local control plane | 5 min | Structured handoff | Full (SQLite + git) | Yes | Iterative multi-agent work |

## Approach 1: Alternate manually in two terminals

The zero-tool version. Open two terminals; run `claude` in one and
`codex` in the other. Copy/paste context between them when handing off.

```bash
# Terminal A
claude
> investigate the flaky queue test, find the root cause

# Terminal B (paste Claude's analysis as Codex's input)
codex
> here is what Claude found: [paste]
> implement the fix
```

This works for small one-shot tasks. It falls apart on iterative work:
by round three you've forgotten which prompt produced which diff, and
neither agent has a shared view of what's already been tried.

## Approach 2: Shared agent memory files

Both Claude Code and Codex CLI read structured memory files at the start
of every session:

- Claude Code: `CLAUDE.md` and `~/.claude/memory.md`
- Codex CLI: `.codex/memory.md` and `AGENTS.md` (the cross-vendor convention)

Write your project's conventions, current focus, and decisions into
these files once. Both agents pick up the same context on their next
run.

```markdown
# CLAUDE.md (also read by Codex via AGENTS.md convention)

Current focus: replacing the queue layer with asyncio.Queue.
Avoid: introducing new dependencies; the goal is stdlib-only.
Test discipline: every new function gets a focused unit test.
```

This is a real improvement over Approach 1, especially for teams. The
limit is that the files are *static* — they don't capture "Claude
investigated this specific bug and ruled out cause X today." For task-
level handoff you're back to copy-paste.

## Approach 3: A local control plane

The third approach puts a thin orchestrator between you and the agents.
The orchestrator:

- Records each agent run as a structured "attempt" (prompt, output,
  files changed, commits, exit code)
- Writes a structured handoff file (`AIT_CONTEXT_FILE`) summarising
  the previous attempt
- Lets the next agent read that file at startup
- Logs everything to a local SQLite ledger you can query

The tool that does this for Claude Code + Codex CLI + Aider + Gemini
+ Cursor is [ait](https://github.com/m24927605/ait). It is MIT,
Python 3.14, zero runtime dependencies, no SaaS:

```bash
pipx install ait-vcs
cd your-repo
ait init

# Claude investigates
ait run --adapter claude-code --intent "investigate flaky queue test"

# Codex picks up the structured handoff Claude left behind
ait run --adapter codex --intent "fix what Claude found"

# Query the ledger
ait query "attempt intent_id=<id>"
```

The handoff is structured (not "paste the previous chat"). It contains
accepted facts, decisions made, paths ruled out, and review findings —
filtered by policy so you don't leak everything into every prompt.

## When to pick which

- **Solo, one-shot tasks** → Approach 1.
- **Team with stable conventions** → Approach 2 (the memory files).
- **Iterative work, multiple agents per task, want an audit trail** →
  Approach 3.

You can also stack them: Approach 2 (convention files) is the static
baseline; Approach 3 (`ait`) federates the convention files into the
per-task handoff. Many teams end up with both.

## Further reading

- [Aider](https://aider.chat) — single-agent local CLI, complementary
- [LangGraph](https://www.langchain.com/langgraph) — cloud-shaped
  framework for custom multi-agent workflows
- [ait](https://github.com/m24927605/ait) — local-first multi-agent
  control plane (the Approach 3 tool described above)
