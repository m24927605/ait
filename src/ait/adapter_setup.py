from __future__ import annotations

import json
from pathlib import Path
import shlex

from ait.adapter_doctor import doctor_automation
from ait.adapter_models import (
    AdapterAutoEnableResult,
    AdapterBootstrapResult,
    AdapterDoctorCheck,
    AdapterError,
    AdapterSetupResult,
)
from ait.adapter_registry import ADAPTERS, get_adapter
from ait.adapter_resources import (
    _claude_code_settings,
    _codex_hooks_settings,
    _gemini_settings,
    _merge_settings,
    _read_adapter_resource,
    _read_claude_resource,
    _read_json_object,
    _resolve_target,
)
from ait.adapter_wrapper import (
    _adapter_wrapper_script,
    _find_real_binary,
    _merge_envrc,
    _real_agent_binary_check,
    _real_claude_check,
)
from ait.repo import resolve_repo_root


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
    elif adapter.name == "gemini":
        hook_path = hook_path / "gemini_hook.py"
    wrapper_path = root / ".ait" / "bin" / adapter.command_name
    direnv_path = root / ".envrc"
    if target is not None:
        settings_path = _resolve_target(root, target)
    elif adapter.name == "claude-code":
        settings_path = root / ".claude" / "settings.json"
    elif adapter.name == "codex":
        settings_path = root / ".codex" / "hooks.json"
    elif adapter.name == "gemini":
        settings_path = root / ".gemini" / "settings.json"
    else:
        settings_path = None
    if adapter.name == "claude-code":
        settings = _claude_code_settings()
    elif adapter.name == "codex":
        settings = _codex_hooks_settings()
    elif adapter.name == "gemini":
        settings = _gemini_settings()
    else:
        settings = {}
    install_wrapper = install_wrapper or install_direnv
    if adapter.name not in {"claude-code", "codex", "gemini"}:
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
        elif adapter.name == "gemini":
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            hook_path.write_text(
                _read_adapter_resource("gemini", "gemini_hook.py"),
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
