from __future__ import annotations

from ait.adapter_doctor import doctor_adapter, doctor_automation
from ait.adapter_models import (
    AdapterAutoEnableResult,
    AdapterBootstrapResult,
    AdapterDoctorCheck,
    AdapterDoctorResult,
    AdapterError,
    AdapterSetupResult,
    AgentAdapter,
    AutomationDoctorResult,
)
from ait.adapter_registry import ADAPTERS, get_adapter, list_adapters
from ait.adapter_resources import (
    _claude_code_settings,
    _codex_hooks_settings,
    _gemini_settings,
    _merge_settings,
    _read_adapter_resource,
    _read_claude_resource,
    _read_json_object,
    _resolve_target,
    _resource_exists,
)
from ait.adapter_setup import (
    bootstrap_adapter,
    bootstrap_shell_snippet,
    enable_available_adapters,
    setup_adapter,
)
from ait.adapter_wrapper import (
    _adapter_wrapper_script,
    _envrc_has_wrapper_path,
    _find_real_binary,
    _merge_envrc,
    _real_agent_binary_check,
    _real_claude_check,
    _same_file,
)

__all__ = [
    "ADAPTERS",
    "AdapterAutoEnableResult",
    "AdapterBootstrapResult",
    "AdapterDoctorCheck",
    "AdapterDoctorResult",
    "AdapterError",
    "AdapterSetupResult",
    "AgentAdapter",
    "AutomationDoctorResult",
    "bootstrap_adapter",
    "bootstrap_shell_snippet",
    "doctor_adapter",
    "doctor_automation",
    "enable_available_adapters",
    "get_adapter",
    "list_adapters",
    "setup_adapter",
]
