from __future__ import annotations

from dataclasses import asdict
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

from ait.adapters import (
    ADAPTERS,
    doctor_adapter,
    doctor_automation,
    get_adapter,
    list_adapters,
)
from ait.app import init_repo
from ait.daemon import daemon_status
from ait.db import (
    connect_db,
    get_memory_fact,
    list_memory_facts,
    list_memory_retrieval_events,
    run_migrations,
)
from ait.memory import (
    agent_memory_status,
    build_repo_memory,
    lint_memory_notes,
    list_memory_notes,
    memory_health_from_lint,
)
from ait.memory.eval import evaluate_memory_retrievals, render_memory_eval_report
from ait.memory_policy import load_memory_policy
from ait.query import QueryError, execute_query, list_shortcut_expression, parse_blame_target
from ait.repo import resolve_repo_root
from ait.shell_integration import shell_snippet

from ait.cli.runtime_helpers import _format_daemon_lines
from ait.cli_installation import (
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_payload,
)


def _format_adapter(adapter) -> str:
    env_lines = [f"  {key}={value}" for key, value in sorted(adapter.env.items())]
    if not env_lines:
        env_lines = ["  none"]
    lines = [
        f"Adapter: {adapter.name}",
        f"Description: {adapter.description}",
        f"Default agent: {adapter.default_agent_id}",
        f"Default context: {adapter.default_with_context}",
        f"Native hooks: {adapter.native_hooks}",
        "Environment:",
        *env_lines,
        f"Setup: {adapter.setup_hint}",
    ]
    return "\n".join(lines)

def _format_adapter_doctor(
    result,
    *,
    installation: dict[str, object] | None = None,
    daemon: dict[str, object] | None = None,
) -> str:
    lines = [
        f"Adapter: {result.adapter.name}",
        f"OK: {result.ok}",
        "Checks:",
    ]
    for check in result.checks:
        status = "ok" if check.ok else "fail"
        lines.append(f"- {check.name}: {status} ({check.detail})")
    next_steps = _doctor_next_steps(result)
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    if daemon is not None:
        lines.extend(_format_daemon_lines(daemon))
    if installation is not None:
        lines.extend(_format_installation_lines(installation))
    return "\n".join(lines)

def _format_auto_enable(result) -> str:
    lines = ["AIT Agent Automation"]
    if result.installed:
        lines.append("Enabled:")
        for item in result.installed:
            wrapper_path = item.setup.wrapper_path or ""
            lines.append(f"- {item.adapter.name}: {wrapper_path}")
    else:
        lines.append("Enabled: none")
    if result.skipped:
        lines.append("Skipped:")
        for item in result.skipped:
            lines.append(f"- {item.name}: {item.detail}")
    if result.shell_snippet:
        lines.append("Current shell:")
        lines.append(f'- eval "$(ait enable --shell)"')
        lines.append("Next:")
        for item in result.installed:
            command = item.adapter.command_name
            if command:
                lines.append(f"- {command} ...")
    return "\n".join(lines)

def _doctor_next_steps(result) -> list[str]:
    checks = {check.name: check.ok for check in result.checks}
    if result.ok:
        return []
    if not checks.get("git_repo", True):
        return ["ait init"]
    if "automation" in checks and not checks["automation"]:
        return []
    if not checks.get("wrapper_file", True):
        return [f"ait init --adapter {result.adapter.name}"]
    real_binary_ok = checks.get("real_claude_binary", checks.get("real_agent_binary", True))
    if not real_binary_ok:
        binary = result.adapter.command_name or result.adapter.name
        return [f"install {binary} or put the real {binary} binary on PATH"]
    if not checks.get("path_wrapper_active", True):
        if checks.get("envrc_path", False) and checks.get("direnv_binary", False):
            return ["direnv allow", 'eval "$(ait init --shell)"']
        return ['eval "$(ait init --shell)"']
    return []

def _agent_cli_message(payload: dict[str, object]) -> str:
    adapter = str(payload["adapter"])
    command = _agent_command_name(adapter)
    if payload["ok"]:
        return f"ready: run {command} ..."
    if not payload["git_repo"]:
        return "not ready: run ait init"
    if not payload["real_agent_binary"]:
        return f"not ready: install {command} or put the real {command} binary on PATH"
    if not payload["wrapper_installed"]:
        return f"not ready: run ait init --adapter {adapter}"
    if not payload["path_wrapper_active"]:
        if payload["direnv_available"]:
            return f"not ready in this shell: run direnv allow once, then run {command} ..."
        return f"not ready in this shell: run eval \"$(ait init --shell)\", then run {command} ..."
    return "not ready: inspect next_steps"

def _agent_cli_summary(payload: dict[str, object]) -> str:
    adapter = str(payload["adapter"])
    command = _agent_command_name(adapter)
    if payload["agent_cli_ready"]:
        return f"ready, run {command} ..."
    if not payload["git_repo"]:
        return "run ait init"
    if not payload["real_agent_binary"]:
        return f"install {command}"
    if not payload["wrapper_installed"]:
        return f"run ait init --adapter {adapter}"
    if not payload["path_wrapper_active"]:
        if payload["direnv_available"]:
            return "run direnv allow once"
        return 'run eval "$(ait init --shell)"'
    return "not ready, inspect JSON status"

def _agent_command_name(adapter: str) -> str:
    return "claude" if adapter == "claude-code" else adapter

def _format_bootstrap(result) -> str:
    lines = [
        f"Adapter: {result.adapter.name}",
        f"OK: {result.ok}",
        "Wrote:",
    ]
    lines.extend(f"- {path}" for path in result.setup.wrote_files)
    if result.next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in result.next_steps)
    return "\n".join(lines)
