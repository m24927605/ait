# AIT Launch Kit — 2026

Status: drafts only. Nothing in this file ships without the orchestrator and
user reviewing first. Every claim is sourced from
`docs/ait-power-user-narrative-2026.md` (the bible); any conflict between this
file and the bible is resolved in favour of the bible.

The hero line below is verbatim from the bible Section 1.

---

## 1. Hacker News Show post

### Title (76 chars)

```
Show HN: AIT – one agent writes, another reviews, the repo remembers both
```

### Body (1,820 chars)

```
One agent writes. Another reviews. The repo remembers both.

AIT is a local CLI that wraps Claude Code, Codex CLI, Aider, Gemini CLI,
and Cursor. Every wrapped run lands as an attempt under `.ait/` — prompt,
diff, review findings, prior decisions, all queryable. It does not replace
your agent; it sits between the agent and Git.

Pillar 1 — cross-agent handoff. Yesterday Claude chased a 429 bug.
This morning Codex opens the same repo. Instead of re-investigating,
Codex receives a handoff file (env var: `AIT_CONTEXT_FILE`), assembled
by `src/ait/context_manifest.py` from prior attempts and notes. Handoff
is asynchronous and inspectable: `ait query --on attempt 'agent.agent_id="codex:main"'`.
Demo: `examples/pain-point-demos/07-cross-agent-handoff/`.

Pillar 2 — the implementer does not review its own work.
`ait review attempt latest-reviewable --mode adversarial --review-adapter
claude-code` runs a different agent, with a different prompt, against the
attempt's diff. The reviewer cannot see the implementer's chat. High-
severity findings hold `ait apply`. Demo:
`examples/pain-point-demos/09-1-codex-reviewer/`.

Pillar 3 — last Tuesday's decision lives in a closed chat tab. `ait
memory recall "retry budget"` searches prior attempts, accepted facts,
and notes (`src/ait/memory/recall.py`), alongside live `CLAUDE.md` /
`AGENTS.md` / `.codex/memory.md` files. You decide what's relevant.
Demo: `examples/pain-point-demos/04-memory-reuse/`.

Install (requires Python 3.14+; on 3.13 or older use
`pipx install --python python3.14 ait-vcs`):

  pipx install ait-vcs      # or: npm install -g ait-vcs
  cd your-repo
  ait init
  claude ...                # codex / aider / gemini / cursor work the same way
  ait status
  ait apply latest

Alpha. Single-machine, no cross-machine sync, no telemetry, daemon on a
Unix socket only. Dogfooded daily; rough edges expected. Happy to take
the tour through any of the three demos in comments.
```

### Top-comment author response templates

**Reaction (a) — "how is this different from Aider / Cursor?"**

```
Fair question. Short version:

- Aider is an in-process edit + auto-commit loop with one model per run.
  AIT runs alongside it: Aider's commits land *inside* an AIT attempt,
  and a separate reviewer agent can run against that attempt
  (`ait review attempt --mode adversarial`, `src/ait/cli/review.py`).
  Apply is still explicit.
- Cursor is an IDE-integrated agent. AIT is CLI-first and wraps the
  agent CLIs you already run outside the editor. `.ait/` is local; the
  daemon listens on a Unix socket only (`src/ait/daemon_transport.py`).
  No SaaS round-trip.
- The piece neither Aider nor Cursor gives you: a queryable attempt
  ledger across non-editor agents — `ait attempt list`, `ait query`
  (`src/ait/query/`), and a handoff file (env var: `AIT_CONTEXT_FILE`)
  so the next agent (could be Codex, could be Claude) starts with the
  previous agent's decisions instead of from zero.

AIT is the layer around the agents, not a replacement.
```

**Reaction (b) — "what about benchmark numbers for the reviewer?"**

```
Straight answer: no published recall, precision, false-positive, or
latency numbers yet. A 10-case fixture lives at
`tests/fixtures/review_benchmark/` and a local dogfood report lives at
`docs/aitbench-dogfood-report.md`. The report itself says
"observational evidence, not a universal quality proof."

So I won't claim the reviewer catches bugs the implementer missed — I
don't have the corpus to back that up yet. What I can show is the
mechanism: the reviewer is a different agent, a different prompt,
without access to the implementer's chat, and high-severity findings
hold `ait apply`. Whether that's worth running on your repo is an
empirical question I'd rather you answer with your own attempts than
take from me.

Building the corpus is the next benchmark milestone. Until then, alpha.
```

---

## 2. X / Twitter launch thread (English)

Length budget: ≤280 chars per tweet. One hashtag per tweet, only where it
adds reach. Demo embed assignments noted under each tweet.

