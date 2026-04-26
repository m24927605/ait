# Changelog

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
