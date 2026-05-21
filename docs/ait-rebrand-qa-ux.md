# AIT Rebrand QA — UX Audit

**Status:** NEEDS WORK
**Reader-question pass rate:** 2.3 / 3 (across the three personas, averaged)

The three drafts answer "What is AIT?" cleanly. They mostly answer "How is it different?" but the differentiation table is dense and arrives late. They under-answer "Why install in 5 minutes?" — there is no compressed leverage hook above the fold, just three pain scenarios that demand reading 400+ words to absorb.

## Persona simulation results

### Persona 1 — Burned Claude Code power user

- **Hero comprehension: 9/10** — "One agent writes. Another reviews. The repo remembers both." plus the subhead lands in <5s. He instantly maps it to his own pain.
- **Pillar comprehension: 7/10** — Picks up multi-agent handoff and review fine. "Memory" pillar is correct but feels like a smaller third item; in `README.md.draft:35` it's "prior attempts stay queryable" — abstract.
- **Differentiation comprehension: 6/10** — Differentiation table at `README.md.draft:82-87` is clear but he stops reading after row 2; "What ait does not do" at line 89-94 is the part he actually remembers.
- **Install temptation: 8/10** — Five-line install snippet is irresistible. The "no published benchmark" line at line 94 is the only friction — he wonders if it's even worth a Saturday morning.
- **Verdict:** *"OK. Reviewer is a different agent — that's the thing I've been hand-rolling with two Claude tabs. I'll install it tonight if the demo gif at the top actually works. The placeholder PNG at `README.md.draft:31` worries me — if a launch README still has 'placeholder.png' I assume the rest is half-baked. Fix that and I'm in."*

### Persona 2 — Multi-tool agent juggler

- **Hero comprehension: 9/10** — Hero line plus `index.md.draft:11-12` "Every agent run is an attempt under .ait/" is exactly what she needed.
- **Pillar comprehension: 8/10** — Three H3s in `index.md.draft:42, 53, 69` name the pillars in order. She can recite them after 30s.
- **Differentiation comprehension: 8/10** — Already knew Aider/Cursor/Cline; the table at `index.md.draft:32-38` confirms the gap. The `AIT_CONTEXT_FILE` phrasing is intentionally hidden behind "handoff file" — she notices and respects it.
- **Install temptation: 9/10** — She'd run it. She has a Codex-after-Claude habit and wants the handoff file.
- **Verdict:** *"Three things I want to know: does the handoff file include the prior diff, or just decisions? Why is it called 'handoff file' on the docs page but `AIT_CONTEXT_FILE` in the launch kit (`launch-kit-2026.md:32`)? That inconsistency would make me check the source. And the differentiation table repeats verbatim across three surfaces — feels like duplication, not synthesis."*

### Persona 3 — Local-first ops engineer

- **Hero comprehension: 7/10** — Likes the hero but doesn't get the "no network" angle until paragraph 4 of `README.md.draft:140-146`. Hero says nothing about local-only.
- **Pillar comprehension: 7/10** — Pillars are clear but he doesn't care about pillar 1 (handoff) at all. He cares about local data.
- **Differentiation comprehension: 9/10** — `index.md.draft:35` "Nothing leaves your machine; the daemon is a local Unix socket" is exactly what hooks him. He reads the r/LocalLLaMA draft in `launch-kit-2026.md:340-445` and approves.
- **Install temptation: 9/10** — Will install on a personal repo. Wants to grep the source for any HTTP client before he points it at production.
- **Verdict:** *"Buried lede. The hero should say 'local-only attempt ledger' or at least 'nothing leaves your machine' above the fold. I had to scroll past three pain points to learn the daemon is Unix-socket only. The r/LocalLLaMA draft leads with that — port it to the README."*

## Per-surface friction findings

