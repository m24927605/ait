# AIT Hero Demo Recording Plan

**Status.** Recording-ready. User records, drops files into `docs/assets/`,
launch unblocks.

**Scope.** Three terminal demos, one per pillar from
`docs/ait-power-user-narrative-2026.md` Section 2.

| Demo | Pillar | Length |
| --- | --- | --- |
| `examples/pain-point-demos/07-cross-agent-handoff/` | multi-agent handoff | 12–18s |
| `examples/pain-point-demos/09-1-codex-reviewer/` | adversarial review | 8–12s |
| `examples/pain-point-demos/04-memory-reuse/` | shared + long-term memory | 8–12s |

## Section 1 — Executive summary

### Tool: `vhs` (charm.sh)

Declarative `.tape` files (reproducible, PR-diff friendly), one source
produces GIF + MP4 + PNG, ms-precision typing / pause control. `asciinema`
needs a separate render step (`agg`); `terminalizer`'s GIF encoder is the
weakest of the three.

Install: `brew install vhs ffmpeg ttyd`.

### Strategy

`run.sh` takes 30–120 s real wall-clock because it provisions a fresh
workspace and calls real `claude` / `codex exec`. We do **not** record
`run.sh`. We record a **post-run inspection** against a workspace the user
has already produced. Inspection commands are sub-second.

### Output formats per demo

- **GIF** — README + docs hero. Target ≤2 MB, hard cap 4 MB. 1200×480 logical,
  18–24 fps, 128-color palette after `gifsicle --lossy=60`.
- **MP4** — X / Threads embeds. ≤5 MB at H.264 30 fps.
- **PNG fallback** — Three stills per demo at hero beats, for surfaces that
  cannot render the GIF (bible Section 5).

### Final asset paths

```
docs/assets/hero-cross-agent-handoff.{gif,mp4}
docs/assets/hero-cross-agent-handoff-{1,2,3}.png
docs/assets/hero-codex-reviewer.{gif,mp4}
docs/assets/hero-codex-reviewer-{1,2,3}.png
docs/assets/hero-memory-recall.{gif,mp4}
docs/assets/hero-memory-recall-{1,2,3}.png
docs/assets/tapes/hero-{cross-agent-handoff,codex-reviewer,memory-recall}.tape
```

The legacy `docs/assets/ait-cross-agent-session.gif` stays — historical v1.

---

## Section 2 — Per-demo storyboards

### Common setup (all three demos)

- **Env.** Python 3.11+, `ait-vcs` via `pipx`, `claude` + `codex` CLIs
  authenticated, `node` + `npm` on PATH.
- **Repo state.** Run the demo's `run.sh` to completion **before**
  recording; confirm `verify.sh` (or the `PASS` line) is green. Export the
  attempt IDs from the `PASS` line into the recording shell.
- **Terminal.** 100 cols × 30 rows. 80×24 collapses table output below
  readability.
- **Palette.** Dark `#0d1117` background, `#e6edf3` foreground; accent green
  `#3fb950` (promoted), yellow `#d29922` (attempt IDs / topics), red
  `#f85149` (blocked / high severity). vhs theme `GitHub Dark`.
- **Shell env.** `AIT_ASSUME_TTY=1`, `NO_COLOR=`, `TERM=xterm-256color`.
- **CWD.** `examples/pain-point-demos/<demo>/workspace` with
  `workspace/.ait/bin` on PATH.

---

### Demo 1 — 07-cross-agent-handoff (hero)

The viewer must believe: *Claude finished an attempt. Codex opened the same
repo and got the prior decision — without reading any file directly.*

**Pre-record state.** Run `run.sh` and export `CLAUDE_ID`, `CODEX_ID` from
the `PASS` output.

**Shot list (10 beats, 14–16 s).**

| # | Command | What viewer sees | Pacing |
| - | --- | --- | --- |
| 1 | *(prompt)* | clean prompt | hold 600 ms |
| 2 | `ait query --on attempt 'title~"calculator module decision"' --format table` | one row: Claude attempt, status `promoted`, agent `claude-code` | 50 ms/char, hold 1.5 s |
| 3 | `ait memory list --format table` | row sourced from `AGENTS.md`, topic `agent-memory`, carrying the decision line | 50 ms/char, hold 1.2 s |
| 4 | `ait query --on attempt 'title~"calculator module handoff"' --format table` | one row: Codex attempt, agent `codex` — a different agent, same repo | 50 ms/char, hold 1.5 s |
| 5 | `ait attempt show $CODEX_ID --format text` | header + `files.changed: handoff-proof.txt` + evidence section | 50 ms/char, hold 2.5 s |
| 6 | `cat $(ait attempt show $CODEX_ID --format json \| python3 -c "import json,sys;print(json.load(sys.stdin)['workspace_ref'])")/handoff-proof.txt` | exact decision string from Claude's attempt, including `AIT_HANDOFF_PROOF=…` | 80 ms/char, hold 3.0 s |
| 7 | *(prompt)* | clean prompt | hold 800 ms |
| 8 | `# Codex received Claude's decision through the handoff file.` | comment appears | 40 ms/char, hold 1.5 s |
| 9 | *(prompt)* | clean prompt | hold 600 ms |
| 10 | end | — | — |

