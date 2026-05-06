# Feature Specification: Reconcile Local Artifacts

**Feature Branch**: `005-reconcile-local-artifacts`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "AIT worktree sandbox commits do not automatically copy files that are ignored by gitignore, such as env files, back to the original repo after commit. This creates a bad experience. AIT should intelligently handle ignored/untracked local artifacts from attempt worktrees during land/promote so user-created local files do not silently disappear. AI may assist classification, but deterministic guardrails must prevent unsafe copying, overwrites, or cleanup."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prevent Silent Local File Loss (Priority: P1)

As an AIT user landing an accepted attempt, I want local files created in the attempt worktree to be detected before the worktree is cleaned up, so that useful files that cannot be committed because of ignore rules do not silently disappear.

**Why this priority**: This fixes the trust-breaking failure mode: a successful attempt can create important local setup files, then AIT removes the only copy.

**Independent Test**: Create an attempt that commits a tracked file and also creates an ignored `.env.local`; land the attempt; verify AIT reports the local artifact and either materializes it in the original repo or keeps the worktree for confirmation.

**Acceptance Scenarios**:

1. **Given** an attempt worktree contains a committed code change and an ignored local file, **When** the user lands the attempt, **Then** AIT detects the local file before cleanup and does not silently delete the only copy.
2. **Given** no ignored or untracked local artifacts exist, **When** the user lands the attempt, **Then** AIT behaves as before and cleans the worktree after a successful land.
3. **Given** local artifacts require user confirmation, **When** the user lands the attempt in a non-interactive context, **Then** AIT reports pending artifacts and keeps the attempt worktree reviewable instead of removing it.

---

### User Story 2 - Explain Artifact Decisions (Priority: P2)

As an AIT user, I want AIT to explain which local files were copied, skipped, or left pending, so that I can understand the outcome without learning implementation-specific allowlists.

**Why this priority**: Users should interact with clear outcomes, not hidden policy details or surprise cleanup behavior.

**Independent Test**: Create an attempt with safe, generated, and risky local artifacts; run land; verify text and JSON outputs include categorized artifact decisions with reasons.

**Acceptance Scenarios**:

1. **Given** AIT copies a low-risk local file, **When** land completes, **Then** output lists the file under copied local artifacts with a concise reason.
2. **Given** AIT skips a generated artifact directory, **When** land completes, **Then** output lists the skipped category and reason without requiring the user to inspect the worktree.
3. **Given** AIT leaves a risky or unknown artifact pending, **When** land cannot safely clean the worktree, **Then** output names the pending path and states the next action needed.

---

### User Story 3 - Use Intelligent Classification Safely (Priority: P3)

As an AIT user, I want AIT to classify unknown local artifacts intelligently while still enforcing safety rules, so that common tool-created files can be handled well without risking secret leakage or accidental overwrites.

**Why this priority**: Deterministic rules cover the critical safety baseline, while intelligent classification can improve handling of unfamiliar local files over time.

**Independent Test**: Present local artifacts with secret-like content, generated dependency directories, small text config files, and existing target conflicts; verify the final decisions obey safety guardrails even when classification confidence differs.

**Acceptance Scenarios**:

1. **Given** a local env file contains secret-like keys or values, **When** AIT classifies artifacts, **Then** it must not auto-copy the file without explicit user approval.
2. **Given** an intelligent classifier recommends copying a path blocked by safety policy, **When** AIT applies decisions, **Then** deterministic guardrails override the recommendation.
3. **Given** no intelligent classifier is configured, **When** AIT reconciles local artifacts, **Then** deterministic classification still prevents silent loss and unsafe copying.

### Edge Cases

- The original repository already has a file at the same path with different content.
- A local artifact is a symlink, directory, binary file, or exceeds the configured size limit.
- A local artifact is under AIT-owned paths such as `.ait/` or Git-owned paths such as `.git/`.
- The target branch is promoted without checking out the original repository working tree.
- Artifact scanning fails because the attempt worktree is missing or Git status cannot be read.
- Interactive prompts are unavailable because the command is running with JSON output or without a TTY.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: AIT MUST scan an attempt worktree for ignored and untracked local artifacts before removing that worktree after a successful land.
- **FR-002**: AIT MUST not silently remove an attempt worktree when unresolved local artifacts may contain user-created work.
- **FR-003**: AIT MUST classify detected local artifacts into copied, skipped, pending confirmation, or blocked categories.
- **FR-004**: AIT MUST automatically skip clearly generated or dependency artifacts such as virtual environments, dependency directories, caches, build output, AIT-owned paths, and Git-owned paths.
- **FR-005**: AIT MUST require explicit confirmation before copying files that are secret-like, unknown but potentially important, conflicting with existing repository files, symlinks, binary files, or over the configured safe size threshold.
- **FR-006**: AIT MUST provide deterministic guardrails that override any intelligent or AI-assisted classification recommendation.
- **FR-007**: AIT MUST work without an AI provider; AI-assisted classification is optional and cannot be required for safe artifact handling.
- **FR-008**: AIT MUST avoid sending raw secret values to any AI-assisted classifier; summaries may include path, size, file kind, detected key names, and secret-risk flags.
- **FR-009**: AIT MUST expose artifact reconciliation outcomes in both human-readable command output and JSON command output.
- **FR-010**: AIT MUST preserve existing land behavior when no local artifacts are detected.
- **FR-011**: AIT MUST avoid overwriting an existing original-repo file with different content unless the user explicitly requests overwrite behavior.
- **FR-012**: AIT MUST keep or report the attempt worktree location when pending or blocked artifacts prevent cleanup.
- **FR-013**: AIT MUST preserve the documented public behavior of existing commands, JSON keys, and verification semantics unless this specification explicitly adds additive fields.
- **FR-014**: AIT MUST keep local artifact logic cohesive and separated from Git commit materialization, verifier commit scanning, and CLI rendering concerns.

### Key Entities *(include if feature involves data)*

- **Local Artifact**: A filesystem item in an attempt worktree that is not represented in the accepted Git commits and may otherwise be lost during cleanup.
- **Artifact Classification**: The decision category and reason assigned to a local artifact before applying any copy, skip, pending, or blocked action.
- **Reconciliation Report**: The user-visible and machine-readable summary of detected artifacts, applied decisions, pending actions, and cleanup status.
- **Safety Guardrail**: A deterministic rule that prevents unsafe copying, overwriting, disclosure, or cleanup regardless of optional AI-assisted recommendations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In acceptance tests, an ignored `.env.local` created by an attempt is never silently lost after `ait attempt land`; it is either copied with an explicit reason or left pending with the worktree retained.
- **SC-002**: In acceptance tests, generated directories such as `.venv/` and `node_modules/` are not copied back to the original repository.
- **SC-003**: In acceptance tests, conflicting destination files are not overwritten unless an explicit overwrite option is used.
- **SC-004**: JSON output for land includes local artifact reconciliation data whenever artifacts are detected or cleanup is blocked by artifact decisions.
- **SC-005**: Existing tests for attempt creation, commit, verify, promote, land, cleanup, and runner auto-commit behavior continue to pass.
- **SC-006**: No touched production module exceeds 600 lines without a documented exception in the implementation plan.

## Assumptions

- Users care about local files created by agents even when those files should not be committed to Git.
- The first implementation focuses on deterministic reconciliation; AI-assisted classification may be represented by an internal extension point without requiring a provider.
- Land is the primary cleanup path that must prevent silent loss; promote behavior is additive where the original working tree is materialized.
- AIT should prefer keeping a reviewable worktree over copying unsafe files or deleting unresolved local artifacts.
