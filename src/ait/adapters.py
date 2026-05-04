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
        description="Gemini CLI wrapper with context enabled by default.",
        setup_hint="Use ait bootstrap gemini to install a repo-local wrapper.",
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
        hook = _resource_exists("claude-code", "claude_code_hook.py")
        settings = _resource_exists("claude-code", "claude-code-settings.json")
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
    elif adapter.name == "codex":
        hook = _resource_exists("codex", "codex_hook.py")
        settings = _resource_exists("codex", "codex-hooks.json")
        checks.append(
            AdapterDoctorCheck(
                "codex_hook_resource",
                hook,
                "ait.resources.codex/codex_hook.py",
            )
        )
        checks.append(
            AdapterDoctorCheck(
                "codex_settings_resource",
                settings,
                "ait.resources.codex/codex-hooks.json",
            )
        )
    else:
        checks.append(
            AdapterDoctorCheck(
                "native_hooks",
                not adapter.native_hooks,
                "native hook doctor is only implemented for claude-code and codex",
            )
        )

    return AdapterDoctorResult(adapter=adapter, checks=tuple(checks))


def doctor_automation(name: str, repo_root: str | Path) -> AutomationDoctorResult:
    adapter = get_adapter(name)
    checks = list(doctor_adapter(name, repo_root).checks)

    try:
        root = resolve_repo_root(Path(repo_root).resolve())
    except ValueError:
        return AutomationDoctorResult(adapter=adapter, checks=tuple(checks))

    if adapter.name == "shell":
        checks.append(AdapterDoctorCheck("automation", False, "shell adapter has no fixed binary wrapper"))
        return AutomationDoctorResult(adapter=adapter, checks=tuple(checks))

    wrapper_path = root / ".ait" / "bin" / adapter.command_name
    envrc_path = root / ".envrc"
    active_binary = shutil.which(adapter.command_name)
    direnv = shutil.which("direnv")
    real_binary_check = (
        _real_claude_check(wrapper_path)
        if adapter.name == "claude-code"
        else _real_agent_binary_check(adapter, wrapper_path)
    )

    checks.extend(
        [
            AdapterDoctorCheck(
                "wrapper_file",
                wrapper_path.is_file() and os.access(wrapper_path, os.X_OK),
                str(wrapper_path),
            ),
            AdapterDoctorCheck(
                "path_wrapper_active",
                active_binary is not None and Path(active_binary).resolve() == wrapper_path.resolve(),
                active_binary or f"{adapter.command_name} not found on PATH",
            ),
            AdapterDoctorCheck(
                "direnv_binary",
                direnv is not None,
                direnv or "direnv not found; use export PATH=\"$PWD/.ait/bin:$PATH\"",
            ),
            AdapterDoctorCheck(
                "envrc_path",
                _envrc_has_wrapper_path(envrc_path),
                str(envrc_path),
            ),
            AdapterDoctorCheck(
                "direnv_env_loaded",
                Path(os.environ.get("DIRENV_FILE", "")).resolve() == envrc_path.resolve(),
                os.environ.get("DIRENV_FILE") or "current shell has not loaded this .envrc",
            ),
            real_binary_check,
        ]
    )
    return AutomationDoctorResult(adapter=adapter, checks=tuple(checks))


def bootstrap_adapter(name: str, repo_root: str | Path) -> AdapterBootstrapResult:
    setup = setup_adapter(name, repo_root, install_wrapper=True, install_direnv=True)
    doctor = doctor_automation(name, repo_root)
    next_steps: list[str] = []
    check_by_name = {check.name: check for check in doctor.checks}
    if not check_by_name.get("direnv_binary", AdapterDoctorCheck("", False, "")).ok:
        next_steps.append('export PATH="$PWD/.ait/bin:$PATH"')
    elif not check_by_name.get("path_wrapper_active", AdapterDoctorCheck("", False, "")).ok:
        next_steps.append("direnv allow")
    return AdapterBootstrapResult(
        adapter=setup.adapter,
        setup=setup,
        checks=doctor.checks,
        next_steps=tuple(next_steps),
    )


def bootstrap_shell_snippet(name: str, repo_root: str | Path) -> str:
    result = bootstrap_adapter(name, repo_root)
    if result.setup.wrapper_path is None:
        raise AdapterError("bootstrap did not install a wrapper")
    wrapper_dir = Path(result.setup.wrapper_path).parent
    return f"export PATH={shlex.quote(str(wrapper_dir))}:\"$PATH\""


