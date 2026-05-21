# Changelog

## Unreleased

## 1.0.1 - 2026-05-21

### Security

- Harden runner and session-room execution paths so shell execution is
  opt-in, subprocess output capture has size and timeout guards, PID reuse is
  less likely to confuse liveness checks, SQLite database files are opened
  through safer path and mode checks, and PTY/socket cleanup is more robust.

### Fixed

- Restore CI by configuring Git author identity in the workflow and preserving
  Python 3.14 mock file-descriptor behaviour in session tests.

### Changed

- Bump the Python and npm package versions to `1.0.1`.

## 1.0.0 - 2026-05-20

### Added

- Add `ait continue` as a top-level recovery router for interrupted local work.
  It chooses between reattaching an active AIT session and resuming a
  recoverable attempt worktree, while keeping JSON/non-interactive mode
  plan-only.
- Add agent-native resume hints for Claude Code, Codex, and Aider. Codex
  resume IDs are extracted best-effort from saved raw traces when present.
- Add design, acceptance, test, and code review documentation for the
  `ait continue` recovery flow.

### Changed

- Bump the Python and npm package versions to `1.0.0`.

## 0.55.67 - 2026-05-18

### Added

- `ait demo` subcommand: zero-setup 60-second walkthrough that creates a
  throwaway tmp repo, runs a scripted multi-agent attempt against the
  built-in `fake:high` reviewer, and demonstrates the review gate
  blocking the apply on a critical finding. No API keys required; all
  printed values come from a real SQLite ledger that the user can
  inspect afterwards (`docs/demo-subcommand-design.md`).
- `--stdin {inherit,none}` flag on `ait run`. Default `inherit` keeps
  the prior behaviour. Passing `--stdin none` redirects child stdin
  from `/dev/null` so non-interactive agent CLIs (e.g. `codex exec`)
  do not hang waiting for stdin EOF when invoked from a non-TTY
  context.

### Changed

