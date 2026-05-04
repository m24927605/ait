# Changelog

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
