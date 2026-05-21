# AIT Rebrand QA — Brand Consistency Audit

**Status:** NEEDS WORK

Phase 2 drafts are broadly consistent with the bible (hero, pain order, demos, banned phrases all clean). Three drifts must be fixed before merge: getting-started.md.draft has no "alpha" disclosure, the r/LocalLLaMA pain list silently drops pain 3 (memory), and the ZH install-snippet comment wording diverges between README and docs index.

## Hero-line consistency

| Surface | EN/ZH hero location | Matches bible? |
|---|---|---|
| README.md.draft:5 (EN) | Verbatim | Y |
| README.zh-TW.md.draft:5 (ZH) | Verbatim | Y |
| site-docs/index.md.draft:2 title, :9 H1 | Verbatim | Y |
| site-docs/why-ait.md.draft | No hero (explainer) | N/A |
| site-docs/getting-started.md.draft | No hero (tutorial) | N/A |
| site-docs/zh-TW/index.md.draft:2 title, :9 H1 | L2 title drops trailing 「。」; L9 H1 has it | Y (title-frontmatter convention) |
| launch-kit:23 HN body, :119 Tweet 1, :242 r/ClaudeAI, :351 r/LocalLLaMA, :458 Threads ZH | All bible verbatim | Y |
| launch-kit:345 r/LocalLLaMA title | "One agent writes, another reviews" — comma, lowercase, third clause dropped (title compromise) | N |

Heroes are clean across all body copy.

## Pain-point order consistency

Bible order: (1) multi-agent communication, (2) adversarial review, (3) shared + long-term memory.

| Surface | Order matches bible (multi-agent → review → memory)? |
|---|---|
| README.md.draft:52, :60, :68 | Y — bible-verbatim H3 headers |
| README.zh-TW.md.draft:49, :61, :84 | Y — explicit pillar tags 「(多 agent 之間能交接)」「(對抗式審查)」「(共同 + 長期記憶)」 |
| site-docs/index.md.draft:42, :53, :69 | Y — pillar framing (hands work / reviews diff / remembers decisions) |
| site-docs/why-ait.md.draft:18, :38, :57 | Y — bible-verbatim |
| site-docs/zh-TW/index.md.draft:42, :52, :66 | Y |
| launch-kit:30, :37, :44 HN body | Y — Pillar 1/2/3 cross-agent / review / memory |
| launch-kit:144, :159, :176 X thread | Y |
| launch-kit:254–266 r/ClaudeAI pain list | Y — bible-verbatim |
| launch-kit:371–377 r/LocalLLaMA "what burned me" | **N — pain 3 (memory) silently dropped, replaced by cloud/SaaS framing** |

**Note:** The r/LocalLLaMA "what AIT adds" block (L383–414) does cover all three pillars including memory, in correct order. Drift is in the preceding "what burned me" list — it replaces pain 3 with cloud-skepticism. Bible Section 2 mandates the three-pain set; pain 3 cannot be dropped.

## Banned-phrase scan

### "catches bugs" / "catches every bug" / "catches what the implementer missed"

- `README.md.draft:94` — "No published benchmark proving the reviewer **catches bugs the implementer missed**." (Negated denial, matches bible "Would not say" disclosure — passes.)
- `site-docs/why-ait.md.draft:82` — "AIT does not promise the reviewer **catches every bug**." (Negated denial — passes.)
- `docs/launch-kit-2026.md:98` — "So I won't claim the reviewer **catches bugs the implementer missed** — I don't have the corpus to back that up yet." (Negated denial in HN top-comment template — passes.)

All occurrences are explicit denials per bible Section 6. Clean.

### "as a team" / "multi-agent team" / "they collaborate" / "agents collaborate"

- `site-docs/why-ait.md.draft:89` — "AIT is **not a multi-agent team**." (Negated denial per bible Section 6, banned claim 2 — passes.)

No positive uses anywhere. Clean.

### "production-ready" / "production ready" / "ready for production"

- `site-docs/why-ait.md.draft:94` — "AIT is alpha, **not production-ready**." (Negated denial — passes.)
- `site-docs/index.md.draft:38` — "a hardened production tool" (in the "When NOT to use AIT" row, framed as what AIT is NOT — passes.)
- `site-docs/zh-TW/index.md.draft:38` — "穩定的 production 工具" (parallel ZH wording in the "不適合 AIT 的情境" row — passes.)

Clean.

### "surfaces the right context" / "never lose a decision" / "always finds"

