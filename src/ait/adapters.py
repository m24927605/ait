from __future__ import annotations

from dataclasses import dataclass, field


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
