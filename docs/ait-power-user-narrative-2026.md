# AIT Power-User Narrative 2026

**Audience.** Engineers running Claude Code, Codex CLI, Aider, Gemini CLI, or
Cursor. They have shipped agent diffs and been burned.

**Voice.** Linear / Vercel / Resend. Calm, demo-heavy, zero slogans.

**Status.** Bible. Every downstream surface quotes this file.

**v2 changelog.** v1 led with "attempts vs. working tree" — plumbing. v2 leads
with three outcomes: cross-agent handoff, a different reviewer, memory across
sessions. "Attempt" stays in body.

---

## 1. Hero line

### English candidates

1. **One agent writes. Another reviews. The repo remembers both.**
2. Hand work between Claude, Codex, and Aider on a repo that remembers.
3. Claude writes, Codex reviews, the repo keeps the receipts.
4. The next agent already read the last agent's notes and the reviewer's blocks.

**Winner: #1** — three sentences, one per pillar: multi-agent, review (no
banned "catches bugs"), memory. #2 docs index; #3 launch; #4 subhead seed.

**Subhead (≤20 words).** "Every agent run is an attempt under `.ait/` —
prompt, diff, review findings, prior decisions, queryable from the CLI."

### Traditional Chinese candidates

1. **一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來。**
2. Claude 寫、Codex 審，repo 幫你把兩邊的決定都留住。
3. 下一個 agent 已經讀過上一個 agent 的筆記和審查結果。
4. 多個 agent 在同一個 repo 工作，誰寫誰審 repo 都記得。

**Winner: #1** — 29 chars; "寫 / 審 / 記下來" carry all three pillars. #2 docs
index; #3 memory subhead; #4 launch.

**Subhead (≤30 chars).** "每一次 agent run 都是 `.ait/` 裡的 attempt：prompt、diff、審查結果、上一輪決定都查得到。"

---

## 2. Three power-user pain points

One pillar per pain, in order: multi-agent communication, adversarial review,
shared + long-term memory.

### Pain 1 — Every agent starts from zero on the same repo (pillar: multi-agent communication)

**Scenario.** Yesterday Claude chased a billing-retry 429 bug. This morning
Codex opens the same repo and re-investigates from scratch. Zero handoff.

**AIT defuses it.** Every wrapped run lands as an attempt under `.ait/`. The
next run — Codex, Aider, Gemini, Cursor, anything wrapped by `ait run
--adapter <name>` (`src/ait/cli/run.py`) — receives `AIT_CONTEXT_FILE`,
assembled from prior attempts and notes (`src/ait/context_manifest.py`).
Asynchronous, evidence-based: prompt, diff, findings, decisions. Trace
handoffs with `ait query --on attempt 'agent.agent_id="codex:main"'`.

**Proof.** [`examples/pain-point-demos/07-cross-agent-handoff/`](../examples/pain-point-demos/07-cross-agent-handoff/) — Codex inherits via `AIT_CONTEXT_FILE`.

### Pain 2 — The agent that wrote the code is the only one who reviewed it (pillar: adversarial review)

**Scenario.** Codex finishes, says "all tests pass." Implementer and reviewer
are the same model, same chat, same prompt.

