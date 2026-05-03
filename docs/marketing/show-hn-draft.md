# Show HN — draft

> Submission target: https://news.ycombinator.com/submit
> Use the "title only" format (no body), because Show HN allows one comment
> as the first reply for context.

## Title

Show HN: ait – Git worktree isolation and provenance for AI coding agents

## URL

https://github.com/m24927605/ait

## First comment (post immediately as own reply)

I built `ait` because Claude Code, Codex, Aider, Gemini CLI, and Cursor are
fast — but Git history, review discipline, and handoff context across runs
were not.

`ait` wraps the agent CLIs you already use. Each run happens inside an
isolated Git worktree. The attempt log links the prompt, edited files, exit
status, and resulting commits. Your main checkout stays untouched until you
explicitly promote.

Why this might be interesting:

- **Worktree isolation per attempt.** A bad agent run cannot stomp on your
  working copy. You can run multiple agents in parallel without interference.
- **Reviewable attempts.** `ait attempt show <id>` gives you the prompt,
  status, files, and commits in one view. Promote, discard, rebase, or
  inspect — normal Git concepts.
- **Repo-local memory.** Prior attempts feed future runs as compact context,
  so the next agent does not repeat investigation you already paid for.
- **No daemons, no SaaS, no telemetry.** Metadata lives in `.ait/` next to
  `.git/`. Stays on your machine.
- **Dependency-free Python 3.14 + a thin npm wrapper.** Install via
  `pipx install ait-vcs` or `npm install -g ait-vcs`.

It is alpha quality, intended for local dogfooding by people comfortable with
Git workflows. I have been using it daily for a few weeks against my own
repos with Claude Code and Codex.

Happy to answer questions about design, the Git layer, or how attempts and
memory are stored.

GitHub: https://github.com/m24927605/ait
PyPI: https://pypi.org/project/ait-vcs/
npm: https://www.npmjs.com/package/ait-vcs