**Hero moment: beat 6.** The prior agent's exact decision string appears in
a file the second agent created. Codex never opened `AGENTS.md` (the prompt
in `run.sh:31` forbids it). Capture as `hero-cross-agent-handoff-2.png`.

**Failure modes.**

- *`run.sh` incomplete.* Beats 2/3/4 render empty tables. Re-run, verify
  green before recording.
- *Attempt IDs change per run.* By design (timestamps in titles). Re-export
  IDs between takes; viewers read row shape, not values.
- *Path pipeline in beat 6 awkward.* Fallback: resolve the workspace path
  before recording, paste literal `cat workspace/.ait/<sha>/<attempt>/handoff-proof.txt`.
- *PNG fallback.* Capture beats 2, 5, 6 as `hero-cross-agent-handoff-{1,2,3}.png`.

**Captions.**

- README EN: *Claude finishes an attempt. Codex opens the same repo and
  writes the prior decision into a file — without reading `AGENTS.md`
  directly. The handoff file did the work.*
- README ZH: *Claude 收尾，Codex 接手，沒翻 `AGENTS.md` 就把上一輪的決定寫進新檔。handoff 檔案幫忙接住的。*
- Alt EN: *Terminal showing two ait attempts on the same repo: Claude's
  decision attempt promoted, then Codex's handoff attempt writes the exact
  decision string into a new file.*
- Alt ZH: *終端機顯示同一個 repo 兩個 attempt：Claude 的決定 attempt 已 promote，Codex 後續 attempt 把同一條決定字串寫到新檔。*
- X tweet: *One agent writes. The next agent already read it. No chat tab.
  No file peek. Just the handoff file.*

---

### Demo 2 — 09-1-codex-reviewer

The viewer must believe: *A different agent reviewed the code, found a real
problem, and held apply.*

**Pre-record state.** Run `run.sh`, confirm `verify.sh` green, export
`ATTEMPT_ID`.

**Shot list (8 beats, 9–11 s).**

| # | Command | What viewer sees | Pacing |
| - | --- | --- | --- |
| 1 | *(prompt)* | clean prompt | hold 500 ms |
| 2 | `ait query --on attempt 'title~"unsafe divide implementation"' --format table` | one row: Claude attempt, agent `claude-code` | 50 ms/char, hold 1.2 s |
| 3 | `ait query --on attempt 'review.status="blocked"' --format table` | same attempt, blocked filter — red on `blocked` | 60 ms/char, hold 1.5 s |
| 4 | `ait review finding list --severity high --format text` | finding: `severity: high`, `blocking: true`, `path: src/divide.js`, `reviewer_adapter:` points at `codex_reviewer.sh` | 50 ms/char, hold 2.5 s |
| 5 | `ait apply $ATTEMPT_ID --mode current` | non-zero exit, line `apply held: review gate` | 70 ms/char, hold 2.0 s |
| 6 | *(prompt)* | clean prompt | hold 600 ms |
| 7 | `# Different agent. Different prompt. Blocked apply.` | comment appears | 40 ms/char, hold 1.5 s |
| 8 | end | — | — |

**Hero moment: beat 5.** `ait apply` exits non-zero with `apply held:
review gate` (verbatim per `verify.sh:28`). The review is not advisory.
Capture as `hero-codex-reviewer-2.png`.

**Failure modes.**

- *Codex reviewer adapter fails.* `codex_reviewer.sh:49` makes a real OpenAI
  call; can fail or run 20–60 s. User must reach `verify.sh` green before
  recording.
- *Finding body wording varies.* The shot list leans on `severity` and
  `reviewer_adapter` fields, not the prose body — both deterministic.
- *Apply succeeds (review gate not enabled).* `run.sh:24` sets
  `auto_apply_requires_review: true`. If beat 5 succeeds, abort and re-run
  `run.sh`.
- *PNG fallback.* Capture beats 4, 5, and 2+3 composite as
  `hero-codex-reviewer-{1,2,3}.png`.

**Captions.**

- README EN: *Claude implemented `divide(a, b)` without zero-division
  handling. Codex reviewed the attempt and recorded a high-severity blocking
  finding. `ait apply` was held by the review gate.*
- README ZH: *Claude 寫了 `divide(a, b)`，沒處理除以零。Codex 審了這個 attempt，記下 high 級別的 blocking finding。`ait apply` 被 review gate 擋住。*
- Alt EN: *Terminal showing an ait review-finding row with severity high,
  blocking true, and an ait apply call that exits with "apply held: review
  gate".*