**AIT defuses it.** `ait review attempt latest-reviewable --mode adversarial
--review-adapter claude-code` (`src/ait/cli/review.py`) runs a different
agent, different prompt, against the attempt's diff. The reviewer cannot see
the implementer's chat. Findings are queryable rows: `ait query --on attempt
'review.status="blocked"'`. High-severity findings hold `ait apply`.

**Proof.** [`examples/pain-point-demos/09-verification-evidence/`](../examples/pain-point-demos/09-verification-evidence/), [`examples/pain-point-demos/09-1-codex-reviewer/`](../examples/pain-point-demos/09-1-codex-reviewer/) — separate reviewer blocks before apply.

### Pain 3 — Last Tuesday's decision lives in a closed chat tab (pillar: shared + long-term memory)

**Scenario.** Three weeks ago you capped the retry budget at three. The chat
tab is closed. The new agent proposes five.

**AIT defuses it.** `.ait/` keeps every attempt — prompt, intent, output,
files, commits, findings — alongside live `CLAUDE.md` / `AGENTS.md` /
`.claude/memory.md` / `.codex/memory.md` / `.cursor/rules`. Recall is a CLI
query: `ait memory recall "retry budget"` (`src/ait/memory/recall.py`)
returns prior attempts, accepted facts, notes. Local, single-machine, shared
across every wrapped agent.

**Proof.** [`examples/pain-point-demos/04-memory-reuse/`](../examples/pain-point-demos/04-memory-reuse/) — prior decision reaches the next agent via `ait memory recall`.

---

## 3. Differentiation table

Every AIT capability cites a real CLI command or a real file under `src/ait/`.

| Tool | What it does | What AIT adds |
|---|---|---|
| **Aider** | In-process edit + auto-commit loop, single model, one chat per run. | A separate reviewer agent against the same attempt (`ait review attempt --mode adversarial`, `src/ait/cli/review.py`). Aider commits land *inside* an AIT attempt; apply is still explicit. Cross-agent handoff via `AIT_CONTEXT_FILE` (`src/ait/context_manifest.py`). |
| **Cursor** | IDE-integrated agent, in-editor diff review, agent-mode parallel tasks. | CLI-first attempt ledger across non-Cursor agents (`ait attempt list`, `src/ait/cli/attempt.py`). No SaaS round-trip; `.ait/` is local, daemon on Unix socket only (`src/ait/daemon_transport.py`). |
| **Cline** | VSCode extension wrapping Claude/OpenAI for in-editor agentic edits. | Wraps the agent CLI you already use, no editor required (`ait run --adapter claude-code`, `src/ait/cli/run.py`). Findings and prompts are queryable rows (`ait query`, `src/ait/query.py`). |
| **Continue.dev** | IDE autocomplete and chat with model routing and rule files. | Reviewable attempts, not autocomplete (`ait apply` / `ait recover`). Review gate (`ait review finding list --severity high`). |

What AIT does **not** do, and downstream writers must not claim:

- No IDE plugin. CLI only.
- No autocomplete. Attempt-grained, not keystroke-grained.
- No cross-machine sync. `.ait/` is single-repo, single-machine.
- No published benchmark proving the reviewer catches bugs the implementer
  missed. Dogfood report exists; quality claim does not.

---

## 4. Voice style guide

### Banned phrases (with replacements)

| Banned | Use instead |
|---|---|
| "Git workflow layer" / "Git safety layer" | "Each agent run is a reviewable attempt." / "The root checkout never moves until you apply." |
| "Control plane" | "Local attempt ledger" or just "AIT". |
| "Sandbox" | "Isolated Git worktree". |
| "Unleash" / "supercharge" / "AI revolution" | A demo command. |
| "Federated memory" | "Prior attempts, notes, and live `CLAUDE.md` / `AGENTS.md` files." |
| "Adversarial review" *as the lead* | "The implementer doesn't review its own work." Adversarial review is OK in body. |
| "AIT_CONTEXT_FILE" *above the fold* | "The next agent receives the prior agent's decisions." |

### Preferred phrases

- Hero: "AI agents should commit to attempts, not your working tree."
- "Run Claude. Run Codex. Run them on the same task. Pick the diff you trust."
- "The reviewer is a different agent, with a different prompt. It can block apply."
- "Nothing leaves your machine."
- "`pipx install ait-vcs && ait init && claude ...` — that is the install."

### Length and rhythm

- **Sentence.** Avg 14 words. Hard cap 22. Period beats comma.
- **Paragraph.** Three sentences typical, four max. Above the fold, two.
- **Demo-to-prose ratio.** One code block or runnable demo link per ~80 words
  above the fold. Every claim has a proof.
- **Emoji.** None, unless quoting an existing artifact verbatim.

### Tone references

1. **linear.app** — homepage. Short declarative sentences, product noun-first.
2. **vercel.com/docs** — code-block-led, no preamble.
3. **resend.com** — engineer-soul calm; every claim has a runnable proof.

---

## 5. Hero demo recommendation

**Hero: `examples/pain-point-demos/07-cross-agent-handoff/`. Second:
`09-1-codex-reviewer/`. Third: `04-memory-reuse/`.** One demo per pillar.

1. **`07-cross-agent-handoff/`.** Claude finishes an attempt; Codex opens the
   same repo and reads `AIT_CONTEXT_FILE` instead of starting from zero. The
   only catalog demo with two agent CLIs on one task. The v1 hero
   (`01-blast-radius`) was defensive; the new lead is leverage.
2. **`09-1-codex-reviewer/`.** Claude writes, Codex reviews; the review
   records a blocking finding before apply.
3. **`04-memory-reuse/`.** `ait memory recall` surfaces a decision from a
   prior session. `01-blast-radius/` moves below the fold.

**Hero asset.** Replace `docs/assets/ait-cross-agent-session.gif` with a 12-
to-18-second recording of `07-cross-agent-handoff/run.sh`: Claude's attempt
closes, terminal switches to Codex, Codex prints the inherited context.
Fallback: three-pane static — attempt summary, `AIT_CONTEXT_FILE` excerpt,
Codex's opening turn.

---

## 6. "Would not say" list

Three claims the current surfaces make that AIT cannot defend with evidence.
Downstream writers must not include any of these.

### Banned claim 1 — "Adversarial review catches bugs the implementer misses"

**Why.** Benchmark fixture exists (`tests/fixtures/review_benchmark/`) and the
dogfood report exists (`docs/aitbench-dogfood-report.md`). What does not exist
is published recall, precision, false-positive, or latency numbers against a
real-world bug corpus. The report itself says "observational evidence, not a
universal quality proof." Say instead: *"a separate reviewer agent runs
against the attempt."*

### Banned claim 2 — "Multi-agent team" / "Claude, Codex, and Aider as a team"

**Why.** AIT serializes agents through attempts and `AIT_CONTEXT_FILE`. Real
workflow improvement, but "as a team" implies live coordination or shared
state during a run. Handoff is asynchronous, one-direction. Say instead:
*"the next agent receives the prior agent's decisions"* or *"run them on the
same task and pick the diff you trust."*

### Banned claim 3 — "Production-ready" / team-readiness implication

**Why.** Alpha. No cross-machine sync of `.ait/`. Console is read-only;
mutation goes through CLI dry-run only. Metadata export/import is dry-run
only. Say instead: *"alpha quality, dogfooded daily on real repos,
single-machine metadata."* The launch kit must say "alpha" in the post body,
not buried in a footer.

### Banned claim 4 — "Memory recall surfaces the right context" / "Never lose a decision"

**Why.** `src/ait/memory/recall.py` uses BM25-style ranking over prior
attempts, accepted facts, and notes. There is no published precision/recall
benchmark on real query corpora. "Never lose a decision" overpromises
retrieval quality. Say instead: *"`ait memory recall <query>` searches prior
attempts, accepted facts, and notes — you decide what's relevant."* This
banned claim was added in v2 because the new lead emphasises memory; the
risk grew with the pitch.

---

## Quick-reference card

- **EN hero:** One agent writes. Another reviews. The repo remembers both.
- **ZH hero:** 一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來。
- **Pain points (in order):** Every agent starts from zero on the same repo ·
  The agent that wrote the code is the only one who reviewed it · Last
  Tuesday's decision lives in a closed chat tab.
- **Hero demo:** `examples/pain-point-demos/07-cross-agent-handoff/`
  (second: `09-1-codex-reviewer/`, third: `04-memory-reuse/`).
- **Install snippet (verbatim across surfaces):**

  ```bash
  pipx install ait-vcs      # or: npm install -g ait-vcs
  cd your-repo
  ait init
  claude ...                # codex / aider / gemini / cursor work the same way
  ait status
  ait apply latest
  ```

- **Sources of truth:** `src/ait/cli/`, `examples/pain-point-demos/`,
  `docs/aitbench-dogfood-report.md`.
