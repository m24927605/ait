# Contract: Public Adapters Surface

## Stable Imports

The following names must remain importable from `ait.adapters`:

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

## Stable Behaviors

- `get_adapter(None)` returns the shell adapter.
- `get_adapter("missing")` raises `AdapterError` with the text
  `unknown adapter` and the supported adapter list.
- `list_adapters()` returns adapters sorted by name.
- `ADAPTERS` contains the same canonical keys used by CLI parser choices.
- Adapter setup for Claude Code, Codex, and Gemini writes the same native hook
  paths and settings paths.
- Adapter setup for fixed-binary adapters can install repo-local wrappers under
  `.ait/bin/`.
- Bootstrap can install wrappers and `.envrc`, then report next steps from
  doctor checks.
- Doctor result dataclasses keep their field names and `.ok` behavior.
- CLI JSON payload keys derived from result dataclasses remain stable.

## Verification Command

```bash
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
```