**`README.md.draft`**
- `README.md.draft:31` ships a `placeholder.png`. Severe — a placeholder image in the launch README signals incompleteness to every persona. **Blocker for launch.**
- `README.md.draft:35` mashes three pillars into one 50-word paragraph. The H1 has a one-pillar-per-clause structure ("writes / reviews / remembers"); the prose right after collapses them into one breath. Personas 1 and 3 noticed.
- `README.md.draft:84-87` differentiation table mentions `src/ait/cli/run.py` and other source paths inline. Persona 2 likes this; Persona 1 finds it noisy. Consider moving source paths to a footnote row.
- `README.md.draft:140-146` "Status" block buries the "no telemetry, Unix socket" line. Move "Nothing leaves your machine" to the second sentence below the hero.

**`README.zh-TW.md.draft`**
- `README.zh-TW.md.draft:20-22` references `docs/assets/ait-cross-agent-session.gif` (existing legacy gif) while the English draft references a placeholder PNG. Two surfaces, two different hero asset states. Pick one.
- `README.zh-TW.md.draft:53` runs a 100-character sentence packed with English nouns ("`ait run --adapter <name>`...都會收到一份 `AIT_CONTEXT_FILE`，內容由..."). Native-Chinese readers will reach the bracket and lose the thread. Split.
- `README.zh-TW.md.draft:30` keeps "依序：多 agent 之間能交接、寫的人不能同時審自己、長期決定不會跟著 chat tab 一起消失" — strong, native-feeling.

**`site-docs/index.md.draft`**
- `index.md.draft:38` puts "When NOT to use AIT" *inside* the differentiation table. Clever, but the cell is dense and easy to skim past. Promote to its own H2 below the table.
- `index.md.draft:88` references `assets/ait-work-graph.png` for the "after a week" screenshot. Verify this asset exists; if not, second placeholder problem.

**`site-docs/why-ait.md.draft`**
- `why-ait.md.draft:78-106` "When NOT to use AIT" is the best block in the whole rebrand. Four boundaries, no hedging. Persona 1 says: *"I trust the rest of the doc more after reading this."*
- `why-ait.md.draft:108-115` repeats the differentiation table that lives in `index.md.draft` and `README.md.draft`. Three surfaces, one table. Either dedupe or vary the angle per surface.

**`getting-started.md.draft`**
- `getting-started.md.draft:60` "Refactor the auth module" — a tutorial against a not-yet-described auth module. A first-time reader on a fresh `your-repo` does not have `src/auth.py`. They will run it on whatever repo they `cd`'d into and get back garbage. Replace with a trivially safe prompt: `"Add a TODO comment to README.md"`.
- `getting-started.md.draft:54` "Now run `exec $SHELL` once" sits inside step 2 prose, not as a shell command in a code block. A skim reader misses it, runs `claude` in step 3, hits the wrapper bypass. Hoist to its own fenced block.
- `getting-started.md.draft:117-123` "Hand work to a second agent" links to the demo but does not show the command. A power user wants to copy-paste, not click through to a demo directory.

**`site-docs/zh-TW/index.md.draft`**
- `site-docs/zh-TW/index.md.draft:34-38` differentiation table reads native. Good.
- `site-docs/zh-TW/index.md.draft:48` "Handoff 是非同步、單向、有證據的" — clean.

**`launch-kit-2026.md`**
- `launch-kit-2026.md:32` HN body uses `AIT_CONTEXT_FILE` verbatim. The bible at `ait-power-user-narrative-2026.md:126` bans `AIT_CONTEXT_FILE` above the fold; the docs surfaces respect this by calling it "handoff file". The HN body breaks ranks. Two voices.
- `launch-kit-2026.md:151, 168, 184` X thread also uses `AIT_CONTEXT_FILE` in three tweets. Same issue.
- `launch-kit-2026.md:506-516` admits three demo recordings are blockers. **Launch blocker, correctly flagged.**

## 5-minute path stopwatch

Walking `getting-started.md.draft` as a first-time user with a fresh terminal:

