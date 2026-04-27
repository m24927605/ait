from __future__ import annotations

from dataclasses import dataclass, field
import json
from importlib import resources
from importlib.util import find_spec
import os
from pathlib import Path
import shlex
import shutil
import sys

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


@dataclass(frozen=True, slots=True)
class AdapterSetupResult:
    adapter: AgentAdapter
    hook_path: str
    settings_path: str | None
    wrapper_path: str | None
    direnv_path: str | None
    settings: dict[str, object]
    wrote_files: tuple[str, ...]


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
            "Use packaged resources claude_code_hook.py and "
            "claude-code-settings.json for native Claude Code hook event capture."
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
        hook = _resource_exists("claude_code_hook.py")
        settings = _resource_exists("claude-code-settings.json")
        checks.append(
            AdapterDoctorCheck(
                "claude_hook_resource",
                hook,
                "ait.resources.claude-code/claude_code_hook.py",
            )
        )
        checks.append(
            AdapterDoctorCheck(
                "claude_settings_resource",
                settings,
                "ait.resources.claude-code/claude-code-settings.json",
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


def setup_adapter(
    name: str,
    repo_root: str | Path,
    *,
    target: str | Path | None = None,
    print_only: bool = False,
    install_wrapper: bool = False,
    install_direnv: bool = False,
) -> AdapterSetupResult:
    adapter = get_adapter(name)
    if adapter.name != "claude-code":
        raise AdapterError(f"adapter setup is not implemented for {adapter.name}")

    try:
        root = resolve_repo_root(Path(repo_root).resolve())
    except ValueError as exc:
        raise AdapterError(str(exc)) from exc
    hook_path = root / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
    wrapper_path = root / ".ait" / "bin" / "claude"
    direnv_path = root / ".envrc"
    settings_path = (
        _resolve_target(root, target)
        if target is not None
        else root / ".claude" / "settings.json"
    )
    settings = _claude_code_settings()
    install_wrapper = install_wrapper or install_direnv

    wrote_files: list[str] = []
    if not print_only:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(_read_claude_resource("claude_code_hook.py"), encoding="utf-8")
        wrote_files.append(str(hook_path))

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        merged = _merge_settings(_read_json_object(settings_path), settings)
        settings_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        wrote_files.append(str(settings_path))

        if install_wrapper:
            real_claude = _find_real_claude(wrapper_path)
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(_claude_wrapper_script(real_claude), encoding="utf-8")
            wrapper_path.chmod(0o755)
            wrote_files.append(str(wrapper_path))

        if install_direnv:
            _merge_envrc(direnv_path)
            wrote_files.append(str(direnv_path))

    return AdapterSetupResult(
        adapter=adapter,
        hook_path=str(hook_path),
        settings_path=str(settings_path) if not print_only else None,
        wrapper_path=str(wrapper_path) if install_wrapper and not print_only else None,
        direnv_path=str(direnv_path) if install_direnv and not print_only else None,
        settings=settings,
        wrote_files=tuple(wrote_files),
    )


def _resource_exists(name: str) -> bool:
    try:
        return resources.files("ait").joinpath("resources", "claude-code", name).is_file()
    except Exception:
        return False


def _read_claude_resource(name: str) -> str:
    return (
        resources.files("ait")
        .joinpath("resources", "claude-code", name)
        .read_text(encoding="utf-8")
    )


def _resolve_target(repo_root: Path, target: str | Path) -> Path:
    path = Path(target)
    if path.is_absolute():
        return path
    return repo_root / path


def _claude_code_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"$CLAUDE_PROJECT_DIR/.ait/adapters/claude-code/claude_code_hook.py"'
    )
    tool_events = {
        "matcher": "Read|Grep|Glob|LS|Write|Edit|MultiEdit|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": command}],
    }
    session_events = {"hooks": [{"type": "command", "command": command}]}
    return {
        "hooks": {
            "SessionStart": [session_events],
            "PostToolUse": [tool_events],
            "PostToolUseFailure": [tool_events],
            "Stop": [session_events],
            "SessionEnd": [session_events],
        }
    }


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AdapterError(f"settings file must contain a JSON object: {path}")
    return data


def _merge_settings(existing: dict[str, object], generated: dict[str, object]) -> dict[str, object]:
    merged = dict(existing)
    existing_hooks = merged.setdefault("hooks", {})
    if not isinstance(existing_hooks, dict):
        raise AdapterError("settings hooks must be a JSON object")

    generated_hooks = generated.get("hooks", {})
    if not isinstance(generated_hooks, dict):
        raise AdapterError("generated hooks must be a JSON object")

    for event_name, generated_entries in generated_hooks.items():
        if not isinstance(generated_entries, list):
            raise AdapterError(f"generated hook entries must be a list: {event_name}")
        existing_entries = existing_hooks.setdefault(event_name, [])
        if not isinstance(existing_entries, list):
            raise AdapterError(f"settings hook entries must be a list: {event_name}")
        for entry in generated_entries:
            if entry not in existing_entries:
                existing_entries.append(entry)
    return merged


def _merge_envrc(path: Path) -> None:
    marker = "# ait: add repo-local adapter wrappers"
    path_line = "PATH_add .ait/bin"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if path_line in text.splitlines():
            return
        if text and not text.endswith("\n"):
            text += "\n"
    else:
        text = ""
    path.write_text(f"{text}{marker}\n{path_line}\n", encoding="utf-8")


def _find_real_claude(wrapper_path: Path) -> str:
    wrapper = wrapper_path.resolve()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = (Path(directory) / "claude").resolve()
        if candidate == wrapper:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("claude")
    if found is None:
        raise AdapterError("could not find claude on PATH")
    return found


def _claude_wrapper_script(real_claude: str) -> str:
    ait_executable = Path(sys.executable).with_name("ait")
    ait_command = str(ait_executable) if ait_executable.exists() else "ait"
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        ': "${AIT_INTENT:=Claude Code session}"\n'
        ': "${AIT_COMMIT_MESSAGE:=claude code changes}"\n'
        f"exec {shlex.quote(ait_command)} run --adapter claude-code --format json "
        '--intent "$AIT_INTENT" --commit-message "$AIT_COMMIT_MESSAGE" -- '
        f"{shlex.quote(real_claude)} \"$@\"\n"
    )
