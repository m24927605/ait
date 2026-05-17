# Awesome-list submission prep

Each entry is a one-line markdown link with a tight description. Match the
sentence style each list already uses; check the contributing guide before
opening a PR.

PRs to awesome-lists are durable backlinks and a passive discovery channel.
They land low and slow, but they accumulate.

## Target lists

| List | Section to add to | URL |
| --- | --- | --- |
| awesome-claude-code | Tooling / Workflow | https://github.com/hesreallyhim/awesome-claude-code |
| awesome-ai-coding | Tools / Workflow | https://github.com/jamesmurdza/awesome-ai-coding |
| awesome-cli-apps | Development / Git | https://github.com/agarrharr/awesome-cli-apps |
| awesome-codex (or fork) | Tooling | search GitHub for the most-starred fork |
| awesome-aider (community pages) | Tooling | search GitHub |
| awesome-llm-tools | Multi-agent / Orchestration | search GitHub for the most-starred |
| awesome-agents | Local orchestration | search GitHub |
| awesome-devtools | AI / Code | search GitHub |

## Suggested entry text

### Generic (one line — preferred default)

```markdown
- [ait](https://github.com/m24927605/ait) — Local control plane for
  multi-agent AI coding. Run Claude Code, Codex, Aider, Gemini CLI, and
  Cursor as a team on the same task, with cross-agent context handoff
  and an adversarial review gate. No SaaS. MIT.
```

### Claude-focused (for awesome-claude-code)

```markdown
- [ait](https://github.com/m24927605/ait) — Lets `claude` hand context
  to Codex/Aider/Gemini and back, with a separate reviewer agent that
  can block the apply if it finds a critical issue. Isolated git
  worktree per attempt. 100% local. MIT.
```

### Aider-focused (for awesome-aider)

```markdown
- [ait](https://github.com/m24927605/ait) — Runs Aider as one agent in
  a local multi-agent loop. Aider implements; a separate reviewer agent
  (any supported model) reads the diff before apply and can block on
  critical findings. Attempt ledger and memory persist locally.
```

### Multi-agent / orchestration lists

```markdown
- [ait](https://github.com/m24927605/ait) — Local, MIT control plane
  for multi-agent coding. Cross-agent context handoff via
  `AIT_CONTEXT_FILE`, adversarial review gate, attempt ledger in
  SQLite. Adapters for Claude Code, Codex, Aider, Gemini CLI, Cursor.
```

### CLI-tool lists

```markdown
- [ait](https://github.com/m24927605/ait) — CLI that orchestrates
  Claude Code, Codex, Aider, and other AI coding agents as a local
  multi-agent loop. Reviewable attempts, review gate, repo-local
  memory. Python 3.14, zero deps.
```

## PR template

Title: `Add ait — local control plane for multi-agent AI coding`

Body:

```
ait is a local-first control plane that runs Claude Code, Codex CLI,
Aider, Gemini CLI, and Cursor as a team on the same task. Cross-agent
context handoff via AIT_CONTEXT_FILE, adversarial review gate that can
block apply on critical findings, attempt ledger and memory in SQLite
under .ait/ next to .git/.

- Repo: https://github.com/m24927605/ait
- License: MIT
- Active maintenance: yes (alpha)
- Install: `pipx install ait-vcs` (PyPI) or `npm install -g ait-vcs`

I confirm this entry follows the existing format and alphabetical order
of the section.
```

## Sequencing

1. Open PRs to the **top 3 most-starred lists** first (highest visibility,
   highest review standards — get those right before broadening)
2. Wait for one to merge before submitting to the rest (the merged PRs
   become social proof in the later PR descriptions)
3. Track open PRs in a single GitHub project; close the loop monthly
