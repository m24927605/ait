# ait SEO Implementation Plan

Author: team-lead (synthesized from Staff-level audits)
Date: 2026-05-04
Iteration: 4 (post Codex Plan-gate review × 4)
Scope: this is **both** the strategic positioning record **and** the
execution plan for SEO work in this branch and the next two
weeks. Concrete shell commands and gate scripts live in
[`docs/release-checklist.md`](release-checklist.md); this document
points to them by section.

## 1. Strategic positioning

`ait` is alpha, one star, one maintainer, no marketing budget. The
SEO target is therefore not classical Google traffic. It is:

1. **Entity authority** so Google KG and AI search treat `ait` as
   a legitimate developer-tool entity.
2. **LLM citation worthiness** when developers ask AI assistants
   for "AI agent VCS" or "git provenance for Claude Code".
3. **Mid-funnel long-tail capture** in the three lanes we can win
   — `git worktree + AI agent`, `agent provenance / local-first`,
   `cross-agent handoff`. Do not chase head terms.
4. **Compounding multi-channel** — PyPI + npm + GitHub + docs +
   LLMs + awesome-lists.

## 2. Cross-domain decisions (ratified)

1. **Canonical entity sentence (L)** — "Git-native version control
   layer for AI coding agents". Single source flows from
   `mkdocs.yml site_description` into JSON-LD `description` via
   Jinja inheritance.
2. **Alpha disclosure** — keep the word in README Status; remove
   the visual hero badge. Honest text without prominence-driven
   churn.
3. **AI bot policy** — `robots.txt` allows GPTBot, ClaudeBot,
   PerplexityBot, Google-Extended, Anthropic-AI, cohere-ai,
   Applebot-Extended.
4. **Comparison pages** — vs naked git-worktree (P0; shipped) →
   vs Aider auto-commits → vs Claude Code built-in worktrees → vs
   SaaS observability.
5. **Homepage URL on registries** —
   `https://m24927605.github.io/ait/` (verified live).
6. **zh-TW investment** — full translation P2. `hreflang="zh-TW"`
   emitted **only** for pages with an actual zh-TW translation;
   `overrides/main.html` excludes `/facts/` and `/compare/` paths
   conditionally. Adding a new untranslated section requires
   updating that exclusion (see §10 Risks).
7. **GitHub Sponsors / `FUNDING.yml`** — deferred until Sponsors is
   enabled. Closed.
8. **`CITATION.cff`** — shipped at repo root with placeholder
   author name and an in-file `NOTE`. Verification is a **hard
   pre-publish gate** in §6 below; the next tagged release blocks
   on it.
9. **JSON-LD drift** — `softwareVersion` omitted; variable fields
   inherit from `mkdocs.yml`. Eight-check SEO Drift Audit lives in
   [`docs/release-checklist.md`](release-checklist.md).

## 3. Canonical messaging architecture

| Length | Chars | Surfaces (audit list — see §7 baseline) |
| ------ | ----- | --------------------------------------- |
| L (~280) | "ait is a Git-native version control layer for AI coding agents (Claude Code, Codex CLI, Aider, Gemini CLI, Cursor) — adding worktree isolation, attempt provenance, cross-agent memory, and reviewable promotion on top of Git. Open source (MIT), Python 3.14+, dependency-free, no SaaS, no telemetry." | README hero, PyPI long_description, llms.txt blockquote, JSON-LD `description`, `mkdocs.yml site_description`, facts.md lead |
| M (~134) | "Git worktree isolation and provenance for AI coding agents — wraps Claude Code, Codex, Aider, Gemini CLI, Cursor. MIT, Python, no SaaS." | `pyproject.toml description`, `npm/ait-vcs/package.json description`, og:description fallback |
| S (~52) | "Worktree isolation & provenance for AI coding agents" | GitHub repo `description`, og:title fallback |
| XS (~30) | "Git layer for AI coding agents" | Twitter/X bio (maintainer manual), social embeds |

The Twitter/X bio surface is a maintainer-manual update. It is in
the §7 launch checklist below, not automatable from this branch.

## 4. P0 — code-complete in this branch

Each row links to its verification gate in §6.

