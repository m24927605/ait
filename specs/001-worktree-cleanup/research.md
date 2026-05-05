# Research: Worktree Cleanup Policy

## Decision 1: Cleanup Defaults To Dry-Run

**Decision**: `ait cleanup` must not delete anything unless `--apply` is
present.

**Rationale**: Attempt worktrees can contain unreviewed code, debugging
context, generated artifacts, or partial agent output. Users need visibility
before deletion.

**Alternatives considered**:

- Apply by default: rejected because it is too risky for local work.
- Prompt interactively: rejected for v1 because AIT commands should remain
  scriptable and deterministic.

## Decision 2: Cleanup Scope Is `.ait/workspaces`

**Decision**: Worktree cleanup only considers paths under the resolved
repo-local `.ait/workspaces` directory.

**Rationale**: AIT owns this directory. Anything outside it may be a user
checkout, sibling repo, manually-created worktree, or unrelated project data.

**Alternatives considered**:

- Use `git worktree list` globally: rejected because Git can list worktrees
  outside AIT ownership.
- Trust recorded `workspace_ref` without containment checks: rejected because
  stale or corrupted state could point outside the owned root.

## Decision 3: Status-Based Worktree Retention

**Decision**: Promoted and discarded worktrees are removable by default in
apply mode. Active, pending, and unpromoted succeeded attempts are retained.
Failed or crashed attempts require a retention window and a clean worktree.

**Rationale**: Promoted and discarded attempts have explicit terminal meaning.
Succeeded attempts may still be promotable or reviewable. Failed/crashed
attempts often contain debugging context, so a retention window avoids early
loss.

**Alternatives considered**:

- Remove all terminal attempts: rejected because `succeeded` is terminal but
  still reviewable.
- Remove failed attempts immediately: rejected because failure diagnosis is a
  core reason to keep isolated attempts.

## Decision 4: Dirty Worktrees Are Skipped

**Decision**: Any worktree with tracked or untracked changes is skipped unless
`--force` is supplied.

**Rationale**: Untracked files may be generated artifacts, but they may also be
valuable source files or logs. The first safe default is to preserve them.

**Alternatives considered**:

- Ignore untracked files: rejected because agent output is often untracked
  before commit.
- Delete allowlisted artifacts from dirty worktrees by default: deferred to
  explicit artifact cleanup.

## Decision 5: Repo-Local Policy Lives In `.ait/config.json`

**Decision**: Cleanup configuration is read from the existing repo-local AIT
config under a `cleanup` object.

**Rationale**: This avoids a new config file and follows existing local-state
patterns.

**Alternatives considered**:

- Add `.ait/cleanup.json`: rejected because it increases config surface.
- Store policy in SQLite: rejected because retention policy is user/local
  configuration, not attempt history.

## Decision 6: JSON Report Is The Contract

**Decision**: Text output is for humans; JSON output is the stable automation
contract.

**Rationale**: Cleanup decisions need to be inspectable by scripts, CI, and
future report integrations. A structured report also makes tests precise.

**Alternatives considered**:

- Text-only output: rejected because parsing cleanup decisions from text is
  brittle.
