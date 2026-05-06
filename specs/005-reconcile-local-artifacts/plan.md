# Implementation Plan: Reconcile Local Artifacts

**Branch**: `005-reconcile-local-artifacts` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/005-reconcile-local-artifacts/spec.md`

## Summary

Prevent accepted attempt worktrees from losing ignored or untracked local files
when AIT lands or materializes an attempt. Add a focused local artifact
reconciliation module that scans Git's ignored/untracked view, classifies paths
with deterministic guardrails, copies only low-risk artifacts, reports skipped
and pending artifacts, and keeps the worktree when unresolved user-created work
would otherwise be deleted. AI-assisted classification remains an extension
point only; deterministic policy is the required implementation.

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: Python standard library only; Git subprocesses already used by AIT
**Storage**: Filesystem artifacts in attempt worktrees and original repository; no SQLite schema change required
**Testing**: `pytest` and `unittest` over existing tests
**Target Platform**: Local POSIX CLI environments with Git
**Project Type**: Python CLI/library package
**Performance Goals**: Artifact scan should be bounded to Git-reported ignored/untracked paths and avoid walking large trees eagerly
**Constraints**: Preserve existing command names, default successful land behavior when no local artifacts exist, and avoid copying secrets, generated directories, symlinks, binary files, or conflicting files without explicit approval
**Scale/Scope**: Attempt worktrees under `.ait/workspaces`; first implementation covers deterministic classification and reporting, with AI classification represented only as a future-safe decision boundary

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Kit Traceability**: PASS. Active feature is recorded in `.specify/feature.json`, and all artifacts live under `specs/005-reconcile-local-artifacts/`.
- **Low Coupling, High Cohesion**: PASS. `local_artifacts.py` owns artifact scanning/classification/copy policy; `workspace.py` remains Git/worktree lifecycle; `app.py` orchestrates attempt land/promote; CLI rendering stays in command handlers.
- **Stable Public Behavior**: PASS. Existing commands remain; JSON output receives additive local artifact fields only where land/promote results already serialize dataclasses.
- **Local Safety And Data Integrity**: PASS. Copy operations are bounded to paths relative to the original repo, exclude AIT/Git/generated paths, avoid symlinks and binary files, and refuse conflicting writes unless a future explicit override is added.
- **Verification Before Completion**: PASS. Targeted local artifact tests, app flow tests, CLI JSON checks, full relevant attempt/workspace suites, and `git diff --check` are required.

## Project Structure

### Documentation (this feature)

```text
specs/005-reconcile-local-artifacts/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── local-artifacts-json.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/ait/
├── local_artifacts.py     # local artifact scan, classification, copy, report dataclasses
├── app.py                 # attempt land/promote orchestration
├── workspace.py           # worktree lifecycle and Git ref materialization
└── cli/attempt.py         # JSON output through existing dataclass serialization

tests/
├── test_local_artifacts.py
├── test_app_flow.py
└── test_cli_run.py or test_cli_attempt coverage embedded in app flow subprocess tests
```

**Structure Decision**: Add one cohesive production module for artifact
reconciliation. Avoid embedding path policy into `workspace.py` so Git lifecycle
code does not start owning secret/copy policy. Avoid SQLite changes for the
first slice; the command result report is sufficient evidence.

### Dependency Direction

Allowed direction:

```text
app.py -> local_artifacts.py
app.py -> workspace.py
cli/attempt.py -> app.py

local_artifacts.py -> standard library only
workspace.py must not import local_artifacts.py
verifier.py must not import local_artifacts.py
```

`local_artifacts.py` owns deterministic policy, destination path validation,
secret-risk heuristics, generated-path heuristics, binary/symlink checks, and
copy actions. `app.py` decides when reconciliation runs and whether worktree
cleanup is allowed after reconciliation.

### Public Compatibility Surface

- `ait attempt land` remains the command for accepting an attempt into the
  original repository and cleaning the worktree when safe.
- `ait attempt promote` remains the command for moving a target branch ref.
- Existing result keys remain present. Additive keys may include
  `local_artifacts` and `worktree_cleaned=false` when cleanup is blocked.
- Existing SQLite tables and verifier commit materialization remain unchanged.
- Existing imports from `ait.app` remain compatible; dataclass fields are
  additive and defaulted where needed.

### Verification Plan

```bash
uv run pytest tests/test_local_artifacts.py
uv run pytest tests/test_app_flow.py tests/test_cli_run.py tests/test_workspace.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Spec-specific checks:

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
for path in [Path("src/ait/local_artifacts.py"), Path("src/ait/app.py"), Path("src/ait/workspace.py")]:
    lines = path.read_text(encoding="utf-8").count("\n") + 1
    print(f"{lines:4d} {path}")
    if lines > 600:
        raise SystemExit(f"{path} exceeds 600 lines")
print("local artifact architecture gate ok")
PY
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