1. **Step 1 (install, ~45s).** `pipx install ait-vcs` (~30s on a warm cache, ~60s cold). `ait --version` (~1s). User stops to verify the output matches the expected `ait 1.0.0`. **Fine.**
2. **Step 2 (init, ~25s).** `cd your-repo` then `ait init`. The expected output block at `getting-started.md.draft:38-50` is helpful. **Friction:** the "Next: exec $SHELL" instruction is in prose at line 54, not in a fenced command. **A user who skims will skip it and pay for it in step 3.** Add ~30s of debugging when they don't.
3. **Step 3 (run agent, ~2-4 min).** "Refactor the auth module" against an unknown repo is the worst step. Either the agent does nothing useful (Claude refuses, no auth module exists), or it does something *too* useful (rewrites half the repo for the demo). **A real user pauses here for ~60s figuring out whether to use a safe demo prompt.** Replace with `"Add a TODO comment to README.md"` — completes in 10-15s, produces a tiny visible diff. New step 3: ~30s.
4. **Step 4 (inspect, ~30s).** `ait status` and `ait attempt show latest` — clean. **Fine.**
5. **Step 5 (apply, ~10s).** Single command. **Fine.**

**Realistic 5-minute path with current draft: 4:30-7:00.** With the two fixes (hoist `exec $SHELL`, swap demo prompt): **2:30-3:30.** The 5-minute claim survives only with edits.

Moments a real user would stop and Google something:
- `getting-started.md.draft:60` after `claude -p --permission-mode bypassPermissions` runs against a real repo. ("What did it just edit?")
- `getting-started.md.draft:174` "`Bypass detection: bypass_risk`" — if this appears, user Googles "ait bypass_risk" rather than reading the next paragraph. Promote `direnv allow` to a bullet.

## "When NOT to use AIT" honesty test

The four-bullet block at `why-ait.md.draft:78-106` is the strongest move in the rebrand.

- **Persona 1 reaction:** *"This is the first README in six months that admits its review tool doesn't have benchmark numbers. I trust everything else here more."* **Honesty wins.**
- **Persona 2 reaction:** *"'AIT is not a multi-agent team' is exactly the line I was about to push back on. Pre-empting that is professional."* **Honesty wins.**
- **Persona 3 reaction:** *"'Alpha, not production-ready' as a heading instead of a footer — I'll still install on a personal repo, but I'll wait six months before I put it on the work box. Which is correct."* **Honesty wins — and correctly self-selects audience.**

No persona is scared off. All three explicitly trust the rest of the doc more after reading this block. The risk was that honesty loses readers; in practice it earns the right to make the three positive claims.

**Caveat:** the block lives only in `why-ait.md.draft`. The README's "What ait does not do" at `README.md.draft:89-94` is shorter and less direct. Promote the four-bullet version to the README too — Persona 1 is unlikely to click through to `why-ait`.

## Chinese surface nativeness

**Mostly native, three sentences read as translated.**

Translated-sounding sentences and native rewrites:

1. `README.zh-TW.md.draft:53` —
   > 下一次跑 agent——Codex、Aider、Gemini、Cursor，任何能被 `ait run --adapter <name>` ([`src/ait/cli/run.py`](src/ait/cli/run.py)) 包住的 CLI——都會收到一份 `AIT_CONTEXT_FILE`，內容由 [`src/ait/context_manifest.py`](src/ait/context_manifest.py) 從過去 attempts 與 notes 組出來：prompt、diff、findings、決定。

   Native rewrite: *下一次跑 agent 時（Codex、Aider、Gemini、Cursor 都行，只要走 `ait run --adapter <name>`），會拿到一份 handoff 檔案，裡面是過去 attempt 整理出來的 prompt、diff、findings、決定。檔案怎麼組看 `src/ait/context_manifest.py`。* Splits the 100-char clause, drops the redundant em-dash break.

