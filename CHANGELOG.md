# Changelog

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
