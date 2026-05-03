# dev.to article draft

> Suggested title is keyword-dense for organic search. Pick one.

## Title options (most search-friendly first)

1. How to run Claude Code safely in a Git worktree
2. Git worktree isolation for AI coding agents (Claude Code, Codex, Aider)
3. Stop letting AI agents trash your working copy: a Git-native review loop

## Tags (dev.to allows up to 4)

`ai`, `claudecode`, `git`, `devtools`

## Cover image

Make a 1000x420 png with the words "ait — Git worktree isolation for AI
coding agents" on a black background. Save under `assets/cover.png` and
link in the article.

## Body

Most teams using Claude Code, Codex CLI, or Aider run them straight against
their working copy. That works until it doesn't:

- One bad prompt edits 30 files.
- The agent commits halfway and bails.
- You can't recall what prompt produced which diff three sessions later.
- Two agents stomp each other when you try to parallelize.

I wanted a thin Git-native layer that fixes those four problems without
introducing a SaaS, a daemon, or a new mental model. That's `ait`
(https://github.com/m24927605/ait).

### The model

`ait` wraps the agent CLI you already use. When you run `claude`, `codex`,
`aider`, `gemini`, or `cursor` inside an `ait`-initialized repo:

1. The agent gets its own **Git worktree**. Your root checkout is never
   touched.
2. Everything the agent does — prompt, exit status, edited files, commits
   — is captured as one **attempt**.
3. You **promote** attempts you like. The rest can be discarded, rebased,
   or kept for review.
4. A repo-local memory layer summarizes prior attempts so the next agent
   does not repeat investigation.

### Install and try

```bash
pipx install ait-vcs
cd your-repo
ait init
claude ...
ait status
ait attempt show <attempt-id>
ait attempt promote <attempt-id> --to main
```

There is also `npm install -g ait-vcs` for teams that prefer Node.

### What it is not

- Not a new agent. It does not write code itself.
- Not a Git replacement. Attempts produce real Git commits.
- Not a SaaS. Metadata lives in `.ait/` next to `.git/`.

### Where it goes next

Currently alpha. Tested daily against real repos with Claude Code and
Codex. Looking for feedback on the attempt model, the memory layer, and
which agent integrations should ship next.

GitHub: https://github.com/m24927605/ait
PyPI: https://pypi.org/project/ait-vcs/
npm: https://www.npmjs.com/package/ait-vcs