2. `site-docs/zh-TW/index.md.draft:14-17` —
   > `ait` 包住你已經在用的 agent CLI。下一個 agent 透過 handoff 檔案收到前一個 agent 留下的決定。

   "透過 handoff 檔案收到" is direct English word order. Native rewrite: *`ait` 把你已經在用的 agent CLI 包起來。下一個 agent 開檔案就讀得到前一個 agent 留下的決定。*

3. `site-docs/zh-TW/index.md.draft:91-93` —
   > Alpha。每天在真實 repo 上 dogfood。Metadata 是單機的，存在 `.ait/`。

   "Metadata 是單機的" reads English-first. Native: *Metadata 只留在這台機器上，存在 `.ait/`*。

Otherwise the Chinese drafts read native — `README.zh-TW.md.draft:28` "多 agent 寫 code 真正卡住的，不是模型不夠強" is a strong native sentence Persona 1's Chinese-reading sibling would post on Threads.

The Chinese launch posts at `launch-kit-2026.md:455-500` are native and tonally consistent with the README — `launch-kit-2026.md:499` "歡迎拆。" is the right register.

## Cross-surface voice consistency

Three voices appear:

1. **Docs voice (README, index.md, why-ait.md, getting-started.md).** Calm, demo-heavy, source-path-cited. **On brand.**
2. **HN voice (`launch-kit-2026.md:22-62`).** Same register as docs. Uses `AIT_CONTEXT_FILE` above the fold, breaking the bible's rule at `ait-power-user-narrative-2026.md:126`. **Off-brand on terminology.**
3. **X voice (`launch-kit-2026.md:118-227`).** Tighter, near-on-brand. But Tweet 3 at line 149 says "Codex opens the same repo and receives AIT_CONTEXT_FILE instead of starting from zero." Same `AIT_CONTEXT_FILE` issue.

**Off-brand line to fix:**
> `launch-kit-2026.md:32` — "Codex receives `AIT_CONTEXT_FILE`, assembled by `src/ait/context_manifest.py`..."

Rewrite to match docs surfaces:
> "Codex receives a handoff file (`AIT_CONTEXT_FILE` to the wrapped process), assembled from prior attempts and notes."

Reddit r/ClaudeAI and r/LocalLLaMA bodies are tonally close to the README and stay on-brand. The Chinese mini-thread is on-brand.

## Top 5 changes that would most improve power-user conversion

1. **Fix the hero asset.** Replace `docs/assets/ait-cross-agent-handoff-placeholder.png` (referenced at `README.md.draft:31`) with the recorded gif or commit to the three-pane static fallback from `ait-power-user-narrative-2026.md:169-170`. A launch README with `placeholder` in a filename costs ~20% of skim conversions. **Blocker.**

2. **Promote "Nothing leaves your machine" above the fold on the README and `index.md`.** Persona 3 doesn't reach it until paragraph 4. Add as the second line of the subhead block at `README.md.draft:7` or as a one-line callout below the install snippet.

3. **Fix the 5-minute path.** Two edits to `getting-started.md.draft`:
   - Line 54: hoist `exec $SHELL` into its own fenced block.
   - Line 60: swap "Refactor the auth module" for a guaranteed-safe demo prompt like `"Add a TODO comment to README.md saying we tried ait"`. Cuts real-user time from 5-7 min to 2-3 min.

4. **Resolve the `AIT_CONTEXT_FILE` vs. "handoff file" inconsistency across launch kit.** Pick the docs version (handoff file, with `AIT_CONTEXT_FILE` as a parenthetical) and apply to `launch-kit-2026.md:32, 149, 168, 184, 276, 386, 473`. Persona 2 will Google the inconsistency.

5. **Promote the four-bullet "When NOT to use AIT" to the README.** Currently only in `why-ait.md.draft:78-106`. The README's `README.md.draft:89-94` version is shorter and weaker. Honesty earns trust from all three personas; don't bury it one click away.

---

**Word count:** ~2,180.
