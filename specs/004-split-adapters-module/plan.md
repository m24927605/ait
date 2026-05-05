# Implementation Plan: Split Adapters Module

**Branch**: `004-split-adapters-module` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/004-split-adapters-module/spec.md`

## Summary

Reduce coupling in `src/ait/adapters.py` by extracting adapter dataclasses,
registry metadata, resource/settings helpers, wrapper helpers, doctor checks,
and setup/bootstrap orchestration into focused modules. Keep `ait.adapters` as
the public compatibility facade so CLI code and external imports continue to
work unchanged.

## Technical Context

**Language/Version**: Python 3.14+
**Primary Dependencies**: Python standard library only; no new runtime dependencies
**Storage**: Existing repository files under `.ait/`, `.claude/`, `.codex/`, `.gemini/`, and `.envrc`
**Testing**: `pytest` and `unittest` over existing tests
**Target Platform**: Local POSIX CLI environments with Git
**Project Type**: Python CLI/library package
**Performance Goals**: Preserve current adapter setup and doctor runtime behavior; no new startup work for normal CLI parser imports
**Constraints**: Preserve `ait.adapters` imports, CLI output, generated resources, wrapper scripts, settings merge semantics, and Git/path safety
**Scale/Scope**: Adapter module extraction only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Kit Traceability**: PASS. Active feature is recorded in
  `.specify/feature.json` and artifacts live under `specs/004-split-adapters-module/`.
- **Low Coupling, High Cohesion**: PASS. Models, registry, resources/settings,
  wrapper helpers, doctor checks, and setup orchestration have explicit module
  boundaries and dependency direction.
- **Stable Public Behavior**: PASS. The plan preserves `ait.adapters` public
  imports, `ADAPTERS`, CLI adapter behavior, generated resource contents,
  wrapper behavior, and setup/doctor result dataclasses.
- **Local Safety And Data Integrity**: PASS. Writes remain bounded to existing
  adapter-owned paths in the target repository and no Git refs, SQLite schema,
  or daemon protocol behavior is introduced.
- **Verification Before Completion**: PASS. Targeted adapter tests, native hook
  tests, full suites, public import contract, architecture gates, and
  `git diff --check` are required.

## Project Structure

### Documentation (this feature)

```text
specs/004-split-adapters-module/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── public-adapters-surface.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/ait/
├── adapters.py             # public compatibility facade
├── adapter_models.py       # adapter/result dataclasses and AdapterError
├── adapter_registry.py     # ADAPTERS, get_adapter, list_adapters
├── adapter_resources.py    # resource loading, generated settings, settings merge
├── adapter_wrapper.py      # real binary lookup, wrapper script, .envrc helpers
├── adapter_doctor.py       # adapter and automation doctor checks
└── adapter_setup.py        # setup, bootstrap, and auto-enable orchestration

tests/
├── test_adapters.py
├── test_cli_adapters.py
├── test_claude_code_hook.py
├── test_codex_hook.py
└── test_gemini_hook.py
```

**Structure Decision**: Keep `src/ait/adapters.py` as a module facade, not a
package conversion, to preserve existing `from ait.adapters import ...` callers
and CLI parser imports. Move implementation concerns into `adapter_*.py`
helpers whose names make responsibility and dependency direction explicit.

### Dependency Direction

Allowed direction:

```text
adapters.py -> adapter_models.py
adapters.py -> adapter_registry.py
adapters.py -> adapter_doctor.py
adapters.py -> adapter_setup.py

adapter_registry.py -> adapter_models.py
adapter_resources.py -> adapter_models.py
adapter_wrapper.py -> adapter_models.py
adapter_doctor.py -> adapter_models.py
adapter_doctor.py -> adapter_registry.py
adapter_doctor.py -> adapter_resources.py
adapter_doctor.py -> adapter_wrapper.py
adapter_setup.py -> adapter_models.py
adapter_setup.py -> adapter_registry.py
adapter_setup.py -> adapter_resources.py
adapter_setup.py -> adapter_wrapper.py
adapter_setup.py -> adapter_doctor.py
```

Helper modules must not import `ait.adapters`. Setup may depend on doctor for
post-setup checks; doctor must not depend on setup.

### Public Compatibility Surface

- `ADAPTERS`
- `AdapterAutoEnableResult`
- `AdapterBootstrapResult`
- `AdapterDoctorCheck`
- `AdapterDoctorResult`
- `AdapterError`
- `AdapterSetupResult`
- `AgentAdapter`
- `AutomationDoctorResult`
- `bootstrap_adapter`
- `bootstrap_shell_snippet`
- `doctor_adapter`
- `doctor_automation`
- `enable_available_adapters`
- `get_adapter`
- `list_adapters`
- `setup_adapter`

CLI behavior using this surface must remain compatible for adapter listing,
adapter show/doctor/setup, bootstrap, status, init shell install, parser
choices, JSON output keys, generated settings, generated hooks, wrapper scripts,
and `.envrc` updates.

### Verification Plan

```bash
uv run pytest tests/test_adapters.py
uv run pytest tests/test_cli_adapters.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
PYTHONPATH=src python3 - <<'PY'
from ait.adapters import (
    ADAPTERS, AdapterAutoEnableResult, AdapterBootstrapResult,
    AdapterDoctorCheck, AdapterDoctorResult, AdapterError, AdapterSetupResult,
    AgentAdapter, AutomationDoctorResult, bootstrap_adapter,
    bootstrap_shell_snippet, doctor_adapter, doctor_automation,
    enable_available_adapters, get_adapter, list_adapters, setup_adapter,
)
assert "claude-code" in ADAPTERS
assert get_adapter(None).name == "shell"
assert list_adapters()[0].name == "aider"
print("ait.adapters public imports ok")
PY
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
limits = {"src/ait/adapters.py": 150}
for path in Path("src/ait").glob("adapter_*.py"):
    limits[str(path)] = 400
failures = []
for path, limit in sorted(limits.items()):
    lines = Path(path).read_text(encoding="utf-8").count("\n") + 1
    print(f"{lines:4d} {path}")
    if lines > limit:
        failures.append(f"{path} has {lines} lines > {limit}")
for path in Path("src/ait").glob("adapter_*.py"):
    text = path.read_text(encoding="utf-8")
    if "from ait.adapters" in text or "import ait.adapters" in text:
        failures.append(f"{path} imports ait.adapters")
if failures:
    raise SystemExit("\n".join(failures))
print("adapter architecture gate ok")
PY
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Keep `adapters.py` as facade | Existing CLI and external callers import `ait.adapters` directly | Package conversion or import path changes would create unnecessary compatibility risk |