- README first-screen tightened to a dual positioning hero ("local
  control plane for multi-agent AI coding"), with the long-form
  rationale lifted into a new manifesto in
  `docs/marketing/manifesto-multi-agent-local.md`.
- `pyproject.toml` `authors` metadata aligned with the active
  maintainer identity.

### Fixed

- `ait run` against an adapter whose repo-local wrapper has not been
  installed by `ait init --adapter <name>` now prints a clear stderr
  warning before spawning the agent. Previously the run would proceed
  silently, ait would fail to capture internal tool calls, and the
  verifier would later mark the attempt failed with no obvious
  explanation. The new behaviour is non-blocking; the run still
  proceeds.
- When `ait run` is invoked from a non-TTY context against an adapter
  with `native_hooks` (claude-code, codex, gemini), a one-line stderr
  hint now points at `--stdin none` to prevent the agent CLI hanging
  on stdin EOF.

### Documentation

- Add `docs/marketing/` launch artifact pack covering Show HN copy and
  a 30-question response bank, Reddit/dev.to/Product Hunt/awesome-list
  drafts, a manifesto with real dogfood evidence, a six-tweet X
  thread, Big-5 + second-tier KOL outreach DMs, five long-form
  answer-engine-optimised posts under `docs/marketing/aeo/`, and an
  LLM citation baseline tracking document.
- Add `docs/demo-subcommand-design.md` as the implementation spec for
  the new `ait demo` command.

## 0.55.66 - 2026-05-17

### Documentation

- Reposition README, docs home, AI-search facts, and `llms.txt` around AIT as
  a local control plane and Git-native attempt ledger for AI coding agents.
- Clarify that AIT memory is attempt-derived, evidence-backed repo memory, not
  hidden chat memory, an external vector database, or a `CLAUDE.md` generator.
- Document current product boundaries around alpha adoption, static graph UI,
  and the need for benchmark data before making stronger adversarial review
  quality claims.
- Add a concrete weakness-response engineering spec that maps positioning, UI,
  alpha adoption, memory clarity, and review-gate metrics to design,
  implementation slices, tests, acceptance criteria, release gates, and code
  review standards.
- Add an initial review benchmark dogfood report that records current
  deterministic fake-reviewer baseline metrics and the acceptance targets
  required before stronger adversarial-review quality claims.
- Add a category comparison page that distinguishes AIT from GUI-first agent
  managers, worktree managers, memory layers, review bots, and provenance
  tools without claiming a finished daily console.
- Expand live federated memory docs with source/status/trust rules plus
  false-memory and stale-memory acceptance demo specs.
- Add ticket-level product maturity hardening work orders for the remaining
  daily console, review benchmark, memory trust demo, metadata export/import,
  team policy profile, and UI mutation recovery work.
- Update public docs for the read-only daily console, 10-case benchmark fixture,
  and executable memory trust fixtures while keeping mutation and
  benchmark-proven quality claims out of scope.
- Add concrete resolution designs for the remaining maturity gaps: console
  mutation recovery, real Claude/Codex reviewer dogfood, context manifest memory
  trust UX, and team-readiness metadata export/import plus policy profiles.
- Update README and website docs for implemented hardening slices: context
  manifests, explicit real-reviewer dogfood benchmark path, console action
  dry-run journaling, `.ait/policy.json` validation, and metadata dry-run
  export/import.

### Added

- Add `schema` and `schema_version` to `ait graph --format json`, with a golden
  contract fixture for the `ait.work_graph` payload.
- Add `ait console --read-only`, which renders the versioned work graph as a
  local read-only daily console. `--serve-local` is loopback-only and the
  console does not provide mutation actions. The JSON payload has a schema v1
  golden contract fixture.
- Expand the review benchmark fixture to 10 cases and add JSON/Markdown
  benchmark run/report CLI support for deterministic fake reviewers, including
  a schema v1 golden report contract fixture.
- Add executable false-memory and stale-memory fixtures/tests covering recall
  selection and review trusted-baseline behavior.
- Add versioned `ait.context_manifest` generation for wrapped run context files,
  separating trusted, advisory, and excluded memory while preventing
  policy-blocked body leakage.
- Add explicit real reviewer dogfood support to `ait review benchmark run` via
  `--reviewer-adapter ... --dogfood`, while keeping deterministic fake reviewers
  as the CI-safe default.
- Add `ait console action apply|recover|discard --dry-run` with preflight checks,
  versioned `ait.console_action` JSON, and an append-only local action journal.
- Add `ait policy validate/show` for fail-closed `.ait/policy.json` validation.
- Add `ait metadata export/import --dry-run` for local no-sync metadata planning
  with versioned bundle/import-plan schemas.

### Fixed

- Exclude superseded or expired accepted memory facts from reviewer trusted
  baseline snapshots.

## 0.55.65 - 2026-05-16

### Fixed

- Keep `ait run --adapter <adapter> -- ...` and `ait run --agent <agent> -- ...`
  on the isolated agent-attempt path when `--intent` is omitted, instead of
  falling into the legacy dev-server port preflight path.
- Make `ait session run --mode role --implementer <adapter>` invoke the real
  local implementer adapter inside an isolated attempt workspace for configured
  adapters such as Codex and Claude Code. Fake implementers remain
  deterministic for tests.
- Make `ait session run --mode role --reviewer <adapter>` run real adversarial
  reviewer adapters against the implementer attempt. `claude-code` uses local
  `claude -p`; `codex` uses local `codex exec --sandbox read-only -`; fake
  reviewers remain deterministic for tests.

## 0.55.64 - 2026-05-16

### Documentation

- Reposition README and the documentation site around AIT's strongest
  multi-agent workflow: shared repo memory, long-term memory, agent-to-agent
  communication through `AIT_CONTEXT_FILE`, and adversarial review before
  apply.
- Update English and Traditional Chinese home pages, AI-search facts,
  `llms.txt`, OpenGraph metadata, and the default social card copy so external
  summaries emphasize shared memory and reviewer-agent challenge instead of
  only worktree isolation.

## 0.55.63 - 2026-05-16

### Fixed

- Keep real Codex panel/council invocation compatible with Codex CLI 0.130 by
  no longer passing the removed `--ask-for-approval` flag. AIT still records
  the consented `codex_approval` value in session metadata, while runtime
  invocation uses Codex's supported `--sandbox` flag.

### Documentation

- Update session command docs to describe Codex 0.130-compatible invocation and
  clarify that `codex_approval` is currently stored as consent/audit metadata.

## 0.55.62 - 2026-05-16

### Added

- Make `ait session run --mode panel|council|sequential` invoke real local
  adapter CLIs for active participants instead of returning the previous
  non-fake placeholder response. Claude Code uses `claude -p`; Codex uses
  `codex exec`; explicit `--agent-command agent=command` remains available for
  custom local commands.
- Add session-level permission consent for real panel/council invocation:
  `--claude-permission-mode`, `--codex-sandbox`, and `--codex-approval` are
  captured at `ait session start`, shown in session state, and reused for later
  turns. Interactive text-mode starts ask for missing permission values; JSON
  and non-TTY automation use flags or conservative defaults.

### Documentation

- Reframe README and docs site messaging around agent-to-agent communication
  through repo-local memory and `AIT_CONTEXT_FILE`, while keeping claims aligned
  with the implemented session, memory, and review behavior.
- Document real local session invocation, permission consent prompts, and the
  advisory/non-apply boundary for panel and council responses.

## 0.55.60 - 2026-05-15

### Fixed

- Pass `codex app-server` through to the real Codex CLI so Codex companion
  integrations keep their long-lived JSONL stdio session instead of being
  wrapped as one-shot AIT attempts.
- Add `AIT_WRAPPER_BYPASS=1` / `true` as a per-invocation wrapper bypass for
  direct execution of the real agent binary.

## 0.55.59 - 2026-05-14

### Added

- Capture structured prompt payloads from wrapped Claude Code, Codex, and
  Gemini runs when the adapter hook receives prompt content.
- Preserve non-TTY stdout/stderr transcripts for wrapped commands so failed
  attempts keep local failure evidence.
- Add `prompt-status` evidence so attempts can distinguish captured,
  command-derived, and unavailable prompt data.
- Add wrapper bypass detection to `ait status <adapter>` and `ait status --all`.
- Add zero-interference `ait memory backfill --dry-run` plus explicit
  `--import` for repo-local advisory memory.

### Documentation

- Document bypass detection, zero-write memory backfill, and existing-project
  onboarding in README and website docs.

## 0.55.58 - 2026-05-14

### Documentation

- Reposition the README and documentation homepage around reviewable
  attempts: AI coding agents should work in attempts, not the user's working
  tree.
- Add an `ait graph --html` screenshot to the README and documentation
  homepage to show attempts, evidence, memory, hot files, and query filters.
- Add Staff-level positioning research notes and synchronize English and
  zh-TW copy across the website, README, integrations, and pain-point demos.

### Packaging

- Align PyPI, npm, MkDocs, CITATION, and SEO metadata with the new
  attempt-first positioning.

## 0.55.57 - 2026-05-13

### Added

- Add `ait resume [latest|attempt-id]` to open or print a recoverable attempt workspace for continuing interrupted sessions without manually extracting `workspace_ref`.

## 0.55.56 - 2026-05-13

### Fixed

- Resolve Claude Code, Codex, and Gemini hook scripts through
  `AIT_WRAPPER_REPO` when wrapped agent commands run inside isolated attempt
  worktrees.
- Keep the executable pain-point demos from inheriting a stale
  `ANTHROPIC_API_KEY` into Claude Code child processes.

## 0.55.55 - 2026-05-13

### Fixed

- Suppress raw harness traceback output when an agent CLI exits after the AIT
  daemon socket has already closed or disappeared.
- Finalize wrapped runs locally after harness write failures without retrying
  the daemon finish during context cleanup.

## 0.55.54 - 2026-05-13

### Changed

- Make `ait attempt list` default to a compact human-readable table with
  short attempt IDs, status, agent, exit code, changed-file count, timestamp,
  and intent title.
- Keep full attempt metadata available through `ait attempt list --format
  jsonl` for scripts and debugging.

## 0.55.53 - 2026-05-13

### Fixed

- Let repo-local adapter wrappers recover when the embedded real CLI path is
  stale by resolving the current real command from `PATH` while avoiding
  wrapper recursion.
- Keep missing-real-binary errors fail-closed when no replacement CLI can be
  found.

## 0.55.52 - 2026-05-12

### Added

- Add diff excerpts, prior failed attempts, prior review findings, and
  structured test evidence to adversarial reviewer briefs.
- Record Claude Code reviewer CLI provenance, including the resolved binary,
  timeout, and blocked environment proof.

### Changed

- Harden adversarial review parsing with changed-file validation,
  explicit cross-file findings, duplicate rejection, actionable high-severity
  evidence requirements, and mitigation or suggested-test requirements.
- Keep the built-in `claude-code` reviewer pinned to the local `claude -p`
  CLI even when repository policy defines a conflicting command override.

### Safety

- Reject vague blocking findings, malformed review JSON, and findings outside
  the changed-file set unless they are explicitly marked as cross-file.
- Block reviewer workspace writes under both `.ait/workspaces` and
  `.ait/worktrees`.

## 0.55.51 - 2026-05-12

### Fixed

- Report a clear `WorkspaceError` when an attempt workspace is missing during
  auto-commit staging instead of surfacing a raw Python `FileNotFoundError`
  traceback.

## 0.55.50 - 2026-05-11

### Added

- Add the multi-agent control plane guide with capability matrix, same-task
  agent workflow, safe promote/merge workflow, stale recovery workflow,
  manual commit recovery workflow, and safety guarantees.
- Add acceptance coverage for same-intent parallel attempts, concurrent
  same-target promote races, local-only Unix socket coordination, bad-prompt
  worktree isolation, decision contracts, dirty worktree blocking, and manual
  workspace commit reconciliation.

### Changed

- Embed the `ait next --json` decision contract in `ait whereami --json` and
  `ait status --json` so agents can make state-aware decisions from any
  primary context command.
- Add a repo-local branch ref lock and stale-base check for promote/apply
  landing so concurrent agents cannot silently overwrite a target branch.
- Ensure idle `ait next --json` still returns an explicit recommended command.
- Resolve the built-in `claude-code` adversarial reviewer to the local
  `claude -p` CLI and strip `ANTHROPIC_API_KEY` from that child process
  environment.

### Safety

- Same-target landing now leaves the losing attempt reviewable when the target
  branch changed after its base, requiring a rebase or a different target
  branch instead of overwriting the winner.
- Claude Code adversarial reviews no longer inherit `ANTHROPIC_API_KEY` on the
  built-in local CLI path, preventing silent provider-credit fallback.

## 0.55.49 - 2026-05-10

### Added

- Add AI-agent-first state contract commands with `ait whereami`, `ait next`,
  and agent-readable JSON context for status, reconcile, recover, apply,
  review, and merge workflows.
- Add `ait merge` with dry-run operation plans, safe fast-forward/application
  paths, dirty-worktree blocking, and actionable JSON errors.
- Add `ait review report` to aggregate attempt, test, review, finding, fix,
  approval, and residual-risk evidence as JSON or Markdown.
- Add Claude Code and Codex adapter doctor auth diagnostics for local CLI
  mode without silent API-key or credits fallback.

### Changed

- Extend `ait reconcile` so manual commits made inside AIT workspaces can be
  converted into synthetic AIT results instead of leaving agents stuck outside
  AIT lineage.
- Document the standard non-interactive agent loop, JSON schema reference,
  safe merge workflow, manual commit recovery workflow, and no credits/API-key
  policy.

## 0.55.48 - 2026-05-09

### Added

- Add AIT Risk-Based Pre-Apply Review Orchestration design and
  implementation docs covering Phase 0 through Phase 6.
- Add `ait review attempt`, review queue worker, deterministic risk
  scoring, trusted baseline snapshots, structured reviewer findings,
  finding lifecycle commands, and local review benchmark support.
- Add `ait query` fields for review and finding state, including review
  status, profile, override, freshness, and finding severity/lifecycle
  filters.

### Changed

- Harden pre-apply review gates so required missing, queued, running,
  failed, blocked, stale, or malformed reviews fail closed for auto
  apply.
- Keep review status separate from verifier `verified_status`; review
  failures remain quality/safety gate evidence and do not mutate
  Git/provenance integrity status.
- Extend reports, status, and release checklist coverage for review
  status, baseline refs, freshness, overrides, and benchmark checks.

### Safety

- Reviewer adapters run through configured local commands with bounded
  cwd/env/timeout controls; AIT core does not add direct network access.
- Human override remains auditable and is recorded as override state
  rather than rewriting blocked/failed reviews as passed.
- Trusted baseline retrieval excludes candidate, stale, and
  policy-blocked memory from trusted reviewer context.

## 0.55.47 - 2026-05-08

### Added

- Add centralized decision reason codes and richer decision reports with
  paths/debug metadata across apply, recover, status, integration, and
  cleanup flows.
- Add `ait config show` for effective policy inspection, including safe
  fallback warnings for invalid repo config.
- Add repo-level recovery summary to `ait status --all` while keeping
  internal workspace paths limited to debug and JSON output.

### Changed

- Complete the minimal-interruption automation path with dev-server-aware
  cleanup/recover/status debug metadata and active-dev-server retention.
- Update the minimal-interruption design document to mark the core
  workflow complete and move remaining items to hardening/future work.

## 0.55.46 - 2026-05-08

### Added

- Add the minimal-interruption `ait apply` / `ait recover` workflow,
  workspace leases, decision reports, and status recovery dashboard.
- Add integration attempts for dirty-checkout recovery, including dirty
  snapshots, path classification, safe non-overlap replay, text
  three-way merge handling, durable integration artifacts, and
  conservative hold decisions for unsafe overlaps.

### Changed

- Shift daily CLI and docs language toward apply/recover while keeping
  low-level attempt/worktree details available in debug and JSON output.
- Tighten cleanup retention so internal workspaces with conflicts,
  active dev servers, dirty state, or missing durable results are kept
  explainably.

## 0.55.45 - 2026-05-06

### Changed

- Remove bundled specification-workflow artifacts, templates, local skills,
  and workflow metadata so AIT remains independent of any specific planning
  workflow.
- Split daemon lifecycle, status, process-state, and reaper behavior out of
  `src/ait/daemon.py` into focused `daemon_*` modules while keeping
  `ait.daemon` as the public API and monkey-patch surface.
- Preserve the existing daemon protocol, socket/PID paths, CLI behavior,
  startup/shutdown handling, and stale-attempt recovery behavior.

## 0.55.43 - 2026-05-06

### Added

- `ait attempt land` now reconciles ignored and untracked local artifacts
  before cleaning an accepted attempt worktree. Safe low-risk local files
  such as `.vscode/settings.json` can be copied back to the original
  repository, while risky files such as `.env.local` are reported as
  pending and keep the attempt worktree available for review.
- `ait attempt promote` also reconciles local artifacts when the target is
  the currently checked-out branch, so materialized current-branch
  promotions do not drop safe local configuration files.
- Land JSON results now include additive `local_artifacts` details with
  copied, skipped, pending, blocked, and cleanup status categories.

### Safety

- Local artifact handling uses deterministic guardrails: AIT skips generated
  dependency/build artifacts, refuses symlinks and binary files, avoids
  overwriting conflicting destinations, and never auto-copies secret-like
  env files.

## 0.55.40 - 2026-05-05

### Documentation

- New comparison page `/compare/git-worktree-naked-vs-ait/` with a
  7-row manual-vs-ait table, a 3-agent-parallel side-by-side bash
  example, and an honest "when you don't need ait" section.
- New AI-search facts page `/facts/` with 15 self-contained Q&A
  and `FAQPage` JSON-LD aimed at LLM retrieval (ChatGPT,
  Perplexity, Google AI Overviews, Claude search).
- New `site-docs/llms.txt` (per llmstxt.org) with a fact-dense
  blockquote and a link manifest pointing at core docs,
  integrations, comparisons, spec, and project URLs.
- README hero rewritten with the canonical entity-first sentence
  ("Git-native version control layer for AI coding agents"). Adds
  GitHub-stars / PyPI-downloads / last-commit badges; removes the
  visual `alpha` badge from the hero — the word "alpha" stays in
  the Status section. New "Compared to alternatives" H2 with a
  four-row table linking to the new comparison page.
- New `CITATION.cff` (with `m24927605` as the author handle) and
  `SECURITY.md` at the repo root for GitHub Community Standards.
- New `docs/seo-strategy.md` capturing the four-domain Staff-level
  audit, the canonical messaging architecture, and the P0/P1/P2
  work breakdown. New "SEO Drift Audit" section in
  `docs/release-checklist.md` enforcing eight canonical-string
  and version-sync checks before each tagged release.

### Packaging

- `pyproject.toml`: classifiers expanded 6 → 18 (License, OS,
  Topic depth, Intended Audience); `[project.urls]` extended
  (Documentation, Source Code, Bug Tracker, Release Notes);
  `description` switches to the canonical short form; keywords
  refined (drop generic, add `agent-harness`, `code-provenance`,
  `*-wrapper` variants).
- `npm/ait-vcs/package.json`: `description` aligned with PyPI;
  `homepage` points at the docs site; adds `os`, `cpu`,
  `preferGlobal`, `publishConfig`; keywords expanded.

### Site

- `overrides/main.html`: full template head rewrite — `og:image`
  1200×630, `twitter:card=summary_large_image`, `og:locale` +
  alternate, conditional `hreflang` (zh-TW alternate suppressed
  for `/facts/` and `/compare/` until translations land),
  `<meta name="robots">`, JSON-LD `@graph` with
  `SoftwareApplication` + `SoftwareSourceCode` + `WebSite` on the
  home page and `BreadcrumbList` on inner pages. JSON-LD
  `description` and `name` inherit from `mkdocs.yml`
  `site_description` / `site_name` to avoid drift.
- `mkdocs.yml`: `site_description` switches to the canonical long
  form; enables `navigation.indexes`, `search.share`; adds
  `i18n.fallback_to_default` + `reconfigure_material`; nav
  extended for Compare and Facts; `nav_translations` updated.
- `site-docs/robots.txt`: explicitly allows `GPTBot`, `ClaudeBot`,
  `PerplexityBot`, `Google-Extended`, `Anthropic-AI`, `cohere-ai`,
  `Applebot-Extended`.
- `site-docs/assets/og-default.{svg,png}`: 1200×630 social-preview
  asset generated from SVG via `rsvg-convert`. Same image is the
  GitHub repo social preview source (uploaded manually via the
  Settings UI).

### GitHub repo metadata

- Description: "Worktree isolation & provenance for AI coding
  agents".
- Homepage: `https://m24927605.github.io/ait/` (was the GitHub
  README anchor).
- Topics rerank under the 20-topic cap: drops `ai`, `cli`,
  `coding-agents`, `provenance`; adds `agent-harness`,
  `code-provenance`, `agentic`, `coding-assistant`.

This release is purely metadata, content, and site-level SEO —
the `ait` CLI behavior is unchanged from 0.55.39.

## 0.55.39 - 2026-05-04

### Added

- `ait init` now auto-installs the per-cd shell hook into the user's
  rc file (`~/.zshrc` for zsh, `~/.bashrc` for bash) when at least one
  adapter binary was found on `$PATH` and the hook is not already
  present. After `ait init` finishes, a single `exec $SHELL` (or new
  terminal) is enough — no `direnv allow`, no `eval "$(ait init
  --shell)"`. The block is fenced with the existing markers and `ait
  shell uninstall` removes it cleanly.
- `ait init --no-shell-install` opts out for CI, root, hardened
  sandboxes, or users who manage their rc files by hand.

### Behavior

- The Details section now reports the auto-install outcome:
  `Shell hook: installed for zsh in ~/.zshrc (run \`ait shell
  uninstall\` to remove)`, `Shell hook: already installed for zsh`,
  or `Shell hook: skipped (<reason>)`.
- Scenarios that skip auto-install: `--no-shell-install`, no adapters
  installed, shell not zsh/bash (e.g. fish), filesystem write errors.
  The legacy hint (`ait shell install` / `eval` / `direnv allow`) is
  shown in those cases.

## 0.55.38 - 2026-05-04

### Documentation

- Clarify across the docs site (`site-docs/integrations/*` en + 繁中)
  and both READMEs that `ait init` already detects every supported
  agent CLI on `$PATH` and wires it up automatically — wrappers under
  `.ait/bin/` plus hook configs merged into `.claude/settings.json`,
  `.codex/hooks.json`, and `.gemini/settings.json`. The previous docs
  showed `ait init` followed by a per-adapter `ait adapter setup
  <name>` step which is redundant; that command remains available for
  explicit re-setup (e.g. after upgrading an agent).

No code changes — auto-setup behavior was already implemented in
`adapters.enable_available_adapters` and called from the init flow.
This release is purely a documentation correction surfaced by user
feedback.

## 0.55.37 - 2026-05-04

### Added

- `ait query` now searches intent text. Both `intent.title` and
  `intent.description` are queryable with all the standard operators,
  including the substring `~` operator. The headline use case
  ("Where's that prompt I wrote last month for the query parser?")
  now works:
  ```bash
  ait query --on intent 'title~"query parser"'
  ait query --on attempt 'title~"auth"'
  ait query --on intent 'description~"staging session"'
  ```
- Every wrapped attempt now records the launched command as
  `evidence_summary.raw_prompt_ref`, stored under
  `.ait/prompts/<attempt-id>.txt`. Native-hook adapters (Claude Code,
  Codex, Gemini) still capture richer per-turn prompts via their hook
  bridges; this fallback guarantees every attempt has *some* prompt
  reference instead of `null`.

### Changed

- Reword the "local-first" claim across README, the docs site, and
  why-ait.md. The previous "no daemon" wording was literally wrong —
  ait does run `src/ait/daemon.py` on every wrapped run. New wording
  is accurate: "harness daemon is local-only — Unix socket, no
  network. No telemetry, no SaaS, no cross-machine sync."

These three changes close the gaps surfaced in the Staff QA audit of
the why-ait.md value-prop claims. After the fixes, all 10 claims hold
up to behavioural verification.

## 0.55.36 - 2026-05-04

### Added

- Cursor CLI session capture. Cursor's lifecycle hooks are unreliable
  in headless mode, so ait captures the structured event stream Cursor
  already emits to stdout via `cursor-agent --print --output-format
  stream-json`. The runner auto-enables stdout capture for the cursor
  adapter, parses the typed events (`system`, `user`, `assistant`,
  `tool_call`, `result`), and persists them as common envelope under
  `.ait/transcripts/<attempt-id>.jsonl`.
- The parser coalesces consecutive assistant chunks into a single
  turn and pairs `tool_call.started` / `tool_call.completed` events
  into envelope tool_use / tool_result entries.

### The transcript memory pipeline is now feature-complete

Cross-agent recall spans **all five** supported agents:

| Agent | Capture mechanism |
| --- | --- |
| Claude Code | Native SessionEnd hook → transcript copy |
| Codex CLI | Native SessionEnd hook → transcript copy |
| Aider | Post-run chat-history conversion |
| Gemini CLI | Native Stop hook → transcript copy |
| Cursor | Stdout stream-json post-processing (this release) |

Every session in any of these agents:
1. lands as one ait attempt with a full transcript under `.ait/transcripts/`,
2. is summarized by the heuristic (default) or LLM summarizer,
3. is recalled by every future session in every agent.

A Claude session next month can pick up where last week's Cursor
session left off. The original goal of the agent-transcript-memory-design.md
pipeline is met.

## 0.55.35 - 2026-05-04

### Added

- Native Gemini CLI hook adapter. `ait adapter setup gemini` installs
  a `gemini_hook.py` bridge under `.ait/adapters/gemini/` and writes
  `.gemini/settings.json` so each Gemini session is captured the same
  way as Claude Code and Codex: `SessionStart` → ait attempt + intent;
  `AfterTool` / `AfterToolFailure` → tool events; `Stop` → finalize
  with the persisted transcript copied into
  `.ait/transcripts/<attempt-id>.jsonl`.
- The bridge accepts both `AfterTool` (Gemini's name) and
  `PostToolUse` (Claude/Codex's name) so it stays compatible across
  versions and migration tooling.
- `Stop` does double duty as Gemini's session-end event (it fires on
  both `/clear` reset and CLI exit). The next `SessionStart` opens a
  fresh attempt.

### Cross-agent recall now spans

- Claude Code (native hook)
- Codex CLI (native hook)
- Aider (post-run chat-history conversion)
- Gemini CLI (native hook, this release)

A future Claude session can recall what last week's Gemini session
decided, and vice versa, via the existing transcript-summary memory
notes.

## 0.55.34 - 2026-05-04

### Added

- Aider chat history capture. After every wrapped aider run, ait now
  reads the markdown chat history aider writes to its working
  directory (`.aider.chat.history.md`) and converts it to the common
  envelope jsonl at `.ait/transcripts/<attempt-id>.jsonl`. Aider
  sessions now flow through the same retention, summarizer, and
  recall pipeline as Claude Code and Codex.
- The integration is zero-config — no aider flag changes required.
  As long as aider writes its default chat history file, ait captures
  it.

### Cross-agent recall now spans

- Claude Code (via SessionEnd hook + transcript copy)
- Codex CLI (via SessionEnd hook + transcript copy)
- Aider (via post-run chat-history conversion, this release)

A future Claude session can recall what last week's aider session
decided, and vice versa.

## 0.55.33 - 2026-05-04

### Added

- Native Codex CLI hook adapter. `ait adapter setup codex` now installs
  a `codex_hook.py` bridge under `.ait/adapters/codex/` and writes
  `.codex/hooks.json` so each Codex session is captured exactly the
  same way as Claude Code: SessionStart → ait attempt + intent;
  PostToolUse → tool events; SessionEnd → finalize with the persisted
  transcript copied into `.ait/transcripts/<attempt-id>.jsonl`.
- Codex transcript persistence flows through the same retention
  policy, summarizer, and recall pipeline as Claude Code, so cross-
  agent recall now works in both directions: a Claude session can
  recall what a previous Codex session decided, and vice versa.

### Fixed

- The hook bridges no longer include the `model` field in
  `attempt_started` payloads when the agent did not report one. The
  protocol validator rejects empty strings, so the previous behavior
  could surface as "daemon closed the connection before responding to
  attempt_started" warnings on agents that omit `model`.

## 0.55.32 - 2026-05-04

### Added

- Pluggable LLM-backed transcript summarizer. The default heuristic
  summarizer captures structural facts (decisions visible in the last
  assistant message, tool calls, file touches, failures); the new LLM
  variant compresses the full transcript into a richer narrative
  ("chose A over B because …", "tried X, abandoned, then Y") that the
  heuristic cannot infer.
- Two providers ship out of the box, both implemented over stdlib
  `urllib`, no SDK dependency:
  * `anthropic` — calls `/v1/messages`, default model
    `claude-haiku-4-5-20251001`.
  * `openai-compat` — calls `<base_url>/chat/completions`. Works with
    OpenAI, Azure OpenAI, Together, OpenRouter, vLLM, and Ollama
    (set `base_url` to `http://localhost:11434/v1`).
- Memory policy gains an optional `summarizer` block. Off by default —
  set `summarizer.kind` to `"llm"` to opt in.
- LLM failures (missing API key, network error, malformed response)
  log a warning and transparently fall back to the heuristic, so a
  misconfiguration never blocks the attempt lifecycle.

### Configuration

```jsonc
{
  "summarizer": {
    "kind": "llm",
    "llm": {
      "provider": "anthropic",
      "model": "claude-haiku-4-5-20251001",
      "api_key_env": "ANTHROPIC_API_KEY",
      "max_chars": 600,
      "timeout_seconds": 30
    }
  }
}
```

API keys are never written to `memory-policy.json` — only the env var
name. `ait` reads the value at summary time, so secrets stay in
shell config / direnv / your system keychain.

## 0.55.31 - 2026-05-04

### Added

- Persist Claude Code session transcripts to `.ait/transcripts/<attempt-id>.jsonl`
  on session end, instead of only referencing the upstream
  `~/.claude/projects/...` path. Transcripts now travel with the repo
  and survive Claude Code cache clears.
- Memory policy gains a `transcripts` block (`retain_days`,
  `max_total_bytes`) controlling retention. Defaults: 90 days, 500 MB.
  Applied by the daemon reaper on each scan cycle.
- Heuristic transcript summarizer (`src/ait/transcript_summarizer.py`)
  parses the persisted jsonl and writes a compact memory note
  (`topic=transcript-summary`,
  `source=transcript-summary:<agent_id>:<attempt_id>`) so future
  agents — same or different — can recall what the previous session
  decided, abandoned, or failed at, not just what it changed.
- The daemon now fires the summarizer in a background thread on each
  `attempt_finished` event, in addition to the existing verifier hook.
- `transcript-summary:*` is added to the default
  `recall_source_allow`, so summaries flow through
  `build_relevant_memory_recall` into `AIT_CONTEXT_FILE` automatically.

### Migration

Existing repositories carry a frozen
`recall_source_allow` list in `.ait/memory-policy.json` from a prior
`ait init`. To opt into transcript-summary recall, either:

- add `"transcript-summary:*"` to that list manually, or
- delete `.ait/memory-policy.json` and let the next `ait init` /
  wrapped run regenerate it with the new default.

New `ait init` runs pick up the default automatically.

### Design doc

See `docs/agent-transcript-memory-design.md` for the full pipeline,
including the not-yet-shipped Steps 3 (non-Claude hook adapters) and
the optional LLM summarizer.

## 0.55.30 - 2026-05-04

### Changed

- Reframe the README "Why ait" section as a 9-row pain → solution table
  covering blast radius, missing provenance, polluted working copy,
  repeated investigation, parallel collisions, promotion ambiguity,
  lost cross-agent context, forced SaaS, and prompt search. Mirrored to
  README.zh-TW.md and the documentation site landing page.

### Added

- Add `Why ait` deep-dive page (`site-docs/why-ait.md`) to the docs
  site, with one section per problem and the concrete ait command or
  feature that addresses it. Targets long-tail searches such as "ai
  agent blast radius", "claude code provenance", "git worktree ai
  coding".

## 0.55.29 - 2026-05-04

### Changed

- Expand PyPI and npm package keywords with long-tail terms (claude-code,
  codex, aider, gemini-cli, cursor, worktree, agent-isolation, ai-coding,
  coding-agent, git-worktree) for SEO discoverability.

### Added

- Add MkDocs Material documentation site under `site-docs/` with
  GitHub Pages deploy workflow, automatic sitemap, OpenGraph and
  Twitter Card meta, and `robots.txt`.
- Add agent integrations sections to README and 繁中 README, with one
  long-tail keyword heading per supported agent (Claude Code, Codex,
  Aider, Gemini CLI, Cursor, shell).
- Add external-promotion drafts under `docs/marketing/` (Show HN,
  Reddit, awesome-list PRs, dev.to article, Product Hunt copy).
- Update GitHub repository description and topics for SEO.

## 0.55.28 - 2026-05-01

### Fixed

- Return exit code 130 instead of surfacing a traceback when `ait run`
  receives Ctrl-C while writing or cleaning a captured command
  transcript.
- Limit captured transcript fields before terminal-control cleanup so
  very large interactive agent outputs do not stall post-run handling.
- Convert top-level CLI `KeyboardInterrupt` into exit code 130.

## 0.54.0 - 2026-04-29

### Fixed

- Mark non-terminal intents as `finished` when any child attempt verifies
  as `succeeded`, not only when an attempt is promoted.
- Keep failed and discarded-only intents running for review/retry, while
  still preserving terminal `finished`, `abandoned`, and `superseded`
  states.
- Add regression coverage so `ait graph` shows a successful wrapper run
  under a finished intent instead of a running intent.

## 0.53.0 - 2026-04-29

### Added

- Add `ait upgrade` to update the current ait installation through the
  detected installer: `pipx upgrade ait-vcs`, `python -m pip install -U
  ait-vcs`, or `npm install -g ait-vcs`.
- Add `ait upgrade --dry-run` and JSON output so users and scripts can
  inspect the selected upgrade command before running it.
- Add regression coverage for pipx dry-run output and virtualenv/pip
  upgrade execution.

## 0.52.0 - 2026-04-29

### Fixed

- Let repo-local agent wrappers use `ait run --format text` when stdin
  and stdout are real terminals, so interactive CLIs such as Codex keep
  their TTY and no longer fail with `stdout is not a terminal`.
- Keep wrapper JSON output for non-interactive invocations, preserving
  existing scripted smoke tests and automation.
- Make `ait run --format text` stream the child process directly and
  print a compact ait summary to stderr after the command exits.

## 0.51.0 - 2026-04-29

### Changed

- Make `ait doctor --fix` and `ait repair` automatically initialize Git
  when run from a plain project directory, matching the low-friction
  `ait init` behavior.
- Make `ait status` in a non-Git directory report a single actionable
  next step, `ait init`, without creating `.git` or `.ait/`.
- Add regression coverage for plain-directory status diagnostics and
  `doctor --fix --format json` initialization.

## 0.50.0 - 2026-04-29

### Changed

- Make `ait init` automatically run `git init` when invoked from a
  plain project directory, so first-time setup does not require users to
  initialize Git by hand.
- Persist a repo identity in `.ait/config.json`, including an `unborn:*`
  identity for repositories without a first commit, so local ait object
  IDs stay stable after the first commit is eventually created.
- Add regression coverage for zero-touch initialization in a non-Git
  directory and for deriving repo IDs in repositories with no commits.

## 0.49.0 - 2026-04-29

### Added

- Add `ait graph --status` to focus the work graph on attempts with a
  matching verified or reported status, such as `failed`, `succeeded`,
  or `promoted`.
- Add `ait graph --agent` to focus the work graph on a specific agent
  identity or adapter family.
- Add `ait graph --file` to show only attempts whose recorded evidence
  includes a matching file path.
- Include active filters and matched intent/attempt counts in text,
  JSON, and HTML graph output.

## 0.48.0 - 2026-04-29

### Changed

- Make `ait graph --html` easier to inspect by adding a first-screen
  summary for attempt status counts, active agents, hot files, and
  memory topics.
- Render the static HTML work graph with native expandable/collapsible
  tree sections using `<details>` and `<summary>`, without adding a
  server or JavaScript runtime.
- Keep the graph output read-only and local under `.ait/report/`.

## 0.47.0 - 2026-04-29

### Added

- Add `ait graph` to render a local AI work-history tree from repo state,
  grouping intents, attempts, agents, changed files, commits, and memory
  note counts.
- Add `ait graph --html` to write a static, read-only local tree graph to
  `.ait/report/graph.html` without starting a web server.
- Add JSON output and negative-limit validation for the work graph.

## 0.46.0 - 2026-04-29

### Changed

- Put install-version conflicts at the top of text `ait status` and
  `ait status --all`, before agent-wrapper details, so users see the
  shortest repair path first when an older pipx command shadows an npm
  install.
- Move regular `ait init` text output to a low-friction layout:
  `AIT initialized`, installed wrappers, `Next:`, then detailed repo,
  state, memory, and policy information.
- Keep install-conflict repair steps in one top-level `Next:` block and
  leave the detailed install inventory under `AIT install`.

## 0.45.0 - 2026-04-29

### Added

- Add install-source diagnostics to `ait status` and `ait doctor`,
  including the active `ait` path, current package version, executable
  path, Python executable, every `ait` command found on `PATH`, and
  detected source type such as npm, pipx, venv, or generic PATH.
- Detect multiple `ait` commands with conflicting versions and report
  low-friction next steps such as `pipx uninstall ait-vcs`, `rehash`,
  and `ait --version` when an older pipx command shadows the npm
  install.
- Add regression coverage for npm/pipx version conflict detection and
  source classification.

## 0.44.0 - 2026-04-29

### Added

- Add an npm `ait-vcs` installer package that exposes the same `ait`
  command for `npm install -g ait-vcs`.
- Make the npm package create a private Python virtual environment and
  install the matching PyPI `ait-vcs` release during npm postinstall, so
  npm users do not need to manage pip or venv setup manually.
- Add Node-based regression coverage for the npm package path and
  Python-version handling.

## 0.43.0 - 2026-04-29

### Changed

- Make text `ait init` report installed agent wrappers with user-facing
  command names such as `claude`, `codex`, `aider`, `gemini`, and
  `cursor` instead of internal adapter names.
- Make `ait init` ready/next command suggestions use the same command
  names.
- Add regression coverage proving one `ait init` installs wrappers for
  every detected supported agent CLI on `PATH`.

## 0.42.0 - 2026-04-28

### Changed

- Make text `ait status --all` report multi-agent CLI readiness first,
  using command names such as `claude`, `codex`, `aider`, `gemini`, and
  `cursor`.
- Keep detailed wrapper, PATH, binary, and memory checks in indented
  detail lines while preserving JSON status fields for automation.
- Prefer install guidance over init guidance when a real agent binary is
  missing from `PATH`.
- Document same-repo multi-agent collaboration: wrappers and adapter
  identities are separate, while memory and attempt evidence share the
  repo-local `.ait/` state.

## 0.41.0 - 2026-04-28

### Added

- Add `gemini` and `cursor` as context-enabled fixed-binary agent CLI
  adapters alongside Claude Code, Codex, and Aider.
- Add automated PATH wrapper integration coverage for `codex ...`,
  `aider ...`, `gemini ...`, and `cursor ...`, matching the existing
  `claude ...` regression path.
- Verify Codex, Aider, Gemini, and Cursor wrappers hit the repo-local
  wrapper, recreate the default memory policy, import `AGENTS.md`,
  create attempt memory, and create attempt commits.

## 0.40.0 - 2026-04-28

### Added

- Add an automated integration test for the normal user command path:
  `ait init`, PATH resolving `claude` to the repo-local wrapper, wrapper
  self-repair, agent-memory import, attempt-memory creation, and attempt
  commit creation.
- Document the reusable PATH-based Claude wrapper smoke test in the
  release checklist so future releases validate the same workflow users
  type at the terminal.

## 0.39.0 - 2026-04-28

### Changed

- Tighten user-facing docs around the normal daily path: install,
  `ait init`, `direnv allow` only if prompted, then keep running
  `claude`, `codex`, or `aider`.
- Move lower-level shell, doctor, and bootstrap commands out of the
  primary README workflow and into advanced/troubleshooting context.
- Extend release smoke coverage to run `claude ...` through `PATH`
  rather than invoking `.ait/bin/claude` directly, matching the command
  users actually type.

## 0.38.0 - 2026-04-28

### Changed

- Put the direct agent CLI readiness answer first in text `ait status`
  output, so users immediately see whether they can run `claude`,
  `codex`, or `aider`, or whether they only need `direnv allow`.
- Rename the detailed text status line to `Agent CLI detail` while
  keeping JSON `agent_cli_ready` and `agent_cli_message` unchanged for
  automation.
- Extend release smoke coverage to invoke the generated wrapper directly
  and verify policy recreation, agent-memory import, attempt-memory
  creation, workspace output, and attempt commit creation.

## 0.37.0 - 2026-04-28

### Added

- Make wrapped agent runs self-repair the default memory policy before
  importing agent memory or building context, so direct `claude`,
  `codex`, and `aider` invocations keep repo memory governance in place
  even if `.ait/memory-policy.json` was removed.
- Add runner coverage for wrapper-path self repair: `ait run` now
  verifies that agent memory is imported and the memory policy exists as
  part of normal agent execution.

## 0.36.0 - 2026-04-28

### Added

- Make `ait doctor --fix` perform the same repo initialization side
  effects as regular `ait init`: database bootstrap, wrapper repair,
  agent-memory import, and default memory policy creation.
- Add `ait doctor --fix --format json` output with initialization,
  memory import, memory policy, and direct agent CLI readiness details.
- Keep default `ait doctor --fix` stdout eval-safe for existing
  `eval "$(ait doctor --fix)"` setups while still repairing repo memory
  and policy state in the background.

### Changed

- Prefer `ait init`/`direnv allow` in one-time automation hints instead
  of teaching users to rely on lower-level shell snippets.
- Make `ait init` text output prefer `direnv allow` when direnv is
  available and only fall back to `eval "$(ait init --shell)"` when it
  is not.

## 0.35.0 - 2026-04-28

### Added

- Make regular `ait init` create the repo-local memory policy guardrail
  alongside wrappers, `.envrc`, database state, and agent-memory import.
- Add explicit `agent_cli_ready` and `agent_cli_message` fields to
  `ait status --format json` so automation can tell whether a user can
  directly invoke the agent CLI.
- Show direct agent CLI readiness in text `ait status` output.
- Include memory policy creation state in `ait init` output.

## 0.34.0 - 2026-04-28

### Added

- Make successful `ait run` sessions auto-commit changed attempt
  worktrees by default, even when no explicit commit message is passed.
- Derive default attempt commit messages from the adapter and intent so
  direct `ait run` follows the same low-interruption behavior as
  repo-local agent wrappers.
- Avoid duplicate commits when the agent already commits its own
  changes; ait verifies and records the existing attempt commit instead.
- Add `--no-auto-commit` for diagnostic runs that intentionally leave
  worktree changes uncommitted.

## 0.33.0 - 2026-04-28

### Added

- Add policy-driven relevant-memory governance while keeping the default
  agent workflow zero-touch for users.
- Add repo-local recall source allow and block patterns to
  `.ait/memory-policy.json`.
- Add repo-local recall lint severity gates so teams can choose whether
  warnings or info-level memory issues are blocked from automatic agent
  context injection.
- Render the active recall governance policy from `ait memory policy
  show`.

## 0.32.0 - 2026-04-28

### Added

- Add memory health reporting to `ait status`, including lint issue
  counts by severity without writing `.ait/` during status-only checks.
- Add default governance gates to relevant-memory recall so notes with
  lint errors are skipped before wrapped agent context injection.
- Add `ait memory recall --include-unhealthy` for explicit diagnostics
  when inspecting blocked memory notes.
- Make `ait repair` run conservative memory lint fixes and report memory
  health alongside wrapper and agent-memory repair results.

## 0.31.0 - 2026-04-28

### Added

- Add `ait memory lint` to report long-term memory quality issues such
  as duplicates, overlong notes, possible secrets, missing confidence,
  low-information notes, and stale attempt-memory sources.
- Add `ait memory lint --format json` for CI and automation.
- Add conservative `ait memory lint --fix` actions for exact duplicate
  deactivation, secret redaction, and overlong note compaction.
- Add lint result summaries with checked note count, issue count, fix
  count, per-note severity, fixability, and applied fixes.

## 0.30.0 - 2026-04-28

### Added

- Add `ait memory recall <query>` to preview the relevant memory that
  wrapped agent runs would inject into context.
- Add `ait memory recall --auto` to generate the same recall query shape
  used by wrapped agent runs from intent, command, kind, description, and
  agent inputs.
- Add recall JSON output with selected memory, skipped candidates, score,
  query sources, budget, rendered chars, and compacted state.
- Add relevant-memory metadata to `.ait-context.md`, including selected
  count and budget chars.

## 0.29.0 - 2026-04-28

### Added

- Add `AIT Relevant Memory` to wrapped agent context files.
- Retrieve the most relevant `agent-memory` and `attempt-memory` notes
  using the generated intent, command, kind, and agent query.
- Compact relevant memory to a fixed budget before injecting context so
  long-term memory remains token-conscious.
- Include intent title, kind, and description in automatic attempt
  memory notes to improve future recall quality.

## 0.28.0 - 2026-04-28

### Added

- Add automatic attempt memory notes after every `ait run` so completed
  agent work is preserved as reusable long-term memory.
- Record structured low-noise attempt summaries with attempt id, intent
  id, agent id, status, exit code, confidence, changed files, commit
  oids, and trace reference.
- Add source-based deduplication for attempt memory notes.
- Store successful attempts with high confidence and failed attempts
  with advisory confidence.

## 0.27.0 - 2026-04-28

### Added

- Add automatic agent memory import before every wrapped `ait run`, so
  existing `CLAUDE.md`, `AGENTS.md`, Codex, Claude, and Cursor memory
  files are picked up even when users only activate wrappers and run an
  agent CLI.
- Add repo-local agent memory import state at
  `.ait/memory/agent-import-state.json` to avoid repeated imports when
  memory files have not changed.
- Show agent memory initialization state, imported source count, and
  pending memory files from `ait status`.
- Make `ait repair` also repair agent memory import state.

## 0.26.0 - 2026-04-28

### Added

- Make `ait init` safely import detected agent memory files into ait
  memory notes during repository initialization.
- Add `memory_import` details to `ait init --format json` so scripts can
  inspect imported and skipped memory sources.

### Changed

- Keep `ait init --shell` shell-only and eval-safe: it installs wrappers
  and prints only the PATH export for the current terminal.

## 0.25.0 - 2026-04-28

### Added

- Add `ait memory import` to convert existing agent memory files into
  ait memory notes.
- Auto-detect common memory files such as `CLAUDE.md`, `AGENTS.md`,
  `.claude/memory.md`, `.codex/memory.md`, and Cursor rules files.
- Add `ait memory import --path <file>` for custom memory file imports.
- Add source, path, confidence, redaction, deduplication, and memory
  policy handling for imported agent memory.

## 0.24.0 - 2026-04-28

### Added

- Add `ait repair` to rebuild detected agent wrappers, restore `.envrc`
  wrapper activation, and report before/after automation status.
- Add `ait repair <adapter>` for scoped wrapper repair, such as
  `ait repair codex`.
- Add JSON and text repair output with installed adapters, skipped
  adapters, shell activation hints, and status changes.
- Keep repair conservative when no real agent binary is found: skip the
  adapter and avoid creating wrapper or `.envrc` files for it.

## 0.23.0 - 2026-04-28

### Added

- Add wrapper preflight diagnostics for missing or non-executable real
  agent binaries, including adapter, repo, wrapper path, real binary,
  and next-step output.
- Add wrapper recursion diagnostics that point users back to scoped
  `ait init --adapter <name> --shell` setup.
- Record direct `ait run -- <missing-command>` failures as failed
  attempts with clear command-not-executable stderr instead of raising a
  traceback.

## 0.22.0 - 2026-04-28

### Added

- Make `ait init` perform repo initialization plus automatic wrapper
  setup for detected Claude Code, Codex, and Aider binaries.
- Add `ait init --shell` as an eval-safe one-command activation path
  for the current shell.
- Add `ait init --adapter <name>` and `ait init --format json` for
  scoped or scripted initialization.
- Report installed, skipped, ready, and next shell activation state from
  `ait init`.

## 0.21.0 - 2026-04-28

### Added

- Add automatic repo brain briefing query generation from intent text,
  command args, agent identity, recent failed attempts, hot files, and
  memory note topics.
- Add `ait memory graph brief --auto` for generated briefing queries.
- Add query source explanations to repo brain briefing text and JSON.
- Use automatic query generation for wrapped agent context briefings.

## 0.20.0 - 2026-04-28

### Added

- Add `ait memory graph brief <query>` to render a compact repo brain
  briefing selected from the graph.
- Add JSON output for repo brain briefings.
- Inject `AIT Repo Brain Briefing` into wrapped agent context instead
  of the full graph report.
- Add design documentation for repo brain briefing selection.

## 0.19.0 - 2026-04-28

### Added

- Add derived repo brain graph construction from docs, memory notes,
  intents, attempts, agents, changed files, and attempt commits.
- Add `ait memory graph build`, `ait memory graph show`, and
  `ait memory graph query` with JSON and text output.
- Automatically refresh `.ait/brain/graph.json` and
  `.ait/brain/REPORT.md` before wrapped agent context injection.
- Include an `AIT Repo Brain` section in wrapped agent context files.
- Add design and acceptance documents for the repo brain control plane.

## 0.18.0 - 2026-04-28

### Added

- Add `ait shell show` to print the persistent shell integration block.
- Add `ait shell install` for opt-in zsh/bash rc integration that
  automatically activates `.ait/bin` when the current directory is an
  AIT-enabled repository.
- Add `ait shell uninstall` to remove the managed shell integration
  block.

## 0.17.0 - 2026-04-28

### Changed

- Make `ait doctor --fix` delegate to all-agent auto-enable so the
  legacy low-friction setup command now enables every detected supported
  agent CLI, not only Claude Code.
- Keep `ait doctor <adapter> --fix` as a scoped setup path for users who
  want to enable one agent.
- Add explicit post-enable next commands in text output, such as
  `claude ...`, `codex ...`, and `aider ...`.

## 0.16.0 - 2026-04-28

### Added

- Add `ait status --all` to report automation readiness for Claude
  Code, Codex, and Aider in one command.
- Add JSON and text output for all-agent status checks.

### Changed

- Point status next steps and one-time hints at `ait enable --shell`
  and `ait enable --adapter <name>` so users do not need to learn
  per-adapter bootstrap commands first.

## 0.15.0 - 2026-04-28

### Added

- Add `ait enable` to auto-detect installed Claude Code, Codex, and
  Aider binaries and install repo-local wrappers for every detected
  agent.
- Add `ait enable --shell` as a single eval-friendly setup path for all
  detected agent workflows.
- Add JSON and text output for auto-enable results, including installed
  and skipped adapters.

## 0.14.1 - 2026-04-28

### Fixed

- Make the GitHub Actions PyPI publish workflow tolerate already
  uploaded distributions so manual fallback uploads do not leave release
  automation in a failed state.

## 0.14.0 - 2026-04-27

### Added

- Add repo-local `.ait/memory-policy.json` configuration.
- Add `ait memory policy init` and `ait memory policy show`.
- Exclude policy-matched changed paths from memory summaries, hot files,
  and memory search metadata.
- Exclude policy-matched Aider/Codex transcripts before durable storage
  so sensitive transcript text cannot become searchable memory.

## 0.13.0 - 2026-04-27

### Added

- Redact common secrets before Aider and Codex transcripts are written
  to `.ait/traces/`.
- Redact curated memory notes in rendered memory and memory search
  documents.
- Mark memory search results with `redacted` metadata when evidence
  contains redactions.

### Fixed

- Make schema migration recording tolerant of re-entrant migration calls.

## 0.12.0 - 2026-04-27

### Added

- Capture Aider and Codex wrapped command stdout/stderr transcripts into
  repo-local `.ait/traces/` files.
- Attach captured transcripts to attempts as raw trace evidence.
- Include captured Aider and Codex transcripts in `ait memory search`
  documents.

## 0.11.0 - 2026-04-27

### Added

- Add repo-local TF-IDF vector ranking for `ait memory search`.
- Add `ait memory search --ranker vector|lexical`, with vector ranking
  as the default and lexical ranking retained as a deterministic
  fallback.
- Include the selected memory search ranker in result metadata.

## 0.10.0 - 2026-04-27

### Added

- Add repo-local wrapper, bootstrap, doctor, and direnv automation for
  the Aider and Codex adapters.
- Add `AIT_CONTEXT_HINT` for Aider and Codex so their wrapped runs use
  the same memory/context handoff contract as Claude Code.
- Keep Claude Code native hook setup while generalizing adapter
  automation checks for non-Claude fixed-binary adapters.

## 0.9.0 - 2026-04-27

### Added

- Add `ait memory search <query>` for repo-local evidence search across
  curated memory notes, attempts, intent text, changed files, and
  attempt commits.
- Add JSON and text output for memory search results so agent workflows
  can retrieve relevant memory without reading the full memory summary.

## 0.8.0 - 2026-04-27

### Added

- Add memory filtering by file path with `ait memory --path`.
- Add topic filtering for curated memory with `ait memory --topic`.
- Add promoted-only memory mode with `ait memory --promoted-only`.
- Add manually curated memory notes through `ait memory note add`,
  `ait memory note list`, and `ait memory note remove`.
- Add a character-budget compaction policy with
  `ait memory --budget-chars`.

## 0.7.0 - 2026-04-27

### Added

- Add `ait memory` for local long-term repo memory summaries derived
  from intents, attempts, changed files, and attempt commits.
- Inject long-term repo memory into Claude Code context files generated
  by `ait run --adapter claude-code`.
- Add Staff-level long-term memory design and acceptance documents.

## 0.6.7 - 2026-04-27

### Fixed

- Do not fail `ait run --commit-message ...` when the wrapped agent exits
  successfully but leaves no file changes to commit.

## 0.6.6 - 2026-04-27

### Changed

- Rework the README opening for a 30-second external quickstart from
  PyPI or GitHub.
- Add `docs/getting-started.md` with install, activation,
  verification, and rollback steps for Claude Code automation.
- Improve package metadata description for PyPI readers.

## 0.6.5 - 2026-04-27

### Added

- Add global `--no-hints` to suppress automation hints for scripted use.
- Add one-time stderr automation hints for text `ait status` output when
  Claude Code automation is not connected.
- Store shown hint state in `.ait/hints.json` without affecting JSON
  stdout.

## 0.6.4 - 2026-04-27

### Added

- Add `ait status` for a compact, non-mutating automation readiness
  summary with next steps.
- Let `ait bootstrap` default to the Claude Code adapter.
- Add `ait doctor --fix` as an eval-friendly one-command setup path.

## 0.6.3 - 2026-04-27

### Added

- Add `ait bootstrap claude-code --shell` for eval-friendly setup that
  installs the wrapper and prints an export for the current shell.
- Add `ait bootstrap claude-code --check` for non-mutating automation
  readiness checks.
- Make top-level `ait doctor` text output include the shortest next
  command when the wrapper path is not active.

## 0.6.2 - 2026-04-27

### Added

- Add `ait bootstrap claude-code` as a single low-friction setup command
  for Claude Code wrapper and direnv integration.
- Add top-level `ait doctor` automation checks for wrapper, PATH,
  direnv, `.envrc`, and the real Claude Code binary.

## 0.6.1 - 2026-04-27

### Added

- Add `ait adapter setup claude-code --install-direnv`, which installs
  the repo-local Claude wrapper and appends `PATH_add .ait/bin` to
  `.envrc` so `claude` can resolve through ait with less manual setup.

## 0.6.0 - 2026-04-27

### Added

- Add `ait adapter setup claude-code --install-wrapper`, which installs
  a repo-local `.ait/bin/claude` wrapper so users can keep invoking
  `claude` while ait automatically runs Claude Code through an isolated
  attempt worktree.

## 0.5.4 - 2026-04-27

### Added

- Add `ait run --format json|text`; JSON mode captures command stdout
  and stderr in result fields so stdout remains parseable JSON for CI
  and scripts.

## 0.5.3 - 2026-04-27

### Fixed

- Make `ait run --commit-message ...` stage generated worktree changes,
  commit them, verify the attempt, and omit the generated
  `.ait-context.md` handoff file from the commit.
- Return a clean CLI error if `ait run --commit-message ...` cannot
  stage or commit the attempt worktree.

### Added

- Document the Claude Code worktree workflow where `ait run --adapter
  claude-code` makes Claude edit the attempt worktree, then
  `ait attempt promote` applies the result to the target branch.

## 0.5.2 - 2026-04-27

### Fixed

- Generate Claude Code hook settings with the Python executable that ran
  `ait adapter setup`, so pipx and virtualenv installs can import
  `ait` from the hook process.

### Added

- Document the live Claude Code smoke test that verified real Claude
  Code hook payloads record ait attempts and tool evidence.

## 0.5.1 - 2026-04-27

### Added

- Add an end-to-end Claude Code hook regression test that installs the
  packaged hook, simulates Claude Code session/tool/finish payloads, and
  verifies recorded ait evidence.

## 0.5.0 - 2026-04-27

### Added

- Add `ait adapter setup claude-code` to install the packaged Claude
  Code hook bridge into a repository and merge hook settings into
  `.claude/settings.json`.
- Add `ait adapter setup claude-code --print` for printing the generated
  Claude Code settings without writing files.

## 0.4.4 - 2026-04-27

### Changed

- Add a workflow integration guide for shell commands, Claude Code,
  Codex, Aider, and custom harness integrations.

## 0.4.3 - 2026-04-27

### Added

- Add `ait --version` for install and smoke-test verification.

## 0.4.2 - 2026-04-26

### Changed

- Configure the PyPI publish workflow to use the `pypi` GitHub
  environment for Trusted Publishing, and document the matching PyPI
  publisher settings.

## 0.4.1 - 2026-04-26

### Fixed

- Package Claude Code hook script and settings sample as installable
  resources so `ait adapter doctor claude-code` works from PyPI
  installs.

## 0.4.0 - 2026-04-26

### Added

- Add `ait adapter doctor <name>` for non-mutating adapter readiness
  checks.
- Add `ait adapter list` and `ait adapter show <name>` for inspecting
  adapter defaults, environment variables, and native-hook capability.

## 0.3.0 - 2026-04-26

### Added

- Add an adapter registry for `ait run` with `shell`, `claude-code`,
  `aider`, and `codex` presets.
- Add `ait run --adapter ...` while preserving `--agent` as an override.

## 0.2.0 - 2026-04-26

### Added

- Add `ait context <intent-id>` with text and JSON output for compact
  agent handoff context.
- Add `ait run --with-context`, which writes `.ait-context.md` into the
  attempt worktree and exposes it as `AIT_CONTEXT_FILE`.

## 0.1.3 - 2026-04-26

### Fixed

- Make fresh SQLite schema creation avoid an unstable `ALTER TABLE DROP
  COLUMN` path that failed on Linux CI. New databases now start from the
  final attempts table shape directly.

## 0.1.2 - 2026-04-26

### Added

- Add `ait run`, a universal command wrapper that creates an intent and
  attempt, runs a shell-launchable agent command inside the attempt
  worktree, streams command provenance through the daemon, and finishes
  the attempt with the command exit code.

## 0.1.1 - 2026-04-26

### Changed

- Rename the PyPI distribution to `ait-vcs` because `ait` is already
  owned by another PyPI project. The installed command and import package
  remain `ait`.
- Add PyPI metadata, project URLs, README packaging, and classifiers.

## 0.1.0 - 2026-04-26

Initial MVP release candidate.

### Added

- Local `.ait/` initialization with SQLite state.
- Intent and attempt lifecycle commands.
- Attempt isolation through Git worktrees.
- Daemon process with Unix socket transport.
- Harness client for lifecycle and tool-event ingestion.
- Evidence summaries for tool calls, file reads, file writes, commands,
  and durations.
- Query, list, show, and blame commands over indexed metadata.
- Attempt verification, commit indexing, promote, discard, and rebase.
- Git post-rewrite hook installation and local reconciliation path.
- Claude Code hook bridge example and settings sample.
- GitHub Actions CI running the test suite on Python 3.14.

### Known Limitations

- Metadata is local-only and not synchronized across machines.
- Claude Code hook bridge records provenance but does not force Claude
  Code to edit inside the ait attempt worktree.
- Rebase conflicts are left in the attempt worktree for manual Git
  resolution or abort.
- The daemon is a long-running Python process and must be restarted to
  pick up source changes during development.
