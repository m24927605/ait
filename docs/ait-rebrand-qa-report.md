# AIT Rebrand QA — Consolidated Report

**Date:** 2026-05-21
**Phase:** 3 — Quality gates complete
**Gate verdicts:** Reality NEEDS WORK · UX NEEDS WORK · Brand NEEDS WORK
**Net verdict:** NEEDS WORK — no BLOCK, but drafts cannot be promoted until the listed fixes land.

Detailed reports:

- `docs/ait-rebrand-qa-reality.md`
- `docs/ait-rebrand-qa-ux.md`
- `docs/ait-rebrand-qa-brand.md`

## Headline

The four Phase 2 drafts hit the positioning bible cleanly (zero banned-claim
leakage), maintain English-Chinese structural parity, and land all three
pillars. They cannot ship because three CLI commands quoted in the drafts do
not actually work and a fourth crashes with a real code bug — and because the
hero asset is a placeholder.

## Critical findings (must fix before promotion)

| # | Source | Finding | Fix |
|---|---|---|---|
| C1 | Reality | `ait query --on attempt 'adapter="..."'` appears in every English/Chinese surface and in the launch kit. `adapter` is not whitelisted in `src/ait/query/fields.py`; the command prints `error: field is not queryable in v1: adapter`. | Replace with the whitelisted form, e.g. `ait query --on attempt 'agent.agent_id="codex-cli"'`. Also fix bible Section 2 (pain 1 defuse). |
| C2 | Reality | `ait attempt show latest` and `ait attempt discard latest` appear in `getting-started.md.draft:89, 104`. They raise `IdResolutionError: no attempt matches: latest` — `latest` is only special-cased for `apply` and `recover`. | Rewrite the getting-started examples to capture an attempt id from `ait status` and use it, or use `ait apply latest` / `ait recover latest` for the demo flow. |
| C3 | Reality | `ait memory sources` (default text mode) crashes with `NameError: _format_live_memory_sources` at `src/ait/cli/memory.py:201`. The getting-started "next steps" recommends running it. | Two-pronged: (a) remove the recommendation from `getting-started.md.draft` until the bug is fixed; (b) file the bug as a real issue against `src/ait/cli/memory.py:201`. |
| C4 | UX | `README.md.draft:31` ships `placeholder.png` as the hero asset. A README launching with a literal "placeholder" filename signals "not ready" to every skimmer. | Record `examples/pain-point-demos/07-cross-agent-handoff/run.sh` to a 12-18s GIF OR commit to the bible's three-pane static fallback (attempt summary + `AIT_CONTEXT_FILE` excerpt + Codex opening turn). Same fix applies to docs index. |
| C5 | Brand | `site-docs/getting-started.md.draft` contains ZERO occurrences of the word "alpha." Bible Section 6 mandates "alpha in the body, not buried." Canonical onboarding hides the alpha posture from new users. | Add a single line near the top of getting-started: "AIT is alpha. Single machine, `.ait/` stays local, expect rough edges." |

## High-priority findings (should fix before promotion)