def enable_available_adapters(
    repo_root: str | Path,
    *,
    names: tuple[str, ...] | None = None,
) -> AdapterAutoEnableResult:
    try:
        root = resolve_repo_root(Path(repo_root).resolve())
    except ValueError as exc:
        raise AdapterError(str(exc)) from exc
    selected = names or tuple(name for name in sorted(ADAPTERS) if name != "shell")
    installed: list[AdapterBootstrapResult] = []
    skipped: list[AdapterDoctorCheck] = []
    for name in selected:
        adapter = get_adapter(name)
        if adapter.name == "shell":
            skipped.append(AdapterDoctorCheck(adapter.name, False, "shell adapter has no fixed binary wrapper"))
            continue
        wrapper_path = root / ".ait" / "bin" / adapter.command_name
        real_check = (
            _real_claude_check(wrapper_path)
            if adapter.name == "claude-code"
            else _real_agent_binary_check(adapter, wrapper_path)
        )
        if not real_check.ok:
            skipped.append(AdapterDoctorCheck(adapter.name, False, real_check.detail))
            continue
        installed.append(bootstrap_adapter(adapter.name, root))

    shell_snippet = ""
    if installed:
        wrapper_path = installed[0].setup.wrapper_path
        if wrapper_path is not None:
            wrapper_dir = Path(wrapper_path).parent.resolve()
            shell_snippet = f"export PATH={shlex.quote(str(wrapper_dir))}:\"$PATH\""
    return AdapterAutoEnableResult(
        installed=tuple(installed),
        skipped=tuple(skipped),
        shell_snippet=shell_snippet,
    )


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
    if adapter.name == "shell":
        raise AdapterError("adapter setup is not implemented for shell")

    try:
        root = resolve_repo_root(Path(repo_root).resolve())
    except ValueError as exc:
        raise AdapterError(str(exc)) from exc
    hook_path = root / ".ait" / "adapters" / adapter.name
    if adapter.name == "claude-code":
        hook_path = hook_path / "claude_code_hook.py"
    elif adapter.name == "codex":
        hook_path = hook_path / "codex_hook.py"
    wrapper_path = root / ".ait" / "bin" / adapter.command_name
    direnv_path = root / ".envrc"
    if target is not None:
        settings_path = _resolve_target(root, target)
    elif adapter.name == "claude-code":
        settings_path = root / ".claude" / "settings.json"
    elif adapter.name == "codex":
        settings_path = root / ".codex" / "hooks.json"
    else:
        settings_path = None
    if adapter.name == "claude-code":
        settings = _claude_code_settings()
    elif adapter.name == "codex":
        settings = _codex_hooks_settings()
    else:
        settings = {}
    install_wrapper = install_wrapper or install_direnv
    if adapter.name not in {"claude-code", "codex"}:
        install_wrapper = True

    wrote_files: list[str] = []
    if not print_only:
        if adapter.name == "claude-code":
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text(_read_claude_resource("claude_code_hook.py"), encoding="utf-8")
            wrote_files.append(str(hook_path))

            assert settings_path is not None
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            merged = _merge_settings(_read_json_object(settings_path), settings)
            settings_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            wrote_files.append(str(settings_path))
        elif adapter.name == "codex":
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text(
                _read_adapter_resource("codex", "codex_hook.py"),
                encoding="utf-8",
            )
            wrote_files.append(str(hook_path))

            assert settings_path is not None
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            merged = _merge_settings(_read_json_object(settings_path), settings)
            settings_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            wrote_files.append(str(settings_path))

        if install_wrapper:
            real_binary = _find_real_binary(adapter.command_name, wrapper_path)
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(_adapter_wrapper_script(adapter, real_binary), encoding="utf-8")
            wrapper_path.chmod(0o755)
            wrote_files.append(str(wrapper_path))

        if install_direnv:
            _merge_envrc(direnv_path)
            wrote_files.append(str(direnv_path))

    return AdapterSetupResult(
        adapter=adapter,
        hook_path=str(hook_path),
        settings_path=str(settings_path) if settings_path is not None and not print_only else None,
        wrapper_path=str(wrapper_path) if install_wrapper and not print_only else None,
        direnv_path=str(direnv_path) if install_direnv and not print_only else None,
        settings=settings,
        wrote_files=tuple(wrote_files),
    )


def _resource_exists(adapter_dir: str, name: str) -> bool:
    try:
        return resources.files("ait").joinpath("resources", adapter_dir, name).is_file()
    except Exception:
        return False


def _read_adapter_resource(adapter_dir: str, name: str) -> str:
    return (
        resources.files("ait")
        .joinpath("resources", adapter_dir, name)
        .read_text(encoding="utf-8")
    )


def _read_claude_resource(name: str) -> str:
    return _read_adapter_resource("claude-code", name)


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