**Tweet 1 (hero + hook, 245 chars)**

```
One agent writes. Another reviews. The repo remembers both.

AIT is a local CLI that wraps Claude Code, Codex, Aider, Gemini, Cursor.
Every run becomes an attempt under .ait/ — prompt, diff, review,
prior decisions, queryable.

Three pillars in this thread.
```

**Tweet 2 (the three pillars, 224 chars)**

```
The three things AIT actually changes:

1. Cross-agent handoff — the next agent inherits the last agent's
   decisions.
2. The implementer does not review its own work.
3. Memory across sessions — last Tuesday's call is a CLI query away.

One per tweet next.
```

**Tweet 3 (pillar 1, embed: `07-cross-agent-handoff`, 268 chars)**

```
Pillar 1 — cross-agent handoff.

Yesterday Claude chased a 429. This morning Codex opens the same repo
and receives the prior agent's handoff file instead of starting from
zero. (env var: AIT_CONTEXT_FILE)

ait query --on attempt 'agent.agent_id="codex:main"'

[VIDEO: examples/pain-point-demos/07-cross-agent-handoff/ — 12-18s]

#ClaudeCode
```

**Tweet 4 (pillar 2, embed: `09-1-codex-reviewer`, 271 chars)**

```
Pillar 2 — the implementer does not review its own work.

ait review attempt latest-reviewable \
  --mode adversarial \
  --review-adapter claude-code

Different agent. Different prompt. No access to the implementer's
chat. High-severity findings hold ait apply.

[GIF: 09-1-codex-reviewer]

#Codex
```

**Tweet 5 (pillar 3, embed: `04-memory-reuse`, 252 chars)**

```
Pillar 3 — last Tuesday's decision lives in a closed chat tab.

ait memory recall "retry budget"

Searches prior attempts, accepted facts, notes, plus live CLAUDE.md /
AGENTS.md / .codex/memory.md. You decide what's relevant.

[GIF: 04-memory-reuse]
```

**Tweet 6 (differentiation, 277 chars)**

```
What it's not:

- Not an Aider replacement — Aider commits land inside an AIT attempt.
- Not Cursor — AIT is CLI-first, wraps the agents you run in a terminal.
- Not Cline / Continue — AIT is attempt-grained, not keystroke-grained,
  no IDE plugin.

AIT is the layer around the agents, not another agent.
```

**Tweet 7 (honest alpha line, 240 chars)**

```
Honest posture: alpha.

Single-machine. No cross-machine sync of .ait/. No telemetry. Daemon
on a Unix socket only.

Dogfood report lives at docs/aitbench-dogfood-report.md — observational
evidence, no recall / precision numbers yet. I'd rather say that than
fake it.
```

**Tweet 8 (CTA, 167 chars)**

```
Try it on a repo you already trust git on (requires Python 3.14+):

  pipx install ait-vcs
  cd your-repo
  ait init
  claude ...
  ait status
  ait apply latest

Three demos linked above. Break it and tell me.

#AI
```

---

## 3. Reddit r/ClaudeAI post draft

### Title (155 chars)

```
[AIT] One agent writes. Another reviews. The repo remembers both. — a local-only attempt ledger for Claude Code + Codex + Aider.
```

### Body (3,720 chars)

```
One agent writes. Another reviews. The repo remembers both.

I've been running Claude Code daily for months and the three things that
kept burning me weren't the model — they were the workflow around it.
AIT is a local CLI I've been building to fix exactly those three. Sharing
the draft here before it goes anywhere else because this sub will catch
the things I'm wrong about faster than HN will.

---

What burned me before AIT, in order:

1. Every agent starts from zero on the same repo. Yesterday Claude chased
   a billing retry 429 for two hours. This morning I opened Codex on the
   same repo to push the fix and Codex re-investigated from scratch.
   Zero handoff. I paid twice for the same investigation.

2. The agent that wrote the code is the only one who reviewed it. Codex
   finishes a diff, says "all tests pass," and the implementer and
   reviewer are the same model, same chat, same prompt. I caught myself
   trusting that on autopilot more than once.

3. Last Tuesday's decision lives in a closed chat tab. Three weeks ago I
   capped the retry budget at three after a long conversation. The chat
   tab is gone. The new agent proposes five and I have to remember
   whether I had a reason.

---

What AIT does, one pillar per pain:

1. Cross-agent handoff. Every wrapped run lands as an attempt under
   `.ait/`. The next run — Codex, Aider, Gemini, Cursor, anything
   wrapped by `ait run --adapter <name>` — receives
   a handoff file (env var: `AIT_CONTEXT_FILE`), assembled from prior
   attempts and notes. You can walk the handoff with
   `ait query --on attempt 'agent.agent_id="codex:main"'`.
   Demo: `examples/pain-point-demos/07-cross-agent-handoff/`.

2. A separate reviewer agent.

   ```
   ait review attempt latest-reviewable \
     --mode adversarial \
     --review-adapter claude-code
   ```

   Different agent. Different prompt. The reviewer cannot see the
   implementer's chat. Findings are queryable rows; high-severity
   findings hold `ait apply`. Demo:
   `examples/pain-point-demos/09-1-codex-reviewer/`.

3. Memory across sessions.

   ```
   ait memory recall "retry budget"
   ```

   Searches prior attempts, accepted facts, and notes alongside live
   `CLAUDE.md` / `AGENTS.md` / `.claude/memory.md` / `.codex/memory.md`
   files. You decide what's relevant. Demo:
   `examples/pain-point-demos/04-memory-reuse/`.

---

Install (requires Python 3.14+; on 3.13 or older use
`pipx install --python python3.14 ait-vcs`):

```
pipx install ait-vcs      # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