| Item | File(s) | Gate |
| ---- | ------- | ---- |
| Canonical L applied to `mkdocs.yml site_description` | `mkdocs.yml` | G1 |
| Canonical L on README hero | `README.md` | G1 |
| Canonical M on `pyproject.toml description` | `pyproject.toml` | G2 |
| Canonical M on `npm/ait-vcs/package.json description` | `npm/ait-vcs/package.json` | G3 |
| Classifiers expanded 6 → 18; `[project.urls]` extended | `pyproject.toml` | G2 |
| npm `os`/`cpu`/`preferGlobal`/`publishConfig`/`keywords` | `npm/ait-vcs/package.json` | G3 |
| og:image, twitter `summary_large_image`, og:locale, conditional hreflang, robots meta, JSON-LD (`SoftwareApplication`+`SoftwareSourceCode`+`WebSite` on home; `BreadcrumbList` on inner) | `overrides/main.html` | G4, G5 |
| `llms.txt` published with canonical L blockquote and link manifest | `site-docs/llms.txt` | G6 |
| AI bots Allow | `site-docs/robots.txt` | G7 |
| `SECURITY.md` at repo root | `SECURITY.md` | G8 (manual) |
| `CITATION.cff` with NOTE | `CITATION.cff` | G9 (validator) |
| `mkdocs.yml` features + nav extension + `i18n.fallback_to_default` | `mkdocs.yml` | G4 (build) |
| README structural rewrite: hero, badges trim, Compared section, Documentation repoint | `README.md` | G4 (build) |
| `compare/git-worktree-naked-vs-ait.md` (1480 words; content-seo delivered) | `site-docs/compare/git-worktree-naked-vs-ait.md` | G4 |
| `facts.md` 15 Q&A + FAQPage JSON-LD | `site-docs/facts.md` | G4, G10 |
| `og-default.png` 1200×630 (rsvg-convert from svg) | `site-docs/assets/og-default.{svg,png}` | G11 |
| Release checklist SEO Drift Audit section | `docs/release-checklist.md` | (this is the gate, no separate test) |
| `site/` build output ignored | `.gitignore` | G4 |

## 5. Deployment & external launch — ordered sequence

Deploy in this order. Do not skip checkpoints.

1. **Land local commits to `main`.** Push triggers
   `.github/workflows/docs.yml` GitHub Pages deploy and (separately)
   the release smoke jobs.
2. **Verify Pages build** (≤ 10 min after push):
   `curl -fsSI https://m24927605.github.io/ait/llms.txt`,
   `curl -fsSI https://m24927605.github.io/ait/facts/`,
   `curl -fsSI https://m24927605.github.io/ait/compare/git-worktree-naked-vs-ait/`,
   `curl -fsSI https://m24927605.github.io/ait/assets/og-default.png`.
   All must return `200 OK`. Do **not** advance to step 3 until
   this passes — pointing the GitHub repo homepage at a 404 is
   worse than the current state.
3. **Update GitHub repo metadata** (one command):
   ```bash
   gh repo edit m24927605/ait \
     --description "Worktree isolation & provenance for AI coding agents" \
     --homepage "https://m24927605.github.io/ait/"
   ```
4. **Apply final 20-topic set** (cap = 20). Drop `ai`, `cli`,
   `coding-agents`, `provenance`. Add `agent-harness`,
   `code-provenance`, `agentic`, `coding-assistant`. Final list:
   `agent-harness`, `agent-isolation`, `agentic`, `ai-agents`,
   `ai-coding`, `ai-tools`, `aider`, `claude-code`,
   `code-provenance`, `codex`, `coding-assistant`, `cursor`,
   `developer-tools`, `gemini-cli`, `git`, `git-worktree`,
   `llm-agents`, `python`, `vcs`, `worktree`. Apply with:
   ```bash
   for t in ai cli coding-agents provenance; do
     gh repo edit m24927605/ait --remove-topic "$t"; done
   for t in agent-harness code-provenance agentic coding-assistant; do
     gh repo edit m24927605/ait --add-topic "$t"; done
   ```
   Verify:
   `gh repo view m24927605/ait --json repositoryTopics |
   python3 -c "import sys,json; t=[t['name'] for t in json.load(sys.stdin)['repositoryTopics']]; assert len(t)==20 and 'agent-harness' in t and 'ai' not in t, t; print('topics OK')"`.
5. **Upload GitHub social preview** (web UI only): Settings →
   Social preview → Edit → upload
   `site-docs/assets/og-default.png`. Verify by sharing the repo
   URL into a fresh tab; Twitter card validator / LinkedIn
   inspector / Facebook debugger refresh OG cache.
6. **Update Twitter/X bio** (maintainer manual) to canonical XS:
   "Git layer for AI coding agents". Verify on profile page.
7. **Submit `ait` to `bradAGI/awesome-cli-coding-agents`**
   (P1 follow-up; PR procedure in §11 below).

