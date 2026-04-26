from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path

from ait.repo import resolve_repo_root


class AdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentAdapter:
    name: str
    default_agent_id: str
    default_with_context: bool
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


ADAPTERS: dict[str, AgentAdapter] = {
    "shell": AgentAdapter(
        name="shell",
        default_agent_id="shell:local",
        default_with_context=False,
        description="Generic shell command wrapper.",
        setup_hint="No setup required; pass a command after --.",
    ),
    "claude-code": AgentAdapter(
        name="claude-code",
        default_agent_id="claude-code:manual",
        default_with_context=True,
        env={
            "AIT_ADAPTER": "claude-code",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        native_hooks=True,
        description="Claude Code CLI wrapper with context enabled by default.",
        setup_hint=(
            "Use examples/claude_code_hook.py and examples/claude-code-settings.json "
            "for native Claude Code hook event capture."
        ),
    ),
    "aider": AgentAdapter(
        name="aider",
        default_agent_id="aider:main",
        default_with_context=True,
        env={"AIT_ADAPTER": "aider"},
        description="Aider CLI wrapper with context enabled by default.",
        setup_hint="Run aider after --; native hook capture is not implemented yet.",
    ),
    "codex": AgentAdapter(
        name="codex",
        default_agent_id="codex:main",
        default_with_context=True,
        env={"AIT_ADAPTER": "codex"},
        description="Codex CLI wrapper with context enabled by default.",
        setup_hint="Run codex after --; native hook capture is not implemented yet.",
    ),
}


def get_adapter(name: str | None) -> AgentAdapter:
    adapter_name = name or "shell"
    adapter = ADAPTERS.get(adapter_name)
    if adapter is None:
        choices = ", ".join(sorted(ADAPTERS))
        raise AdapterError(f"unknown adapter: {adapter_name}; expected one of: {choices}")
    return adapter


def list_adapters() -> tuple[AgentAdapter, ...]:
    return tuple(ADAPTERS[name] for name in sorted(ADAPTERS))


def doctor_adapter(name: str, repo_root: str | Path) -> AdapterDoctorResult:
    adapter = get_adapter(name)
    root = Path(repo_root).resolve()
    checks: list[AdapterDoctorCheck] = []

    try:
        resolved_root = resolve_repo_root(root)
        checks.append(AdapterDoctorCheck("git_repo", True, str(resolved_root)))
    except Exception as exc:
        checks.append(AdapterDoctorCheck("git_repo", False, str(exc)))
        resolved_root = root

    ait_spec = find_spec("ait")
    checks.append(
        AdapterDoctorCheck(
            "ait_importable",
            ait_spec is not None,
            "ait package importable" if ait_spec is not None else "ait package not importable",
        )
    )

    if adapter.name == "claude-code":
        hook_path = resolved_root / "examples" / "claude_code_hook.py"
        settings_path = resolved_root / "examples" / "claude-code-settings.json"
        checks.append(
            AdapterDoctorCheck(
                "claude_hook_example",
                hook_path.exists(),
                str(hook_path),
            )
        )
        checks.append(
            AdapterDoctorCheck(
                "claude_settings_example",
                settings_path.exists(),
                str(settings_path),
            )
        )
    else:
        checks.append(
            AdapterDoctorCheck(
                "native_hooks",
                not adapter.native_hooks,
                "native hook doctor is only implemented for claude-code",
            )
        )

    return AdapterDoctorResult(adapter=adapter, checks=tuple(checks))