- Alt ZH: *終端機顯示 ait review finding 列出 severity high、blocking true，接著 ait apply 被 review gate 擋下。*
- X tweet: *The implementer doesn't review its own work. A different agent
  does. Apply is held until the finding is resolved.*

---

### Demo 3 — 04-memory-reuse

The viewer must believe: *A decision from a prior session is one CLI command
away. The new agent does not re-investigate.*

**Pre-record state.** Run `run.sh`, export `CLAUDE_ID`, `CODEX_ID`.

**Shot list (9 beats, 10–12 s).**

| # | Command | What viewer sees | Pacing |
| - | --- | --- | --- |
| 1 | *(prompt)* | clean prompt | hold 500 ms |
| 2 | `ait memory list --format table` | row: topic `auth-retry`, source `manual:demo`, body starts `Decision: auth retry backoff uses missing jitter…` | 50 ms/char, hold 1.5 s |
| 3 | `ait memory recall "auth retry backoff" --limit 3 --format text` | recall hits including the `auth-retry` note and its `AIT_PROOF_AUTH_RETRY=…` body, plus a hit referencing the Claude attempt | 70 ms/char, hold 3.0 s |
| 4 | `ait query --on attempt 'title~"reuse auth retry investigation"' --format table` | one row: Codex attempt | 50 ms/char, hold 1.2 s |
| 5 | `ait attempt show $CODEX_ID --format text` | `files.changed: context-proof.txt`, evidence shows the proof string reached Codex via the handoff file | 50 ms/char, hold 2.0 s |
| 6 | *(prompt)* | clean prompt | hold 500 ms |
| 7 | `# Prior decision, one CLI command away.` | comment appears | 40 ms/char, hold 1.2 s |
| 8 | *(prompt)* | clean prompt | hold 500 ms |
| 9 | end | — | — |

**Hero moment: beat 3.** `ait memory recall` returns the prior decision
line including the proof string — single CLI call, no chat scrollback.
Capture as `hero-memory-recall-2.png`.

**Failure modes.**

- *Recall returns zero hits.* Query `"auth retry backoff"` matches the note
  body on three terms; rerank can shift order but the hit appears.
  Acceptable.
- *Note not yet imported.* `run.sh:26` calls `ait memory note add` after
  Claude's attempt. Re-run to `PASS` before recording.
- *Terminal width truncates.* `ait memory list` may truncate at 100 cols;
  beat 3 (`text` format) does not. Acceptable degradation.
- *PNG fallback.* Capture beats 2, 3, 4 as `hero-memory-recall-{1,2,3}.png`.
  Beat 3 is the must-have still.

**Captions.**

- README EN: *Last week Claude recorded a decision about auth retry backoff.
  `ait memory recall` surfaces it for the next agent. Codex picks up the
  prior decision through the handoff file.*
- README ZH: *上週 Claude 記下 auth retry backoff 的決定。`ait memory recall` 把它撈回來給下一個 agent。Codex 透過 handoff 檔案接到上一輪的決定。*
- Alt EN: *Terminal showing ait memory recall returning a prior decision
  note and an ait attempt row from a different agent reusing that decision.*
- Alt ZH: *終端機顯示 ait memory recall 回傳一筆過去的決定 note，以及另一個 agent 的 attempt 已經把這條決定用上。*
- X tweet: *Last Tuesday's decision is one CLI call away. `ait memory recall
  <query>` searches prior attempts, accepted facts, and notes — you decide
  what's relevant.*

---

## Section 3 — Recording tool setup

### Tape template

Copy to three files under `docs/assets/tapes/`. Body filled from each shot
list in Section 2.

```tape
# hero-<demo>.tape — vhs source for AIT hero demo recording.
# Shot list: docs/ait-hero-demo-recording-plan.md Section 2.

Output docs/assets/hero-<demo>.gif
Output docs/assets/hero-<demo>.mp4

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 480
Set TypingSpeed 50ms
Set PlaybackSpeed 1.0
Set Framerate 24
Set Theme "GitHub Dark"
Set Padding 20
Set FontFamily "JetBrainsMono Nerd Font"

# Pre-recording: user exports CLAUDE_ID / CODEX_ID / ATTEMPT_ID in the
# shell that invokes `vhs` BEFORE running the tape.
Hide
Type "cd examples/pain-point-demos/<demo>/workspace" Enter
Type "export PATH=\"$PWD/.ait/bin:$PATH\"" Enter
Type "clear" Enter
Show

Sleep 600ms

# Beat 2:
Type "ait query --on attempt 'title~\"…\"' --format table"
Enter
Sleep 1500ms

