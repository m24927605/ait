# Data Model: Reconcile Local Artifacts

## LocalArtifact

Represents one filesystem item in an attempt worktree that Git does not include
in accepted commits.

Fields:
- `path`: repository-relative POSIX path.
- `kind`: `file`, `directory`, `symlink`, `missing`, or `other`.
- `size_bytes`: file size when available.
- `git_status`: ignored or untracked source status.
- `is_text`: whether file content can be safely inspected as text.
- `secret_risk`: whether path/content metadata suggests credentials or tokens.

Validation:
- Path must be relative.
- Path must not escape the repository root.
- Paths under `.git/` and `.ait/` are always blocked or skipped.

## ArtifactDecision

Represents the deterministic decision for one artifact.

Fields:
- `path`: artifact path.
- `action`: `copy`, `skip`, `pending`, or `blocked`.
- `reason`: concise user-facing explanation.
- `destination`: original repo destination path when relevant.

Validation:
- `copy` requires a regular text file, no destination conflict, no secret risk,
  no symlink, and size under threshold.
- `pending` requires retaining the attempt worktree.
- `blocked` requires no copy attempt.

## ReconciliationReport

Represents the aggregate result shown to users and JSON consumers.

Fields:
- `detected`: all detected artifact paths.
- `copied`: decisions copied to the original repo.
- `skipped`: generated or irrelevant decisions skipped safely.
- `pending`: decisions that require user confirmation.
- `blocked`: decisions that were unsafe to copy.
- `cleanup_allowed`: whether the worktree may be removed.

State transitions:
- No artifacts -> cleanup allowed.
- Only copied/skipped artifacts -> cleanup allowed.
- Any pending/blocked user-work artifact -> cleanup not allowed.

## SafetyGuardrail

Represents a hard deterministic rule.

Examples:
- Never copy `.git/`, `.ait/`, `.venv/`, `node_modules/`, cache, or build output.
- Never copy symlinks.
- Never overwrite conflicting destination files.
- Never auto-copy secret-like env files.
- Never auto-copy binary or oversized files.
