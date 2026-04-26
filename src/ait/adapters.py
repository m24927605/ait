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


ADAPTERS: dict[str, AgentAdapter] = {
    "shell": AgentAdapter(
        name="shell",
        default_agent_id="shell:local",
        default_with_context=False,
    ),
    "claude-code": AgentAdapter(
        name="claude-code",
        default_agent_id="claude-code:manual",
        default_with_context=True,
        env={
            "AIT_ADAPTER": "claude-code",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
    ),
    "aider": AgentAdapter(
        name="aider",
        default_agent_id="aider:main",
        default_with_context=True,
        env={"AIT_ADAPTER": "aider"},
    ),
    "codex": AgentAdapter(
        name="codex",
        default_agent_id="codex:main",
        default_with_context=True,
        env={"AIT_ADAPTER": "codex"},
    ),
}


def get_adapter(name: str | None) -> AgentAdapter:
    adapter_name = name or "shell"
    adapter = ADAPTERS.get(adapter_name)
    if adapter is None:
        choices = ", ".join(sorted(ADAPTERS))
        raise AdapterError(f"unknown adapter: {adapter_name}; expected one of: {choices}")
    return adapter