| # | Source | Finding | Fix |
|---|---|---|---|
| H1 | Brand | `docs/launch-kit-2026.md:371–377` r/LocalLLaMA "what burned me" list silently drops the memory pain and substitutes cloud/SaaS framing. The pillars below still cover memory — surface is internally inconsistent. | Restore pain 3 (cross-session memory) in the burned-me list. Cloud/SaaS framing can live as a fourth bullet, not a replacement. |
| H2 | Brand | `site-docs/zh-TW/index.md.draft:20` and `README.zh-TW.md.draft:33` use two different ZH install-snippet localizations (`# 或:` + `接法都一樣` vs `# 或` + `用法一樣`). | Pick one. Use the README ZH version (`# 或:` + `用法一樣`) for consistency. |
| H3 | UX | `getting-started.md.draft` has `exec $SHELL` glued to a previous block, and the demo prompt "Refactor the auth module" is too destructive for a 5-minute happy-path tutorial. | Hoist `exec $SHELL` to its own block with an explanatory line. Swap the demo prompt to something low-risk, e.g. "add a docstring to the top-level CLI function." |
| H4 | UX | `docs/launch-kit-2026.md` has `AIT_CONTEXT_FILE` and "handoff file" used interchangeably across lines 32, 149, 168, 184, 276, 386, 473. | Pick "handoff file" above the fold in every post; name the env var once per post in body, parenthetically. |
| H5 | UX | Chinese drafts have 3 specific sentences that read as translated rather than native. Specific quotes and rewrites are in `docs/ait-rebrand-qa-ux.md`. | Apply the rewrites from the UX report. |
| H6 | Reality | Python 3.14+ floor is in `pyproject.toml:6` but not flagged in any launch-kit one-liner. `pipx install ait-vcs` will silently fail for the typical contributor running 3.11/3.12. | Add a one-line note to each launch post: "Requires Python 3.14+." Same in README install snippet. |
| H7 | Reality | 7 additional high-priority command/output divergences across drafts (see Reality report § High-priority findings for full list). | Apply each fix as listed in `docs/ait-rebrand-qa-reality.md`. |

## What is clean

- **Banned-claim discipline.** All three gates confirm zero positive uses of the
  four "would not say" claims. Every match for "catches bugs," "as a team,"
  "production-ready," and "surfaces the right context" is an explicit
  negation, exactly as the bible mandates.
- **Hero line consistency.** Every surface uses the bible's EN and ZH hero lines verbatim.
- **Pain-point order.** Every surface lands the three pillars in bible order: multi-agent → review → memory. (Exception: r/LocalLLaMA — see H1.)
- **Pillar parity EN ↔ ZH.** Same pillar names, same demos, same order across languages.
- **Install package name.** `ait-vcs` matches `pyproject.toml:6` and `npm/ait-vcs/package.json`.
- **Reader-question pass rate.** 2.3/3 across three power-user personas. The
  three pillars do land. Differentiation lands for 2 of 3 personas.

## Bonus discovery — real code bug to file

`ait memory sources` (default text mode) crashes with
`NameError: _format_live_memory_sources` at `src/ait/cli/memory.py:201`. This
is a real product bug, not a draft bug. It should be filed as an issue and
fixed independently of the rebrand. The fix is local; the draft just needs to
stop recommending the command until the bug is fixed.

## Demo asset blocker (still open from Phase 2 Track D)

The three hero demos referenced across all surfaces have no in-repo asset:

- `07-cross-agent-handoff` — only the legacy "advisory analysis" GIF exists,
  not the 12-18s recording the bible specifies.
- `09-1-codex-reviewer` — no asset.
- `04-memory-reuse` — no asset.

Three new recordings (or approved static fallbacks) must be produced before
any launch post goes live. C4 covers the README hero; the launch kit asset
plan is a separate workstream.

## Recommended next moves

In severity order:

1. **Phase 4 fix pass** — dispatch targeted agents to apply the C1-C5
   critical fixes plus the H1-H7 high-priority fixes against the draft files.
   Estimated 4 parallel agents (Reality fixes, README/Chinese fixes, docs
   fixes, launch kit fixes), 10-15 min.
2. **File the `ait memory sources` bug** — separate work item, not part of
   the rebrand. Two-line comment fix; root cause likely a renamed helper
   that left a dangling reference.
3. **Record the three hero demos** — out of Phase 4 scope; this needs the
   real machine, real agents, and a recording tool. Plan as a separate
   "launch readiness" workstream.
4. **Update positioning bible** — C1 means the bible itself uses a non-working
   query example in Section 2. Fix the bible first so Phase 4 has a stable
   source.

Until Phase 4 completes, the `.draft` files stay in place; the live README,
README.zh-TW, site-docs hero pages, and launch-kit stay untouched.
