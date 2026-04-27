# Changelog

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
