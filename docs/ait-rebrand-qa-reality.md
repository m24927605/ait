# AIT Rebrand QA — Reality Audit

**Status:** NEEDS WORK

Default stance held. Four critical issues will cause the very first command a
reader copies into a terminal to fail or crash. Once those land, the drafts
are close to PASS — banned-claim discipline is clean and the demo paths exist.

## Critical findings (must fix before drafts are promoted)

1. **`ait query --on attempt 'adapter="codex-cli"'` is not a real query.**
   Cited verbatim in `README.md.draft:56`, `README.zh-TW.md.draft:57`,
   `site-docs/index.md.draft:48-50` (implied via pillar 1), `site-docs/why-ait.md.draft:33`,
   `site-docs/zh-TW/index.md.draft` (Pillar 1), `docs/launch-kit-2026.md:34, 149, 277, 387`.
   Counter-evidence: `src/ait/query/fields.py:418-660` enumerates queryable
   fields — `adapter` is not present. Running the command prints
   `error: field is not queryable in v1: adapter`. The legitimate field is
   `agent.agent_id` (`src/ait/query/fields.py:475`). **Proposed fix:** replace
   every occurrence with `ait query --on attempt 'agent.agent_id="codex"'`
   (or `"claude-code"` etc., matching what the runner records).

2. **`ait attempt show latest` and `ait attempt discard latest` raise
   `IdResolutionError`.** Cited in `site-docs/getting-started.md.draft:89, 104`.
   Counter-evidence: `src/ait/idresolver.py:36-67` (`resolve_attempt_id`) does
   exact match then `LIKE %given%`, with no "latest" alias. Confirmed by
   running: `ait.idresolver.IdResolutionError: no attempt matches: latest`.
   Only `ait apply` (`src/ait/cli/apply.py:88`) and `ait recover`
   (`src/ait/recovery.py:44`, `:299`) special-case the literal "latest".
   **Proposed fix:** in getting-started, replace
   `ait attempt show latest` with `ait attempt list --limit 1` followed by
   `ait attempt show <attempt-id>`, and drop or fix `ait attempt discard latest`.

3. **`ait memory sources` crashes in default text mode.** Cited in
   `site-docs/getting-started.md.draft:138-141`, `site-docs/getting-started.md.draft:144`,
   `README.zh-TW.md.draft:205`. Counter-evidence: running the command yields
   `NameError: name '_format_live_memory_sources' is not defined` from
   `src/ait/cli/memory.py:201`. The function reference exists at two call
   sites (`memory.py:201` and `:252`) but is never defined nor imported.
   `--format json` works. **Proposed fix (code, not docs):** define or import
   the formatter in `src/ait/cli/memory.py`. Until then, demoting this
   command from "casual next step" to JSON-only usage in the draft is
   misleading on its own.

