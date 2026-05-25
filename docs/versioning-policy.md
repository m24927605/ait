# Versioning Policy

AIT uses Semantic Versioning for public releases:

```text
MAJOR.MINOR.PATCH
vMAJOR.MINOR.PATCH
```

The package version in `pyproject.toml`, the npm package version in
`npm/ait-vcs/package.json`, the Git tag, README install examples, and the
CHANGELOG release heading must refer to the same release version.

## Release Version Rules

Use `PATCH` (`X.Y.Z -> X.Y.Z+1`) for changes that are backward-compatible and
do not add a new user-facing capability:

- bug fixes
- security hardening that preserves the current interface
- packaging, install, CI, and release automation fixes
- documentation, website, README, or metadata-only changes
- internal refactors with no CLI, JSON contract, DB, config, or workflow change
- compatibility fixes for new versions of supported agent CLIs

Use `MINOR` (`X.Y.Z -> X.Y+1.0`) for backward-compatible product capability:

- new CLI commands, options, modes, or shell integration behavior
- new adapter support or meaningful adapter capability
- new user-visible workflows, recovery behavior, automation, or UX defaults
- new JSON fields or schemas that old readers can safely ignore
- backward-compatible SQLite migrations or metadata additions
- policy/config additions that default to existing safe behavior

Use `MAJOR` (`X.Y.Z -> X+1.0.0`) for breaking changes:

- removing or renaming public commands, flags, JSON fields, schemas, config keys,
  or documented files
- changing default behavior in a way that can surprise existing automation
- incompatible `.ait/state.sqlite3` or artifact migration requirements
- dropping supported Python, Node, OS, Git, or agent CLI compatibility
- changing package names, install flow, or Git tag format

## Current Project Policy

AIT is alpha-quality as a product, but the published package line is already
`1.x`. Do not reset public versions back to `0.x`.

Within the `1.x` line:

- Treat CLI commands, JSON output, local metadata, and shell integration as
  public contracts once released.
- Prefer `MINOR` for any user-visible workflow improvement, even when it feels
  small.
- Prefer `PATCH` only when the behavior is clearly a fix to already released
  functionality.
- If a release contains both patch-worthy fixes and minor-worthy features, bump
  `MINOR`.
- If a release contains any breaking change, bump `MAJOR`.

For wrapper-level agent auto-continue work, the correct release level is
`MINOR`: it adds a backward-compatible, user-visible recovery workflow for
bare interactive agent commands.

## Git Tags

Stable releases use annotated Git tags:

```bash
git tag -a vX.Y.Z -m "AIT vX.Y.Z"
```

Rules:

- Tags are lowercase `v` followed by the exact package version.
- Do not tag dirty worktrees.
- Do not reuse or move published tags.
- Do not publish npm until PyPI lists the same stable version.
- The GitHub release title should be `AIT vX.Y.Z`.

## Pre-Releases

Avoid publishing pre-releases unless a broader external test is required.

If needed:

- Git tag: `vX.Y.Z-rc.N`
- npm version: `X.Y.Z-rc.N`
- Python version: `X.Y.ZrcN` (PEP 440)

Because Python and npm spell pre-releases differently, stable releases are the
default. Internal testing should normally use commit SHAs, branches, or local
wheels instead of published pre-release versions.

## Bump Checklist

When bumping a release version, update all of:

1. `pyproject.toml` `[project].version`
2. `npm/ait-vcs/package.json` `version`
3. README install examples containing the previous tag
4. `CHANGELOG.md`: move `Unreleased` notes under `## X.Y.Z - YYYY-MM-DD`
5. any docs/site facts that mention the current release version
6. Git tag `vX.Y.Z`

Before choosing the bump level, classify every shipped change against the
PATCH/MINOR/MAJOR table above. Use the highest required level.
