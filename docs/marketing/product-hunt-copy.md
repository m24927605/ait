# Product Hunt launch copy

Submit at: https://www.producthunt.com/posts/new

## Tagline (60 chars max)

`Git worktree isolation for AI coding agents`

(57 chars — fits.)

Alt: `Reviewable attempts for Claude Code, Codex, Aider, Gemini`

## Description (260 chars max)

```
ait wraps Claude Code, Codex, Aider, Gemini CLI, and Cursor so every agent
run edits an isolated Git worktree. Each session becomes a reviewable
attempt — prompt, files, status, commits, all linked. Promote what works,
discard what doesn't. Local-first, MIT.
```

(Count to confirm before posting.)

## Topics

- Developer Tools
- Open Source
- Artificial Intelligence
- GitHub
- Productivity

## First comment (Maker comment)

Hi PH — I built `ait` because the AI coding agents I use daily (Claude
Code, Codex CLI, Aider) are fast but produce diffs without useful
provenance, and a bad prompt can rewrite half my repo before I notice.

`ait` is a Git-native layer:

- Each agent run gets an isolated Git worktree.
- The attempt captures prompt, output, files, and commits.
- You promote, discard, or rebase with normal Git concepts.
- Repo-local memory feeds future runs.

100% local. No SaaS, no telemetry. Install via `pipx install ait-vcs` or
`npm install -g ait-vcs`. MIT licensed.

It is alpha — looking for feedback from people who run a lot of agent
sessions on real repos. Happy to answer anything about the design or the
roadmap.

## Gallery assets needed

- 1270x760 hero image showing `ait status` + `ait attempt show` output.
- Short looping demo (≤ 30s, 1280x720, mp4) of `claude ...` → `ait
  attempt promote`.
- Logo (240x240 png with transparent background).