---

Honest posture: alpha. I've been dogfooding it daily on real repos but
there's no cross-machine sync of `.ait/`, no SaaS, no telemetry, and the
daemon listens on a Unix socket only. A 10-case review-benchmark fixture
exists at `tests/fixtures/review_benchmark/` and a dogfood report lives
at `docs/aitbench-dogfood-report.md`, but I have not published recall or
precision numbers and I won't until the corpus is real.

Things I'd specifically like you to break:

- Wrap a Claude Code session you've been running for weeks and tell me
  what the handoff to a second agent feels like.
- Run the adversarial review on a diff Claude already shipped and tell
  me whether the findings are noise.
- Try `ait memory recall` on a phrase you remember writing months ago
  and see if the right attempt comes back.

I'd rather hear the rough edges from this sub than ship more polish.
```

---

## 4. Reddit r/LocalLLaMA post draft

### Title (151 chars)

```
[AIT] Local-only attempt ledger for Claude Code, Codex, Aider — no SaaS, no telemetry, daemon on a Unix socket. One agent writes, another reviews.
```

### Body (3,580 chars)

```
One agent writes. Another reviews. The repo remembers both.

Every AI dev tool I've tried in the last year wants my prompts and diffs
in someone else's cloud. Langfuse, Braintrust, the agent-management
SaaS of the week — they all default to round-tripping through a service.
For a local-LLM crowd that already pays the inference bill on-machine,
that trade is bad.

AIT is the opposite. It's a CLI that wraps Claude Code, Codex CLI,
Aider, Gemini CLI, and Cursor. Every wrapped run lands as an attempt
under `.ait/` in your repo. The daemon listens on a Unix socket only
(`src/ait/daemon_transport.py`). No network egress, no telemetry, no
required account. If you point your wrapped agent at a local model
endpoint, the entire loop — prompt, diff, attempt metadata, review
findings, memory recall — stays on-machine.

---

What burned me before AIT:

1. Every agent starts from zero on the same repo. The next CLI session
   re-investigates the same code path the last one already mapped.
2. The agent that wrote the code is the only one who reviewed it. One
   model, one chat, one prompt — and the review is the same model
   talking to itself.
3. Last Tuesday's decision lives in a closed chat tab. Three weeks ago
   I capped a retry budget at three after a long conversation. The
   chat tab is gone. The new agent proposes five and I have to
   remember whether I had a reason.
4. Every dev tool wanted my prompts and diffs in their cloud, and I
   couldn't always tell whether the "local" mode actually was local.

---

What AIT adds, one pillar per pain:

1. Local-first cross-agent handoff. Wrap any agent CLI with
   `ait run --adapter <name>` (`src/ait/cli/run.py`). The next run
   receives a handoff file (env var: `AIT_CONTEXT_FILE`) assembled by
   `src/ait/context_manifest.py` from prior attempts and notes. Walk
   the trail with `ait query --on attempt 'agent.agent_id="codex:main"'`.
   Demo: `examples/pain-point-demos/07-cross-agent-handoff/`.

2. A separate reviewer agent.

   ```
   ait review attempt latest-reviewable \
     --mode adversarial \
     --review-adapter claude-code
   ```

   Different agent, different prompt, no access to the implementer's
   chat. High-severity findings hold `ait apply`. Point the reviewer
   at a local-hosted model adapter if that's your preference; the
   review loop has no network requirement of its own. Demo:
   `examples/pain-point-demos/09-1-codex-reviewer/`.

