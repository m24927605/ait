# AIT Market Positioning Research

This note records the positioning work requested by
`docs/ait-market-positioning-goal.md` before editing README and website copy.

## Staff Team Discussion

### Product Marketing

AIT should not lead with "Git layer" or "workflow layer". Those labels are
accurate to the implementation, but they make the product feel like internal
plumbing. The first-time pain is sharper: AI agents are now powerful enough to
change real repositories, but the default interaction model still feels like
terminal scrollback plus a risky working tree.

The market narrative should make the user feel: "Claude and Codex can work on
my repo, but they should work in a controlled attempt before anything lands."

### DevRel

The demo moment is not "AIT uses worktrees." The demo moment is:

1. Run the agent normally.
2. AIT captures the run as an isolated attempt.
3. The root checkout is still clean.
4. The prompt, files, commits, memory, and review evidence are inspectable.
5. The user chooses what to apply.

That story is concrete enough for README, Show HN, and conference demos.

### Docs

The durable mental model should be `attempt`. Worktrees, commits, traces,
memory, review findings, and apply/recover all attach to that object. The docs
should teach that AI agent work belongs in attempts before it belongs in the
working tree.

### Growth

"Stop letting AI agents use your working tree as a scratchpad" is memorable,
but too slogan-like for the primary project definition. The strongest durable
positioning is:

> AI coding agents should work in attempts, not your working tree.

It is short, visual, developer-native, and points to AIT's product model.

### Security/Trust

Do not promise correctness. AIT provides isolation, provenance, local metadata,
review evidence, and explicit apply. It does not prove the generated code is
right. The copy must keep no SaaS/no telemetry/local `.ait/` visible.

### Open Source Maintainer

The positioning must be specific enough to survive issue threads and docs.
"Attempt" is project-native and inspectable in the CLI. It also differentiates
AIT from both SaaS observability tools and bare Git worktree scripts.

## AIT Solved Problems

- AI agents can modify a real repo too broadly before the user notices.
- Failed or partial runs can leave broken tests and half-finished files in the
  working tree.
- Prompt, intent, diff, commits, transcript evidence, and review evidence are
  hard to reconstruct from terminal history.
- Claude Code, Codex, Cursor, Aider, and Gemini do not share durable handoff
  context by default.
- Multiple agents trying the same task can overwrite each other in one checkout.
- Agent claims need review evidence and sometimes a gate before apply.
- Security-sensitive teams do not want source, prompt, or metadata shipped to a
  SaaS dashboard.

## AIT Capabilities

- Isolated attempts backed by Git worktree isolation.
- Root checkout stays untouched until explicit `ait apply`.
- Attempt provenance: prompt, intent, adapter, output, changed files, commits,
  trace references, status, and outcome.
- Shared repo-local memory across supported agents.
- Long-term memory from attempts, commits, notes, accepted facts, imported
  `CLAUDE.md` / `AGENTS.md`, and prior findings.
- Cross-agent handoff through local context rather than hidden chat state.
- Parallel attempts from multiple agents.
- Adversarial review and review-gated apply.
- Queryable prompt and attempt history.
- Local-first `.ait/` metadata, no telemetry, no SaaS dashboard required.

## Differentiators

- Not another coding agent: wraps existing CLIs.
- Not a Git replacement: uses Git, attempts, and explicit apply.
- Not only a worktree helper: adds provenance, memory, review, query, and
  recovery.
- Not SaaS observability: metadata is repo-local and inspectable.
- Not only review tooling: review is one part of the attempt lifecycle.

## Rejected Positioning

| Positioning | Why rejected |
| --- | --- |
| Git safety layer for AI coding agents | Accurate but too infra-like and too defensive. |
| Git workflow layer for AI coding agents | Generic; sounds like documentation for Git plumbing. |
| AI agents 的開發沙盒與交接系統 | More complete than "Git layer", but still abstract and not sharp enough. |
| Multi-agent control plane | Too enterprise and vague for first-time open-source visitors. |
| AI code review tool | Lets adversarial review overpower the broader product. |
| Local memory for AI agents | Undersells isolation, provenance, apply/recover, and review. |

## Candidate Positioning Scores

Scores are 1-5, higher is better.

| Candidate | Hook | Accuracy | Memory | Clarity | Launch | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| AI coding agents should work in attempts, not your working tree | 5 | 5 | 5 | 5 | 5 | Best balance: concrete, visual, and project-native. |
| Stop letting AI agents use your working tree as a scratchpad | 5 | 4 | 5 | 5 | 5 | Strong social hook; slightly more slogan than product definition. |
| Reviewable attempts for AI coding agents | 4 | 5 | 4 | 5 | 4 | Excellent short descriptor; less emotional. |
| Turn Claude/Codex runs into Git attempts you can inspect before apply | 4 | 5 | 4 | 5 | 4 | Very clear, but too long for hero headline. |
| Make every AI code run inspectable before it lands | 4 | 4 | 4 | 5 | 4 | Strong, but misses memory/handoff. |
| The local attempt ledger for AI coding agents | 3 | 4 | 4 | 3 | 3 | "Ledger" captures provenance but not apply/recover. |
| Isolated, remembered, reviewable AI code runs | 4 | 5 | 4 | 4 | 4 | Good secondary line; less ownable as primary. |
| The apply gate for AI-generated code | 4 | 3 | 4 | 4 | 4 | Too review/apply-centric; misses memory and parallel attempts. |
| A flight recorder for AI coding agents | 4 | 3 | 4 | 4 | 4 | Memorable metaphor but undersells isolation and apply. |
| Multi-agent coding without working-tree chaos | 4 | 4 | 4 | 4 | 4 | Good campaign line; less precise as product positioning. |
| Trust the attempt, not the chat scrollback | 5 | 4 | 5 | 4 | 5 | Strong secondary line; requires context. |

## Final Recommendation

Primary positioning:

> AI coding agents should work in attempts, not your working tree.

Traditional Chinese:

> AI agent 應該在 attempt 裡動手，不是直接碰你的 working tree。

Secondary lines:

1. Turn Claude Code, Codex, Aider, Gemini, and Cursor runs into isolated,
   reviewable attempts.
2. Keep prompts, diffs, commits, memory, and review evidence together until you
   explicitly apply.
3. Trust the attempt, not the chat scrollback.

Traditional Chinese secondary lines:

1. 把 Claude Code、Codex、Aider、Gemini、Cursor 的每次執行變成隔離、可審核的 attempt。
2. 在明確 apply 前，把 prompt、diff、commits、memory 與 review evidence 留在一起。
3. 不要只相信聊天紀錄；要能檢查 attempt。

## Why This Fits AIT

- "Attempts" is the product's real abstraction.
- "Working tree" names the concrete user anxiety.
- The line is stronger than "Git safety layer" without overclaiming.
- It leaves room for memory and adversarial review as reasons attempts are
  useful, not as competing main stories.
- It is accurate: AIT wraps existing agent CLIs, records attempts locally, and
  keeps the root checkout untouched until explicit apply.