Clean across all seven surfaces.

### "Git workflow layer" / "Git safety layer" / "control plane" / "sandbox" / "federated memory" / "unleash" / "supercharge" / "AI revolution"

Clean across all seven surfaces.

All four banned-claim sweeps return clean: every "banned" hit is an explicit denial that the bible Section 6 mandates.

## Demo-link order consistency

Bible order: hero `07-cross-agent-handoff/` → second `09-1-codex-reviewer/` → third `04-memory-reuse/`. `01-blast-radius/` below the fold or omitted.

All surfaces follow 07 → 09-1 → 04 in this order: README.md.draft:33/58/66/74; README.zh-TW.md.draft:59/82/96; site-docs/index.md.draft:51/67/84; site-docs/why-ait.md.draft:36/55/76; site-docs/zh-TW/index.md.draft:50/64/80; launch-kit:35/42/48 (HN), Tweet 3/4/5 (X), :278/:291/:302 (r/ClaudeAI), :388/:402/:414 (r/LocalLLaMA), Threads ZH Posts 2 + 3. All **Y**.

site-docs/getting-started.md.draft:121 links 07 only (in "Next steps"); reviewer and memory steps describe but don't link a demo — partial coverage, acceptable for tutorial.

`01-blast-radius/` does not appear as hero anywhere — bible compliance.

## Install snippet consistency

Bible verbatim:

```bash
pipx install ait-vcs      # or: npm install -g ait-vcs
cd your-repo
ait init
claude ...                # codex / aider / gemini / cursor work the same way
ait status
ait apply latest
```

| Surface | Diff vs bible |
|---|---|
| README.md.draft:38, site-docs/index.md.draft:20, launch-kit:52/:309/:421 | Exact match |
| README.zh-TW.md.draft:33 | ZH localization: `# 或: npm install -g ait-vcs` (with colon), `# codex / aider / gemini / cursor 接法都一樣` |
| site-docs/zh-TW/index.md.draft:20 | ZH localization: `# 或 npm install -g ait-vcs` (no colon), `# codex / aider / gemini / cursor 用法一樣` — **diverges from README ZH; pick one** |
| site-docs/why-ait.md.draft | No install snippet (explainer page) |
| site-docs/getting-started.md.draft:16 | Stepwise tutorial install, not the verbatim card. By design |
| launch-kit:217 X Tweet 8, :492 Threads Post 3 | Drops both comment lines (char budget). Acceptable |

**Drift to fix:** ZH README and ZH docs index disagree on the snippet comments. Pick one ZH localization and use it in both.

## Cross-surface tone parity

- README.md.draft:5–7 — bible hero + bible subhead. Linear/Vercel cadence, calm, no slogans.
- README.zh-TW.md.draft:5–7 — bible ZH hero + bible ZH subhead. Native ZH voice, parallel cadence.
- site-docs/index.md.draft:9–12 — bible hero + bible subhead verbatim. Identical tone.
- site-docs/why-ait.md.draft:9–13 — "Three pains hit every engineer running multiple agent CLIs against the same repo." Explainer follow-up, slightly higher density. Within voice.
- site-docs/getting-started.md.draft:9–11 — "One linear path. Five minutes to read and run." Tutorial voice. On-brand.
- site-docs/zh-TW/index.md.draft:9–17 — ZH hero + ZH three-pillar paragraph. Parallel to EN docs index.
- launch-kit:23 — bible hero verbatim. Three-pillar walk-through cadence holds across the 1,820-char body.

All seven surfaces sound like the same product. HN body and docs index are closest in tone (both code-block-led). README hero is more visually dense (badges, HTML alignment) but the voice underneath matches. No surface drifts toward marketing-speak; none drifts toward over-jargonized plumbing.

## Chinese-English structural parity

README EN vs README ZH: Hero, subhead, three-pillar paragraph, install, three pains, differentiation table, status, install (full), links. **EN and ZH parallel.** ZH expands the explainer paragraph (L28) slightly; acceptable.

Docs index EN vs ZH: Both follow title → H1 hero → subhead → three-pillar paragraph → install → "What AIT adds" table (with "When NOT to use AIT" row) → three pillars (H3 each) → "After a week of use" graph callout → Status → links. **Section-for-section parity.** Same pillar names, same demos (07 / 09-1 / 04) in the same order. No structural divergence.

## Alpha-disclosure check

Bible Section 6 mandate: "alpha" appears in the body, not buried in a footer.

