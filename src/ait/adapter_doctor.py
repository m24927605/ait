from __future__ import annotations

from importlib.util import find_spec
import os
from pathlib import Path
import shutil

from ait.adapter_models import AdapterDoctorCheck, AdapterDoctorResult, AutomationDoctorResult
from ait.adapter_registry import get_adapter
from ait.adapter_resources import _resource_exists
from ait.adapter_wrapper import _envrc_has_wrapper_path, _real_agent_binary_check, _real_claude_check
from ait.repo import resolve_repo_root


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
    elif adapter.name == "gemini":
        hook = _resource_exists("gemini", "gemini_hook.py")
        settings = _resource_exists("gemini", "gemini-settings.json")
        checks.append(
            AdapterDoctorCheck(
                "gemini_hook_resource",
                hook,
                "ait.resources.gemini/gemini_hook.py",
            )
        )
        checks.append(
            AdapterDoctorCheck(
                "gemini_settings_resource",
                settings,
                "ait.resources.gemini/gemini-settings.json",
            )
        )
    else:
        checks.append(
            AdapterDoctorCheck(
                "native_hooks",
                not adapter.native_hooks,
                "native hook doctor is only implemented for claude-code, codex, and gemini",
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