def _codex_hooks_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"$CODEX_PROJECT_DIR/.ait/adapters/codex/codex_hook.py"'
    )
    tool_events = {
        "matcher": "Read|Grep|Glob|LS|Write|Edit|MultiEdit|NotebookEdit|Bash|shell|apply_patch",
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


def _envrc_has_wrapper_path(path: Path) -> bool:
    if not path.exists():
        return False
    return "PATH_add .ait/bin" in path.read_text(encoding="utf-8").splitlines()


def _real_claude_check(wrapper_path: Path) -> AdapterDoctorCheck:
    try:
        real_claude = _find_real_binary("claude", wrapper_path)
    except AdapterError as exc:
        return AdapterDoctorCheck("real_claude_binary", False, str(exc))
    return AdapterDoctorCheck("real_claude_binary", True, real_claude)


def _real_agent_binary_check(adapter: AgentAdapter, wrapper_path: Path) -> AdapterDoctorCheck:
    try:
        real_binary = _find_real_binary(adapter.command_name, wrapper_path)
    except AdapterError as exc:
        return AdapterDoctorCheck("real_agent_binary", False, str(exc))
    return AdapterDoctorCheck("real_agent_binary", True, real_binary)


def _find_real_binary(command_name: str, wrapper_path: Path) -> str:
    wrapper = wrapper_path
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / command_name
        if _same_file(candidate, wrapper):
            continue
        resolved = candidate.resolve()
        if _same_file(resolved, wrapper):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    found = shutil.which(command_name)
    if found is None:
        raise AdapterError(f"could not find {command_name} on PATH")
    if _same_file(Path(found), wrapper_path):
        raise AdapterError(f"could not find real {command_name} on PATH")
    return found


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve(strict=False) == right.resolve(strict=False)


def _adapter_wrapper_script(adapter: AgentAdapter, real_binary: str) -> str:
    ait_executable = Path(sys.executable).with_name("ait")
    ait_command = str(ait_executable) if ait_executable.exists() else "ait"
    intent = {
        "claude-code": "Claude Code session",
        "aider": "Aider session",
        "codex": "Codex session",
    }.get(adapter.name, f"{adapter.name} session")
    commit_message = {
        "claude-code": "claude code changes",
        "aider": "aider changes",
        "codex": "codex changes",
    }.get(adapter.name, f"{adapter.name} changes")
    real_command = adapter.command_name
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f"AIT_WRAPPER_ADAPTER={shlex.quote(adapter.name)}\n"
        f"AIT_WRAPPER_COMMAND={shlex.quote(real_command)}\n"
        f"AIT_WRAPPER_REAL_BINARY={shlex.quote(real_binary)}\n"
        f"AIT_WRAPPER_AIT_COMMAND={shlex.quote(ait_command)}\n"
        'AIT_WRAPPER_PATH="${0}"\n'
        'AIT_WRAPPER_REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"\n'
        "export AIT_WRAPPER_ADAPTER AIT_WRAPPER_COMMAND AIT_WRAPPER_REAL_BINARY AIT_WRAPPER_PATH AIT_WRAPPER_REPO\n"
        'if [ ! -x "$AIT_WRAPPER_REAL_BINARY" ]; then\n'
        '  printf "%s\\n" "ait wrapper failed: real ${AIT_WRAPPER_COMMAND} binary not found or not executable" >&2\n'
        '  printf "%s\\n" "adapter: ${AIT_WRAPPER_ADAPTER}" >&2\n'
        '  printf "%s\\n" "repo: ${AIT_WRAPPER_REPO}" >&2\n'
        '  printf "%s\\n" "wrapper: ${AIT_WRAPPER_PATH}" >&2\n'
        '  printf "%s\\n" "real_binary: ${AIT_WRAPPER_REAL_BINARY}" >&2\n'
        '  printf "%s\\n" "next: run ait status ${AIT_WRAPPER_ADAPTER}" >&2\n'
        "  exit 127\n"
        "fi\n"
        'if [ "$AIT_WRAPPER_REAL_BINARY" = "$AIT_WRAPPER_PATH" ]; then\n'
        '  printf "%s\\n" "ait wrapper failed: wrapper recursion detected" >&2\n'
        '  printf "%s\\n" "adapter: ${AIT_WRAPPER_ADAPTER}" >&2\n'
        '  printf "%s\\n" "repo: ${AIT_WRAPPER_REPO}" >&2\n'
        '  printf "%s\\n" "wrapper: ${AIT_WRAPPER_PATH}" >&2\n'
        '  printf "%s\\n" "real_binary: ${AIT_WRAPPER_REAL_BINARY}" >&2\n'
        '  printf "%s\\n" "next: run ait init --adapter ${AIT_WRAPPER_ADAPTER} --shell" >&2\n'
        "  exit 126\n"
        "fi\n"
        f': "${{AIT_INTENT:={intent}}}"\n'
        f': "${{AIT_COMMIT_MESSAGE:={commit_message}}}"\n'
        'if [ -t 0 ] && [ -t 1 ]; then\n'
        '  AIT_WRAPPER_FORMAT=text\n'
        "else\n"
        '  AIT_WRAPPER_FORMAT=json\n'
        "fi\n"
        'exec "$AIT_WRAPPER_AIT_COMMAND" '
        f"run --adapter {shlex.quote(adapter.name)} --format \"$AIT_WRAPPER_FORMAT\" "
        '--intent "$AIT_INTENT" --commit-message "$AIT_COMMIT_MESSAGE" -- '
        '"$AIT_WRAPPER_REAL_BINARY" "$@"\n'
    )
