from __future__ import annotations

from ait.adapter_models import AdapterError, AgentAdapter


ADAPTERS: dict[str, AgentAdapter] = {
    "shell": AgentAdapter(
        name="shell",
        default_agent_id="shell:local",
        default_with_context=False,
        command_name="",
        description="Generic shell command wrapper.",
        setup_hint="No setup required; pass a command after --.",
    ),
    "claude-code": AgentAdapter(
        name="claude-code",
        default_agent_id="claude-code:manual",
        default_with_context=True,
        command_name="claude",
        env={
            "AIT_ADAPTER": "claude-code",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        native_hooks=True,
        description="Claude Code CLI wrapper with context enabled by default.",
        setup_hint=(
            "Use packaged resources claude_code_hook.py and "
            "claude-code-settings.json for native Claude Code hook event capture."
        ),
    ),
    "aider": AgentAdapter(
        name="aider",
        default_agent_id="aider:main",
        default_with_context=True,
        command_name="aider",
        env={
            "AIT_ADAPTER": "aider",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        description="Aider CLI wrapper with context enabled by default.",
        setup_hint="Use ait bootstrap aider to install a repo-local wrapper.",
    ),
    "codex": AgentAdapter(
        name="codex",
        default_agent_id="codex:main",
        default_with_context=True,
        command_name="codex",
        env={
            "AIT_ADAPTER": "codex",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        native_hooks=True,
        description="Codex CLI wrapper with context enabled by default.",
        setup_hint=(
            "Use packaged resources codex_hook.py and codex-hooks.json for "
            "native Codex CLI hook event capture into .ait/transcripts/."
        ),
    ),
    "cursor": AgentAdapter(
        name="cursor",
        default_agent_id="cursor:main",
        default_with_context=True,
        command_name="cursor",
        env={
            "AIT_ADAPTER": "cursor",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        description="Cursor CLI wrapper with context enabled by default.",
        setup_hint="Use ait bootstrap cursor to install a repo-local wrapper.",
    ),
    "gemini": AgentAdapter(
        name="gemini",
        default_agent_id="gemini:main",
        default_with_context=True,
        command_name="gemini",
        env={
            "AIT_ADAPTER": "gemini",
            "AIT_CONTEXT_HINT": "Read AIT_CONTEXT_FILE before starting work.",
        },
        native_hooks=True,
        description="Gemini CLI wrapper with context enabled by default.",
        setup_hint=(
            "Use packaged resources gemini_hook.py and gemini-settings.json "
            "for native Gemini CLI hook event capture into .ait/transcripts/."
        ),
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