| Surface | First "alpha" line | Position vs install | Passes? |
|---|---|---|---|
| README.md.draft | :140 Status header, :142 body | Below install (:38), body-level Status section | Y |
| README.zh-TW.md.draft | :230 Status section, :232 body | Below install (:33), body-level | Y |
| site-docs/index.md.draft | :38 in "When NOT to use AIT" table row, :95 Status | Below install (:20) but in body, in diff table on first scroll | Y |
| site-docs/why-ait.md.draft | :94 in "When NOT to use AIT" body | No install on page; alpha in explainer body | Y |
| site-docs/getting-started.md.draft | **Not present anywhere** | — | **N — must fix** |
| site-docs/zh-TW/index.md.draft | :38 差異化表, :91 Status | Below install (:20) but in body | Y |
| launch-kit-2026.md | :59 HN, :106 HN comment, :202 Tweet 7, :319 r/ClaudeAI, :499 Threads ZH | Every post body has in-body alpha | Y |

**Critical:** `site-docs/getting-started.md.draft` has zero occurrences of "alpha". The page is the canonical onboarding path — a new user reads all 178 lines without learning the product is alpha. Bible Section 6 violation.

## Critical drift findings (must fix)

1. **`site-docs/getting-started.md.draft` is missing the "alpha" disclosure entirely.** Bible Section 6 mandates "alpha" in body across every surface. A reader can complete the five-minute path with no signal that the product is alpha quality. Fix: add a one-sentence note in section 5 ("Apply (or recover)") or above the "Next steps" header, e.g. "AIT is alpha — `.ait/` is single-machine, no cross-machine sync."

2. **`docs/launch-kit-2026.md` r/LocalLLaMA "what burned me" list (L371–377) drops pain 3 (memory).** The list runs cloud → multi-agent → review and stops, even though the "what AIT adds" section below correctly covers all three pillars including memory. Bible Section 2 mandates the three-pain set in order. Fix: add a fourth bullet for the memory pain, or restructure to keep the bible's three pains and demote "cloud" to context framing.

## Approved-with-fixes findings (should fix)

- **ZH install-snippet comments diverge between `README.zh-TW.md.draft:33` (`# 或: npm install -g ait-vcs`, `# codex / aider / gemini / cursor 接法都一樣`) and `site-docs/zh-TW/index.md.draft:20` (`# 或 npm install -g ait-vcs`, `# codex / aider / gemini / cursor 用法一樣`).** Pick one ZH localization (recommend matching README ZH: `# 或:` with colon, `接法都一樣`) and apply to both.

- **`docs/launch-kit-2026.md` r/LocalLLaMA title (L345)** reads "One agent writes, another reviews" — comma instead of period, third clause dropped. The Reddit body (L351) restores the full bible hero. Title compromise is acceptable but flag for orchestrator review.

- **`docs/launch-kit-2026.md` Tweet 1 subhead (L122–123)** paraphrases the bible subhead: "Every run becomes an attempt" vs bible "Every agent run is an attempt"; "review" vs "review findings"; "queryable" vs "queryable from the CLI". Within Twitter char budget but consider tightening to bible verbatim if 280-char budget allows.

- **`README.md.draft` hero `<img>` placeholder** (L31) points to `docs/assets/ait-cross-agent-handoff-placeholder.png`. **`README.zh-TW.md.draft`** (L21) still points to `docs/assets/ait-cross-agent-session.gif` (the legacy "advisory analysis" capture per launch-kit L510). EN and ZH should point at the same hero asset path post-recording.

## Approved as-is

- `site-docs/index.md.draft` — hero verbatim, demos in bible order, alpha in body (first mention in the diff table above the fold), structurally parallel to ZH counterpart.
- `site-docs/why-ait.md.draft` — three pains in bible order with bible-verbatim headers, "When NOT to use AIT" section directly implements bible Section 6 banned-claim disclosures, no install snippet by design.
- `site-docs/zh-TW/index.md.draft` — hero verbatim, ZH parallel to EN docs index section-for-section, alpha in body.
- `README.md.draft` — hero verbatim, three pains in bible order, demos in bible order, no banned-phrase positive uses, alpha in Status section.
- `README.zh-TW.md.draft` — hero verbatim, three pains in bible order (with explicit "(多 agent 之間能交接)", "(對抗式審查)", "(共同 + 長期記憶)" pillar tags matching bible), demos in bible order.