## 6. Verification gates (G1-G11)

Implementation-level gates run by the maintainer (and CI where
applicable). Each refers to an exact command or workflow.

* **G1 (canonical-L sync)** — `docs/release-checklist.md` SEO
  Drift Audit, items 1, 4, 5, 6, 7. `mkdocs.yml site_description`,
  README hero, `llms.txt` blockquote, JSON-LD `description` (via
  inheritance), facts.md lead all hold the same string.
* **G2 (PyPI metadata)** — release-checklist Tagged Release items
  7-8 (`python -m build` + `python -m twine check dist/*`).
  Prereq: `python3 -m pip install --user build twine` (one-time).
* **G3 (npm metadata)** — release-checklist Tagged Release item
  10 (`(cd npm/ait-vcs && npm pack --dry-run)`); the
  parenthesized subshell form is canonical because `npm pack
  --prefix` resolves the wrong `package.json` from this repo
  layout.
* **G4 (docs build)** —
  `cd <repo> && python3 -m mkdocs build --strict`. Required green
  before any push that changes `mkdocs.yml`, `site-docs/**`, or
  `overrides/**`. CI runs the same in
  `.github/workflows/docs.yml`.
* **G5 (JSON-LD validity)** — local check that flattens `@graph`
  and asserts required types:
  ```python
  import json, re, pathlib
  html = pathlib.Path('site/index.html').read_text()
  blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
  parsed = [json.loads(b) for b in blocks]
  flat = [o for p in parsed for o in (p.get('@graph') if isinstance(p, dict) and '@graph' in p else [p]) if isinstance(o, dict)]
  types = {o.get('@type') for o in flat}
  assert {'SoftwareApplication','SoftwareSourceCode','WebSite'} <= types, types
  ```
  Manual fallback: <https://search.google.com/test/rich-results>
  on the deployed home URL.
* **G6 (`llms.txt` link manifest)** —
  `for u in $(grep -oE 'https://[^)]+' site-docs/llms.txt | sort -u); do curl -fsSI "$u" >/dev/null || echo "FAIL: $u"; done`.
  No `FAIL` lines.
* **G7 (robots.txt AI bots)** —
  `grep -cE '^User-agent: (GPTBot|ClaudeBot|PerplexityBot|Google-Extended|Anthropic-AI|cohere-ai|Applebot-Extended)$' site-docs/robots.txt`
  → `7`.
* **G8 (`SECURITY.md`)** — manual: GitHub renders the file at
  `https://github.com/m24927605/ait/security/policy` with no
  formatting errors.
* **G9 (`CITATION.cff`)** — `python3 -c "import yaml; yaml.safe_load(open('CITATION.cff'))"`
  exits 0; **and** the in-file `NOTE` is removed only after the
  maintainer confirms author name. The NOTE removal is a hard
  prerequisite of the next PyPI release (item ① of release
  checklist Tagged Release). The release-checklist SEO Drift Audit
  item 8 enforces version match (which itself blocks until NOTE
  is resolved at v0.55.40 or later).
* **G10 (FAQPage schema)** — count Q&A in `facts.md`:
  `python3 -c "import re,pathlib; n=len(re.findall(r'^### Q:', pathlib.Path('site-docs/facts.md').read_text(), re.M)); assert n>=15, n"`.
  FAQPage JSON-LD parses (covered by G5 on the facts page after
  build).
* **G11 (og-default.png)** — `file site-docs/assets/og-default.png`
  reports `PNG image data, 1200 x 630, 8-bit/color RGB`; size
  < 1 MiB (`stat -f %z` on macOS, `stat -c %s` on Linux).

## 7. Pre-launch baseline capture

Before pushing any of §5, capture the current state in a local
file (`/tmp/ait-seo-baseline-$(date +%Y%m%d).txt`) so later trend
claims are meaningful:

* GitHub stars: `gh repo view m24927605/ait --json stargazerCount`.
* Repo description, topics, homepage:
  `gh repo view m24927605/ait --json description,homepageUrl,repositoryTopics`.
* PyPI weekly downloads: `pip index versions ait-vcs` (best-effort)
  and the count from `https://pypistats.org/api/packages/ait-vcs/recent`.
* npm weekly downloads:
  `https://api.npmjs.org/downloads/point/last-week/ait-vcs`.
* Google indexed pages (manual): `site:m24927605.github.io/ait`
  on Google.
* Schema validator state on home: `https://validator.schema.org/`.
* GSC impressions/clicks (last 28 days), if access exists.

These are observation snapshots. They do not gate launch; they
exist so monthly KPIs (§8) have a starting line.