# Hero still:
Screenshot docs/assets/hero-<demo>-2.png

# ... remaining beats per Section 2 ...

Sleep 600ms
```

### Build

```bash
vhs docs/assets/tapes/hero-cross-agent-handoff.tape
vhs docs/assets/tapes/hero-codex-reviewer.tape
vhs docs/assets/tapes/hero-memory-recall.tape
```

`vhs` writes GIF, MP4, and PNGs to the paths inside the `.tape`. One step.

### File-size optimization

Defaults produce 3–5 MB GIFs. To hit ≤2 MB:

```bash
gifsicle --lossy=60 --optimize=3 --colors 128 -o out.gif in.gif
```

Typical savings: 40–55 %. If still over: drop `Framerate` to 18 (smooth
floor for typing). MP4 at H.264 is naturally ≤1 MB; no extra work.

---

## Section 4 — Asset integration checklist

### Stand-in hero swaps (lines that currently point at `site-docs/assets/ait-work-graph.png`)

These references must be updated to the new hero GIF / PNG. **This plan
does not touch them — the swap is the user's pass after recording.**

- `README.md.draft:23` — `<img src="site-docs/assets/ait-work-graph.png" ...>` → `<img src="docs/assets/hero-cross-agent-handoff.gif" ...>`.
- `README.zh-TW.md.draft:20` — same swap, Chinese alt text from Section 2.
- `site-docs/index.md.draft:91` — `![...](assets/ait-work-graph.png)` → `![...](../docs/assets/hero-cross-agent-handoff.gif)` (verify relative path under the site builder).
- `site-docs/zh-TW/index.md.draft:87` — same as English index, Chinese alt.

Delete the HTML `<!-- TODO: replace with 12-18s recording -->` markers at
`README.md.draft:20` and `README.zh-TW.md.draft:17` once the GIF lands.

### Launch-kit embed slots

Per `docs/launch-kit-2026.md:514–531`:

- HN body — add GIF inline in the README so HN scrapers pick it up.
- X thread `[VIDEO:…]` / `[GIF:…]` markers at `launch-kit-2026.md:151, 168,
  184` — swap each to the matching `docs/assets/hero-*.mp4` (Twitter prefers
  MP4).
- Reddit r/ClaudeAI and r/LocalLLaMA — embed the three GIFs directly, one
  per pillar.

### Pre-promote checklist

- [ ] Each GIF ≤ 2 MB (hard cap 4 MB).
- [ ] Each MP4 ≤ 5 MB.
- [ ] Each demo has three PNG fallbacks.
- [ ] Alt text on every `<img>` and `![...]`.
- [ ] Captions match the bible's voice. No banned phrases (no "git
      workflow layer", no "adversarial review" as lead, no
      "AIT_CONTEXT_FILE" above the fold).
- [ ] Recordings contain no API keys, no real customer paths, no production
      hostnames — only `examples/pain-point-demos/…/workspace`.
- [ ] None of the four "would-not-say" claims appears: no "catches bugs",
      no "multi-agent team", no "production-ready", no "never lose a
      decision".
- [ ] Captions are ASCII / standard Chinese — zero emoji.
- [ ] `verify.sh` was green in the same session as the recording.
- [ ] `.tape` source files committed alongside the GIFs.

---

## Section 5 — Escalations

1. **Inspection vs. live `run.sh` recording.** This plan records the
   post-run inspection. `run.sh` itself takes 30–120 s of real LLM calls
   which blows the 12–18 s budget. Confirm the inspection-recording
   approach, or grant a length-budget waiver.

2. **Real wall-clock for each demo's `run.sh` on the user's machine.** The
   user must measure this once before recording so the pre-record step
   doesn't surprise them. Anywhere 30–120 s per demo.

3. **Font availability.** `.tape` requests `JetBrainsMono Nerd Font`. Without
   it, `vhs` falls back to system monospace. Decide: install
   (`brew install --cask font-jetbrains-mono-nerd-font`) or accept fallback.

4. **Palette exact hex.** Bible doesn't specify. The plan picks GitHub Dark.
   If the rebrand has a specific palette in `site-docs/`, switch the `.tape`
   theme to match.

5. **Fixture-mode `run.sh --rehearsal` flag.** Deterministic replay without
   real LLM calls. Hooks exist (`.state/<demo>/` files, read by `verify.sh`)
   but no flag. **Proposing, not implementing** — touches
   `examples/pain-point-demos/lib/demo.sh` and three `run.sh` files, outside
   this plan's scope. If approved, recording drops from ~10 min per demo to
   ~30 s.

6. **Ship with PNG-only fallbacks?** Bible Section 5 allows a three-pane
   static. If launch ships PNG-only and produces GIFs later, Section 4's
   swap lines change: the PNG fallback becomes the hero. Launch-readiness
   call, not a recording-plan call.
