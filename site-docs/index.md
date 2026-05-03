---
title: ait — Git worktree isolation for AI coding agents
description: >-
  ait wraps Claude Code, Codex, Aider, Gemini CLI, and Cursor in isolated Git
  worktrees with traceable commits, reviewable attempts, and repo-local memory.
---

# ait

**Git worktree isolation and provenance for AI coding agents.**

`ait` wraps the agent CLIs you already use — Claude Code, Codex, Aider,
Gemini CLI, Cursor — and turns each run into a **reviewable attempt**.
The agent edits an isolated Git worktree, `ait` records what happened,
and your main checkout stays untouched until you promote the result.

```bash
pipx install ait-vcs    # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

The package is named `ait-vcs` on PyPI and npm. The installed command is `ait`.

## Why ait

| Problem with agent coding | What ait adds |
| --- | --- |
| A prompt edits many files at once | Each run happens in an isolated Git worktree |
| The diff has no useful provenance | Attempts link intent, command output, files, and commits |
| Agents leave partial or failed work behind | Inspect, discard, rebase, or promote attempts |
| The next agent repeats old investigation | Repo-local memory summarizes prior attempts and commits |
| Tooling should stay local | Metadata lives in `.ait/` inside your repository |

`ait` is **not** another agent. It is the Git layer around the agents you
already trust.

## Supported agents

- [Claude Code](integrations/claude-code.md)
- [Codex CLI](integrations/codex.md)
- [Aider](integrations/aider.md)
- [Gemini CLI](integrations/gemini.md)
- [Cursor](integrations/cursor.md)
- [Any other shell agent](integrations/shell.md)

## Status

`ait` is alpha quality. It is intended for local dogfooding and early users
who are comfortable with Git workflows. Metadata is local to one repository
under `.ait/`; it is not synchronized across machines.

## Project links

- [GitHub repository](https://github.com/m24927605/ait)
- [PyPI package](https://pypi.org/project/ait-vcs/)
- [npm package](https://www.npmjs.com/package/ait-vcs)
- [Changelog](https://github.com/m24927605/ait/blob/main/CHANGELOG.md)
- [Issues](https://github.com/m24927605/ait/issues)