3. Local memory across sessions.

   ```
   ait memory recall "retry budget"
   ```

   Searches prior attempts, accepted facts, and notes under `.ait/`,
   plus live `CLAUDE.md` / `AGENTS.md` / `.cursor/rules`
   (`src/ait/memory/recall.py`). You decide what's relevant. The
   ranking is BM25-style over local state; no embedding service, no
   external index. Demo: `examples/pain-point-demos/04-memory-reuse/`.

---

Install (requires Python 3.14+; on 3.13 or older use
`pipx install --python python3.14 ait-vcs`):

```
pipx install ait-vcs      # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

---

Provenance and posture, since this sub cares:

- `.ait/` lives next to `.git/`. Single-repo, single-machine.
- No cross-machine sync. No SaaS. No telemetry.
- Daemon: Unix socket, no TCP listener.
- A 10-case review fixture exists at
  `tests/fixtures/review_benchmark/`; the dogfood report at
  `docs/aitbench-dogfood-report.md` calls itself observational
  evidence, not a universal quality proof. No recall / precision
  numbers published yet.

Alpha. MIT, Python 3.14+, zero runtime dependencies. Happy to take any
pointed question on the local-only design choice or the daemon
boundary.
```

---

## 5. Threads / X Chinese post

Three-post mini-thread. Hero line is the bible's Traditional Chinese
hero line, verbatim. Native voice, not a translation of the English
thread.

**Post 1 (hero + 三個 pillar 概覽, 257 chars)**

```
一個 agent 寫，另一個 agent 審，repo 把兩邊都記下來。

AIT 是包在 Claude Code、Codex、Aider、Gemini、Cursor 外面的本機 CLI。
每一次 agent run 都是 .ait/ 裡的 attempt：prompt、diff、審查結果、上一輪
決定都查得到。

三個我做這個工具的真正原因，分三則貼。

#ClaudeCode
```

**Post 2 (Pillar 1 + Pillar 2, 269 chars)**

```
1. 同一個 repo，每個 agent 都從零開始。昨天 Claude 追 429，今天 Codex
   開同一個 repo，又從頭調查一次。AIT 讓下一個 agent 透過 handoff
   檔案（env var: AIT_CONTEXT_FILE）接到上一個 agent 的決定。

2. 寫 code 的 agent 是唯一審 code 的人。
   ait review attempt latest-reviewable --mode adversarial
   另一個 agent，不同 prompt，看不到實作者的對話，high-severity 會擋住
   ait apply。

#Codex
```

**Post 3 (Pillar 3 + install + alpha, 268 chars)**

```
3. 上禮拜二的決定關掉 chat tab 就沒了。
   ait memory recall "retry budget"
   會搜尋過去 attempts、accepted facts、notes，加上現存的 CLAUDE.md /
   AGENTS.md。你自己判斷哪一條相關。

安裝（需要 Python 3.14+）：
  pipx install ait-vcs
  cd your-repo
  ait init
  claude ...
  ait status
  ait apply latest

Alpha：單機、無 SaaS、無 telemetry、daemon 只開 Unix socket。歡迎拆。
```

---

## 6. Embedded demo asset note

Launch needs three recordings. Only one exists in-repo today.

| Demo path | Asset needed | Length | Current status |
| --- | --- | --- | --- |
| `examples/pain-point-demos/07-cross-agent-handoff/` | Terminal recording: Claude attempt closes, terminal switches to Codex, Codex prints inherited context from `AIT_CONTEXT_FILE` (per bible Section 5). | 12-18s | **Blocker.** The existing `docs/assets/ait-cross-agent-session.gif` is the legacy "advisory analysis" capture, not the new hero recording the bible specifies. A new recording must be produced before launch. |
| `examples/pain-point-demos/09-1-codex-reviewer/` | Short capture of the review-finding row: `ait review attempt latest-reviewable --mode adversarial --review-adapter claude-code` followed by the blocking finding row in `ait review finding list --severity high`. | 8-12s | **Blocker.** No asset in-repo yet. |
| `examples/pain-point-demos/04-memory-reuse/` | Short capture: `ait memory recall "retry budget"` returns a prior attempt / accepted fact row tied to an earlier decision. | 6-10s | **Blocker.** No asset in-repo yet. |

Fallback per bible Section 5: a three-pane static for the hero — attempt
summary, `AIT_CONTEXT_FILE` excerpt, Codex opening turn — if the 12-18s
recording cannot be produced in time.

**Action required from orchestrator / user before any post goes live:**
schedule three recording sessions or approve the static fallbacks. Until
then, all `[VIDEO:…]` / `[GIF:…]` placeholders in the X thread and the
demo links in the HN / Reddit bodies are unresolved.
