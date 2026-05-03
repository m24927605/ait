# Awesome-list submission prep

Each entry is a one-line markdown link with a tight description. Match the
sentence style each list already uses; check the contributing guide before
opening a PR.

## Target lists

| List | Section to add to | URL |
| --- | --- | --- |
| awesome-claude-code | Tooling / Workflow | https://github.com/hesreallyhim/awesome-claude-code |
| awesome-ai-coding | Tools / Workflow | https://github.com/jamesmurdza/awesome-ai-coding |
| awesome-cli-apps | Development / Git | https://github.com/agarrharr/awesome-cli-apps |
| awesome-codex (or fork) | Tooling | search GitHub |
| awesome-aider (community pages) | Tooling | search GitHub |

## Suggested entry text

### Generic (one line)

```markdown
- [ait](https://github.com/m24927605/ait) — Git worktree isolation and
  provenance for AI coding agents (Claude Code, Codex, Aider, Gemini,
  Cursor). Each run becomes a reviewable attempt; main checkout stays
  untouched until you promote.
```

### Claude-focused

```markdown
- [ait](https://github.com/m24927605/ait) — Wraps `claude` so every run
  edits an isolated Git worktree, captures prompt + files + commits as
  one attempt, and lets you promote, discard, or rebase with normal Git
  concepts.
```

### Aider-focused

```markdown
- [ait](https://github.com/m24927605/ait) — Runs Aider in an isolated
  Git worktree per session. Aider's commits land inside the attempt with
  full provenance back to the prompt and edited files.
```

## PR template

Title: `Add ait — Git worktree isolation for AI coding agents`

Body:
```
ait wraps Claude Code, Codex CLI, Aider, Gemini CLI, and Cursor so each
agent run edits an isolated Git worktree and is captured as a reviewable
attempt with prompt, status, files, and commits.

- Repo: https://github.com/m24927605/ait
- License: MIT
- Active maintenance: yes (alpha)

I confirm this entry follows the existing format and alphabetical order
of the section.
```
