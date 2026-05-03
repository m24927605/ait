# Reddit drafts

Three subreddits, three slightly different angles. Read each subreddit's
self-promotion rules before posting; some require flair or a comment-first
karma history.

---

## r/ClaudeAI

**Title:** I built a Git layer that runs Claude Code in isolated worktrees
with reviewable attempts

**Body:**

Hey r/ClaudeAI — I have been using Claude Code daily and kept hitting two
problems:

1. A single `claude` run can edit dozens of files. Mistakes are painful to
   undo cleanly.
2. The diff and the prompt that produced it drift apart in my memory after
   a few sessions.

So I built `ait` (https://github.com/m24927605/ait). It wraps `claude` (and
Codex / Aider / Gemini / Cursor) so each run happens in an isolated Git
worktree, with the prompt, status, edited files, and resulting commits
captured as one **attempt**. Your main checkout is untouched until you run
`ait attempt promote <id>`.

Quick install:

```
pipx install ait-vcs
cd your-repo
ait init
claude ...   # run as usual; ait wraps it
```

It is alpha and local-only — metadata lives in `.ait/` next to `.git/`.

Looking for early users who run a lot of Claude Code sessions and want a
cleaner provenance + review loop. Feedback welcome.

---

## r/LocalLLaMA

**Title:** ait — Git worktree isolation for local AI coding agents (Aider,
Codex CLI, Claude Code)

**Body:**

If you run local-first AI coding agents — Aider, Continue, Codex CLI,
Claude Code with bypass-permissions, etc. — `ait` adds a Git layer that
isolates each run in a worktree and records what happened.

Why r/LocalLLaMA might care:

- 100% local. No SaaS, no telemetry, no daemon. Metadata stays under
  `.ait/` in your repo.
- Dependency-free Python 3.14 + thin npm wrapper.
- Each agent session = one attempt. Review with normal Git tools.
- Memory layer keeps prior attempts and commits queryable for the next run.

GitHub: https://github.com/m24927605/ait

Alpha quality. Looking for feedback from people running local agents on
real repos.

---

## r/programming

**Title:** ait: a Git worktree layer that gives AI coding agents
reviewable provenance

**Body:**

Open source. AI agents (Claude Code, Codex, Aider, Gemini, Cursor) are
fast but produce diffs without useful provenance. `ait` wraps the agent
CLI, runs the work in an isolated Git worktree, and captures each run as
an attempt linking prompt, output, files, and commits.

You promote attempts you like; the rest stay available for inspection or
get discarded. Repo-local memory feeds future runs.

```
pipx install ait-vcs
cd your-repo
ait init
claude ...
```

Code: https://github.com/m24927605/ait
PyPI: https://pypi.org/project/ait-vcs/
