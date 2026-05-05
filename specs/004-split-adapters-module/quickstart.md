# Quickstart: Split Adapters Module

## 1. Baseline Adapter Behavior

```bash
uv run pytest tests/test_adapters.py
```

## 2. Targeted Adapter Consumers

```bash
uv run pytest tests/test_cli_adapters.py tests/test_claude_code_hook.py tests/test_codex_hook.py tests/test_gemini_hook.py
```

## 3. Public Import Contract

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

## 4. Architecture Gate

```bash
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

## 5. Full Verification

```bash
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```