## 8. Measurement

| Layer | Frequency | Indicator | Acceptance |
| ----- | --------- | --------- | ---------- |
| Discovery | weekly | GSC impressions/clicks/CTR; index coverage; npm + PyPI weekly downloads; GitHub stars; referring domains | trend metrics — no fixed pass/fail; baseline in §7 |
| Lab performance | per-build | Lighthouse SEO + CWV-lab via local CLI | Lighthouse SEO ≥ 95; LCP < 2.5s, CLS < 0.1, INP < 200ms in **lab** |
| Entity authority | monthly | "ait-vcs" SERP positions; KG panel; schema validator | first three SERP results owned; validator returns no errors |
| Field CWV | monthly | CrUX dataset | tracked when CrUX has data; not a release gate |
| LLM citation | monthly (manual prompt panel) | 4 engines × 10 prompts; honeypot canary in `llms-full.txt` | honeypot returns ≥ 1 engine by month 3; citation rate ≥ 25% by month 3, ≥ 60% by month 6 |

## 9. P1 — week 2

Each item carries its own gate.

| Work | Gate |
| ---- | ---- |
| Submit `ait` to `bradAGI/awesome-cli-coding-agents` | upstream PR merged, or feedback received |
| `.github/workflows/docs.yml` — pip cache + link-check step | CI green; link-check finds 0 broken |
| `llms-full.txt` < 8000 chars | `wc -c` < 8000; G6-style URL check |
| PyPI long_description above-the-fold install snippet | `python -m readme_renderer dist/*.tar.gz` ok |
| `CITATION.cff` author name verified; NOTE removed | G9 with NOTE-absent assertion; release-checklist item 8 |

## 10. P2 — weeks 3-6

Comparison pages 2-4; use-case pillars `parallel-agents.md`,
`agent-provenance.md`; HowTo pages `rollback-claude-code.md`,
`multi-agent-handoff.md`; feature pillar `queryable-attempts.md`;
`CODE_OF_CONDUCT.md`; zh-TW translation of `facts.md` and
`compare/*` (then drop the `overrides/main.html` exclusion list);
self-hosted fonts; sitemap real `git log` mtime; additional
awesome-list submissions; honeypot string + monthly LLM prompt
panel.

Every new content page added in P2 must:
* satisfy G4 (build green),
* satisfy G6 if it adds links to `llms.txt`,
* update the `overrides/main.html` exclusion list **before** merge
  if it is not yet zh-TW translated, and
* add an entry to `mkdocs.yml` nav with appropriate
  `nav_translations` for zh-TW when applicable.

## 11. P3 — gating on v1.0

Hacker News Show; Wikidata entity application; per-page automated
`og:image` (GH Actions + Playwright); HowTo schema on
getting-started; GitHub Sponsors enable + `FUNDING.yml`.

## 12. Risks

* **Schema bloat** — limit JSON-LD types to
  `SoftwareApplication`, `SoftwareSourceCode`, `WebSite`,
  `BreadcrumbList`, `FAQPage`. No `HowTo` until v1.0.
* **Awesome-list rejection** — alpha + 1 star may bounce.
  Lead with bradAGI (lower bar).
* **Maintainer bandwidth** — zh-TW writing, dev.to posts, HN
  timing all need sustained creative bandwidth. Stay P2/P3.
* **README maintenance overhead** — richer README means more
  drift. Long-term: trim, push depth into docs site.
* **Conditional hreflang brittleness** — `overrides/main.html`
  excludes `/facts/` and `/compare/` paths. P2 work to ship zh-TW
  translations and remove the list. Near-term guard: §10
  acceptance row that any new untranslated page must update the
  exclusion before merge.

## 13. References

The four underlying Staff audits are stored in the team's task
list at `~/.claude/tasks/ait-seo-staff/`. Audit deliverables
covered Technical SEO (JSON-LD, hreflang, CWV, workflows),
Content SEO (keyword universe, comparison pages, FAQ outline,
README rewrite, zh-TW differentiation), Developer Registry SEO
(PyPI classifiers, npm fields, GitHub topics, awesome-list
targets), and GEO/AEO (`llms.txt`, facts page outline, AI search
ranking signals, README fact-dense lead, entity SEO).

This document is a living plan. Re-read quarterly; revise as KPIs
land. Codex Plan-gate review history: iter 1-3 caught file
ordering, JSON-LD drift, hreflang fallback, dimension
inconsistency; iter 4 prompted §6 verification gate mapping and
§5 deployment ordering.
