# Research: Reconcile Local Artifacts

## Decision: Use Git to enumerate ignored and untracked artifacts

Use Git's own ignored/untracked view to identify filesystem items that are not
represented by accepted commits. The scan should query ignored and untracked
paths from the attempt worktree using porcelain-safe output and then classify
the resulting relative paths.

**Rationale**: Git already owns ignore semantics, including nested ignore files
and exclude-standard behavior. Reimplementing ignore matching would be brittle.

**Alternatives considered**:
- Walk the whole worktree and parse `.gitignore`: rejected because it is easy
  to diverge from Git behavior.
- Only check fixed filenames such as `.env`: rejected because it silently
  misses unknown tool-created local files.

## Decision: Deterministic guardrails are mandatory; AI is optional

The first implementation will classify artifacts deterministically. AI-assisted
classification may later operate on redacted metadata only, but cannot override
hard safety decisions.

**Rationale**: Local artifacts can contain secrets and may overwrite user
state. AIT must be correct and explainable without a configured AI provider.

**Alternatives considered**:
- Let AI decide copy/skip directly: rejected because it risks leaking or
  copying secrets and creates non-deterministic cleanup behavior.
- Require users to maintain allowlists: rejected because users should not need
  to understand internal policy to avoid losing files.

## Decision: Copy only low-risk text files automatically

Automatically copy small text files that are likely local configuration and do
not conflict with an existing destination. Leave env files with secret-like keys
or values pending rather than copying them silently.

**Rationale**: This prevents silent loss while avoiding secret propagation and
unapproved overwrites. Keeping the worktree is safer than deleting unresolved
artifacts.

**Alternatives considered**:
- Copy all text files: rejected because unknown text files can contain secrets.
- Never auto-copy: rejected because it degrades the common case where editor or
  local config files are safe and expected.

## Decision: Keep the worktree when unresolved artifacts remain

If any artifact is pending or blocked because it may be user work, land should
materialize the accepted Git commits but retain the attempt worktree and report
why cleanup did not happen.

**Rationale**: The primary invariant is that AIT must not destroy the only copy
of local work. Worktree retention is reviewable and reversible.

**Alternatives considered**:
- Fail land before checkout: rejected because accepted Git commits can still be
  delivered safely.
- Delete worktree after reporting: rejected because reporting alone does not
  preserve data.
