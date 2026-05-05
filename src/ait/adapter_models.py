from __future__ import annotations

from dataclasses import dataclass, field


class AdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentAdapter:
    name: str
    default_agent_id: str
    default_with_context: bool
    command_name: str
    env: dict[str, str] = field(default_factory=dict)
    native_hooks: bool = False
    description: str = ""
    setup_hint: str = ""


@dataclass(frozen=True, slots=True)
class AdapterDoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AdapterDoctorResult:
    adapter: AgentAdapter
    checks: tuple[AdapterDoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


@dataclass(frozen=True, slots=True)
class AutomationDoctorResult:
    adapter: AgentAdapter
    checks: tuple[AdapterDoctorCheck, ...]

    @property
    def ok(self) -> bool:
        checks = {check.name: check.ok for check in self.checks}
        required = ["git_repo", "ait_importable", "wrapper_file"]
        if self.adapter.name == "claude-code":
            required.extend(["claude_hook_resource", "claude_settings_resource", "real_claude_binary"])
        else:
            required.append("real_agent_binary")
        if not all(checks.get(name, False) for name in required):
            return False
        return checks.get("path_wrapper_active", False) or checks.get("direnv_env_loaded", False)


@dataclass(frozen=True, slots=True)
class AdapterSetupResult:
    adapter: AgentAdapter
    hook_path: str
    settings_path: str | None
    wrapper_path: str | None
    direnv_path: str | None
    settings: dict[str, object]
    wrote_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdapterBootstrapResult:
    adapter: AgentAdapter
    setup: AdapterSetupResult
    checks: tuple[AdapterDoctorCheck, ...]
    next_steps: tuple[str, ...]

    @property
    def ok(self) -> bool:
        required = {"git_repo", "wrapper_file"}
        required.add("real_claude_binary" if self.adapter.name == "claude-code" else "real_agent_binary")
        return all(check.ok for check in self.checks if check.name in required)


@dataclass(frozen=True, slots=True)
class AdapterAutoEnableResult:
    installed: tuple[AdapterBootstrapResult, ...]
    skipped: tuple[AdapterDoctorCheck, ...]
    shell_snippet: str

    @property
    def ok(self) -> bool:
        return bool(self.installed) and all(result.ok for result in self.installed)