4. **`pyproject.toml` requires Python `>=3.14` but the README install
   snippet does not flag it as a sharp edge.** `pyproject.toml:11` says
   `requires-python = ">=3.14"`. `README.md.draft:166` lists Python 3.14+ as
   a requirement, which is technically accurate, but Python 3.14 is fresh
   enough that `pipx install ait-vcs` will fail on most laptops today
   (default `pipx` interpreter is the user's system Python). The launch-kit
   posts (HN, Reddit, Twitter) treat install as a one-liner. **Proposed fix:**
   add "requires Python 3.14+; on 3.13 or older use
   `pipx install --python python3.14 ait-vcs`" near every install snippet
   in the four launch-kit surfaces.

## High-priority findings (should fix)

- **`src/ait/query.py` does not exist; it is a package, `src/ait/query/`.**
  Cited as `src/ait/query.py` in `README.md.draft:86`, `README.zh-TW.md.draft:108`,
  `site-docs/index.md.draft:36`, `site-docs/why-ait.md.draft:114`,
  `site-docs/zh-TW/index.md.draft:36`, `docs/launch-kit-2026.md:82`.
  Counter-evidence: `src/ait/query/` (directory) at the repo root; the
  scalar field table lives at `src/ait/query/fields.py`. **Fix:** change the
  link target to `src/ait/query/`.

- **Getting-started "Daemon: stopped" expected output is one of two real
  states.** `site-docs/getting-started.md.draft:80` shows `Daemon: stopped`;
  in a normal session with a running daemon the line reads
  `Daemon: running (socket_connectable=True, pid_matches=True)`
  (`src/ait/cli/status_helpers.py:518`). Add "(or `running`)" so the reader
  doesn't think a running daemon is a defect.

- **"`AIT_CONTEXT_FILE` is assembled from prior attempts, accepted facts,
  and notes" — partially accurate.** `src/ait/context_manifest.py:112` builds
  the manifest from `entries` filtered by trust (`trusted`, `advisory`,
  `excluded`). The factory pulls candidates from
  `src/ait/memory/candidates.py` (attempts + facts + notes). Drafts that
  *say* "prior attempts and notes" (e.g. `README.md.draft:56`,
  `site-docs/index.md.draft:46-50`) are accurate but understate; drafts that
  *say* "prior attempts, accepted facts, and notes" (e.g.
  `README.md.draft:72`, `why-ait.md.draft:72-73`,
  `launch-kit-2026.md:46-47, 299-302`) match the code. No fix required, but
  pick one wording and use it consistently.

- **README claim ".ait/policy.json validation is fail-closed."**
  `README.md.draft:144`. Counter-evidence: the literal phrase "fail-closed"
  in `src/ait/policy.py:16` and `src/ait/memory/rerank.py:51` describes the
  memory **reranker** mode, not policy.json validation generally. Team
  policy enforcement does live in `src/ait/team_policy.py` and is called
  from `src/ait/cli/apply.py:79` and `src/ait/cli/review.py:135`, which
  supports the "consumed by apply, review, ..." half. **Fix:** say "validated
  on every apply, review, console action preflight, and context trust
  filter pass" without leaning on "fail-closed."

- **"BM25-style ranking" in `why-ait.md.draft:100-101` and
  `docs/launch-kit-2026.md:412-414`.** Counter-evidence:
  `src/ait/memory/search.py:71-93` implements two rankers — `"vector"`
  (tf-idf cosine, `_score_documents_vector`, `:266-294`) and `"lexical"`
  (term-overlap, `_score_document_lexical`, `:297-314`). Neither is BM25.
  The bible (`docs/ait-power-user-narrative-2026.md:206`) calls it
  "BM25-style"; the bible inherits the same loose phrasing. Since the
  bible permits it, this passes — but flag for v2.

- **`Bypass detection: wrapped` vs `bypass_risk` phrasing is accurate.**
  `site-docs/getting-started.md.draft:174-175`,
  `README.zh-TW.md.draft:136`. Confirmed at
  `src/ait/cli/status_helpers.py:140, 146`. No fix.

- **Launch kit asset table at `docs/launch-kit-2026.md:506-521`.** The file
  itself flags missing recordings as "**Blocker.**" That is correct and
  honest; not a draft defect, but the rebrand promotion gate must not slip
  past it.

## Confirmed accurate (sample)

- **Demo directories exist with `run.sh`.** Verified
  `examples/pain-point-demos/04-memory-reuse/{run.sh,verify.sh,README.md}`,
  `…/07-cross-agent-handoff/{run.sh,verify.sh,README.md}`,
  `…/09-1-codex-reviewer/{run.sh,verify.sh,codex_reviewer.sh,README.md}`.
- **`ait review attempt latest-reviewable --mode adversarial
  --review-adapter <name>`.** Selector real
  (`src/ait/review.py:43,807`), flags real
  (`ait review attempt --help` shows `--mode {light,adversarial}` and
  `--review-adapter`).
- **`AIT_INTENT_ID` / `AIT_ATTEMPT_ID` / `AIT_WORKSPACE_REF` /
  `AIT_CONTEXT_FILE` injected into the wrapped process.**
  `src/ait/runner.py:189-197`.
- **Worktree isolation.** `src/ait/workspace.py:64-127` provisions a Git
  worktree per attempt via `git worktree add`.
- **Daemon listens on a Unix socket only.**
  `src/ait/daemon_transport.py:52-81` uses `AF_UNIX` exclusively.
- **PyPI name is `ait-vcs`.** `pyproject.toml:6`. Repo URL
  `git@github.com:m24927605/ait.git` matches the install snippet; tag
  `v1.0.0` exists.
- **npm package layout.** `npm/ait-vcs/package.json` present.
- **`tests/fixtures/review_benchmark/`** exists with `cases.json` and a
  schema file. `docs/aitbench-dogfood-report.md` exists.

## "Would not say" leakage

Clean. Every match for the four banned-claim patterns is in the **rebuttal**
form ("AIT does not promise…", "I won't claim…", "no published benchmark
proving…"). Specifically:

- `README.md.draft:94` — frames absence of the claim, does not assert it.
- `site-docs/why-ait.md.draft:82, 89, 94, 99` — explicit "When NOT to use"
  rebuttals.
- `docs/launch-kit-2026.md:98` — explicit "I won't claim …" in the HN
  reply template.

No surface uses "catches bugs the implementer missed", "as a team",
"production-ready", "surfaces the right context", or "never lose a decision"
as a positive claim.

## CLI-command surface map

| Command in drafts | Code location | Flags match? | Output match? |
| --- | --- | --- | --- |
| `ait init` | `src/ait/cli/init.py` (parser `cli_parser.py`) | Yes | Yes (`getting-started.md.draft:39-50`) |
| `ait status` | `src/ait/cli/status_helpers.py` | Yes | **Drift** — see HP finding (`Daemon:` line variable) |
| `ait status claude-code` | `status_helpers.py:140,146` | Yes (`wrapped` / `bypass_risk`) | Yes |
| `ait attempt list` | `src/ait/cli/attempt.py:69` | Yes | Yes |
| `ait attempt show <id>` | `app.py:303` → `resolve_attempt_id` | Yes | Yes |
| `ait attempt show latest` | n/a | **No — `latest` is not resolved** | n/a (crashes) |
| `ait attempt discard latest` | n/a | **No — same root cause** | n/a (crashes) |
| `ait apply [latest|<id>]` | `cli/apply.py:88` (special-cases `latest`) | Yes | Yes |
| `ait recover [latest|<id>]` | `recovery.py:44, 299` (default `latest`) | Yes | Yes |
| `ait review attempt <selector> --mode adversarial --review-adapter <name>` | `cli/review.py`, `review.py:43,807` | Yes | Yes |
| `ait review finding list --severity high --format text` | `review finding --help` shows `{list,update}` | Yes | Yes |
| `ait query --on attempt 'adapter="codex-cli"'` | n/a (field not whitelisted) | **No** | **Crashes** |
| `ait query --on attempt 'review.status="blocked"'` | `query/fields.py:612` | Yes | Yes (returns "No attempts.") |
| `ait query --on attempt 'review.mode="adversarial"'` | `query/fields.py:617` | Yes | Yes |
| `ait memory recall <query>` | `cli/memory.py:203`, `memory/recall.py` | Yes | Yes |
| `ait memory sources` (default text) | `cli/memory.py:201` | n/a | **NameError crash** |
| `ait memory sources --format json` | `cli/memory.py:199` | Yes | Yes |
| `ait memory search <query>` | `memory/search.py:53` | Yes | Yes |
| `ait memory facts` | `cli/memory.py` | Yes | Yes |
| `ait graph` / `ait graph --html` | `cli/graph.py` | Yes | Yes |
| `ait adapter list` / `setup` | `cli/adapter.py` | Yes | Not output-checked |
| `ait shell show --shell zsh` | `cli/shell.py` | Yes | Not output-checked |
| `ait doctor` / `--fix` | `cli/doctor.py` | Yes | Not output-checked |
| `ait upgrade` / `--dry-run` | `cli/upgrade.py` | Yes | Not output-checked |
| `ait config show` | `cli/config.py` | Yes | Not output-checked |
| `ait run --adapter <name> ...` | `cli/run.py` (parser supports `aider`, `claude-code`, `codex`, `cursor`, `gemini`, `shell`) | Yes | Not output-checked |

---

**Auditor:** TestingRealityChecker
**Evidence root:** `/Users/michael.chen/products/ait/`
**Re-audit required:** after the four critical fixes; the `memory sources`
crash is a code defect, not a draft defect, so either patch the code or
remove the recommendation from `getting-started.md.draft`.
