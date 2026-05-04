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
from ait.shell_integration import (
    ShellIntegrationError,
    detect_user_shell,
    install_shell_integration,
    is_shell_integration_installed,
    shell_snippet,
)

from ait.cli.adapter_helpers import _agent_command_name
from ait.cli.status_helpers import _status_payload
from ait.cli_installation import (
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_payload,
)


def _maybe_auto_install_shell_hook(
    *,
    skip: bool,
    installed_adapters,
) -> dict[str, object]:
    """Best-effort install of the per-cd shell hook into the user's rc.

    Skipped (returns ``status="skipped"``) when:
    - the user passed ``--no-shell-install``
    - no adapters were installed (nothing to wire onto PATH)
    - the user's shell is not zsh or bash (e.g. fish)
    - the hook is already installed (idempotent no-op)
    - writing the rc file fails (filesystem permissions, etc.)
    """
    if skip:
        return {"status": "skipped", "reason": "--no-shell-install"}
    if not installed_adapters:
        return {"status": "skipped", "reason": "no adapters installed"}
    detected_shell = detect_user_shell()
    if detected_shell is None:
        return {"status": "skipped", "reason": "shell not zsh or bash"}
    if is_shell_integration_installed(detected_shell):
        return {"status": "already_installed", "shell": detected_shell}
    try:
        result = install_shell_integration(shell=detected_shell)
    except (ShellIntegrationError, OSError) as exc:
        return {"status": "skipped", "reason": str(exc), "shell": detected_shell}
    return {
        "status": "installed",
        "shell": detected_shell,
        "rc_path": result.rc_path,
    }


def _init_payload(
    init_result,
    automation,
    statuses,
    memory_import=None,
    memory_policy=None,
    *,
    shell_install: dict[str, object] | None = None,
) -> dict[str, object]:
    status_payloads = [_status_payload(status) for status in statuses]
    payload = {
        "repo_root": str(init_result.repo_root),
        "ait_dir": str(init_result.ait_dir),
        "db_path": str(init_result.db_path),
        "repo_id": init_result.repo_id,
        "socket_path": str(init_result.socket_path),
        "git_initialized": init_result.git_initialized,
        "baseline_commit_created": init_result.baseline_commit_created,
        "installed_adapters": [item.adapter.name for item in automation.installed],
        "skipped_adapters": [asdict(item) for item in automation.skipped],
        "shell_snippet": automation.shell_snippet,
        "ready_adapters": [item["adapter"] for item in status_payloads if item["ok"]],
        "status": status_payloads,
    }
    if shell_install is not None:
        payload["shell_install"] = shell_install
    if memory_import is not None:
        payload["memory_import"] = memory_import.to_dict()
    if memory_policy is not None:
        payload["memory_policy"] = memory_policy.to_dict()
    return payload

def _format_init(payload: dict[str, object]) -> str:
    installed = [str(item) for item in payload.get("installed_adapters", [])]
    skipped = payload.get("skipped_adapters", [])
    ready = [str(item) for item in payload.get("ready_adapters", [])]
    statuses = [item for item in payload.get("status", []) if isinstance(item, dict)]
    next_lines: list[str]
    shell_install = payload.get("shell_install") or {}
    if isinstance(shell_install, dict):
        shell_install_status = str(shell_install.get("status") or "")
    else:
        shell_install_status = ""
    if ready:
        next_lines = [f"- run {_agent_command_name(ready[0])} ..."]
    elif payload.get("shell_snippet"):
        next_lines = []
        if shell_install_status in {"installed", "already_installed"}:
            next_lines.append(
                "- exec $SHELL  # picks up .ait/bin via the installed shell hook"
            )
        else:
            detected_shell = detect_user_shell()
            direnv_pending = any(
                item.get("direnv_available") and not item.get("direnv_loaded")
                for item in statuses
            )
            if detected_shell is not None:
                next_lines.append(
                    f"- ait shell install --shell {detected_shell}  # one-time, persists across shells"
                )
                next_lines.append(
                    '  # alternative: eval "$(ait init --shell)"  (this shell only)'
                )
            else:
                next_lines.append('- eval "$(ait init --shell)"')
            if direnv_pending:
                next_lines.append("  # alternative: direnv allow  (if you use direnv)")
        next_lines.extend(f"- then run {_agent_command_name(name)} ..." for name in installed)
    else:
        next_lines = ["- install claude, codex, aider, gemini, or cursor, then run ait init"]
    lines = [
        "AIT initialized",
    ]
    if installed:
        lines.append("Agent wrappers: " + ", ".join(_agent_command_name(name) for name in installed))
    else:
        lines.append("Agent wrappers: none")
    lines.append("Next:")
    lines.extend(next_lines)
    lines.append("Details:")
    if payload.get("git_initialized"):
        lines.append("Git: initialized")
    if payload.get("baseline_commit_created"):
        lines.append("Git baseline: created initial commit")
    lines.append(f"Repo: {payload['repo_root']}")
    lines.append(f"State: {payload['ait_dir']}")
    if isinstance(shell_install, dict):
        if shell_install_status == "installed":
            rc_path = shell_install.get("rc_path", "")
            shell_name = shell_install.get("shell", "")
            lines.append(
                f"Shell hook: installed for {shell_name} in {rc_path}"
                " (run `ait shell uninstall` to remove)"
            )
        elif shell_install_status == "already_installed":
            shell_name = shell_install.get("shell", "")
            lines.append(f"Shell hook: already installed for {shell_name}")
        elif shell_install_status == "skipped":
            reason = shell_install.get("reason", "")
            lines.append(f"Shell hook: skipped ({reason})")
    if skipped:
        lines.append("Skipped:")
        for item in skipped:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}: {item.get('detail')}")
    memory_import = payload.get("memory_import")
    if isinstance(memory_import, dict):
        imported = memory_import.get("imported", [])
        memory_skipped = memory_import.get("skipped", [])
        if imported:
            lines.append("Imported memory:")
            for item in imported:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('source')}")
        elif memory_skipped:
            lines.append("Imported memory: none")
    memory_policy = payload.get("memory_policy")
    if isinstance(memory_policy, dict):
        state = "created" if memory_policy.get("created") else "already current"
        lines.append(f"Memory policy: {state}")
    if ready:
        lines.append("Ready now:")
        lines.extend(f"- {_agent_command_name(name)}" for name in ready)
    elif not payload.get("shell_snippet"):
        lines.append("Current shell: no supported agent CLI found on PATH")
    return "\n".join(lines)

def _repair_payload(
    before,
    result,
    after,
    memory_import=None,
    memory_lint=None,
    memory_health_lint=None,
) -> dict[str, object]:
    before_payload = [_status_payload(item) for item in before]
    after_payload = [_status_payload(item) for item in after]
    before_by_adapter = {str(item["adapter"]): item for item in before_payload}
    changes: list[dict[str, object]] = []
    for item in after_payload:
        adapter = str(item["adapter"])
        previous = before_by_adapter.get(adapter, {})
        changed_fields = {
            key: {"before": previous.get(key), "after": item.get(key)}
            for key in (
                "ok",
                "wrapper_installed",
                "path_wrapper_active",
                "real_agent_binary",
                "direnv_loaded",
            )
            if previous.get(key) != item.get(key)
        }
        changes.append({"adapter": adapter, "changed": changed_fields})
    payload = {
        "before": before_payload,
        "after": after_payload,
        "installed_adapters": [item.adapter.name for item in result.installed],
        "skipped_adapters": [asdict(item) for item in result.skipped],
        "shell_snippet": result.shell_snippet,
        "changes": changes,
    }
    if memory_import is not None:
        payload["memory_import"] = memory_import.to_dict()
    if memory_lint is not None:
        payload["memory_lint"] = memory_lint.to_dict()
        payload["memory_health"] = memory_health_from_lint(memory_health_lint or memory_lint).to_dict()
    return payload

def _format_repair(payload: dict[str, object]) -> str:
    lines = ["AIT repair"]
    installed = [str(item) for item in payload.get("installed_adapters", [])]
    if installed:
        lines.append("Repaired:")
        lines.extend(f"- {name}" for name in installed)
    else:
        lines.append("Repaired: none")
    skipped = payload.get("skipped_adapters", [])
    if skipped:
        lines.append("Skipped:")
        for item in skipped:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')}: {item.get('detail')}")
    memory_import = payload.get("memory_import")
    if isinstance(memory_import, dict):
        imported = memory_import.get("imported", [])
        if imported:
            lines.append("Imported memory:")
            for item in imported:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('source')}")
        else:
            lines.append("Imported memory: already current")
    memory_lint = payload.get("memory_lint")
    memory_health = payload.get("memory_health")
    if isinstance(memory_lint, dict):
        health_status = memory_health.get("status") if isinstance(memory_health, dict) else "unknown"
        lines.append(f"Memory health: {health_status}")
        lines.append(
            "Memory lint: "
            f"issues={memory_lint.get('issue_count', 0)} fixes={memory_lint.get('fix_count', 0)}"
        )
        fixes = memory_lint.get("fixes", [])
        if fixes:
            lines.append("Memory lint fixes:")
            for item in fixes:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('action')} note={item.get('note_id')}: {item.get('detail')}")
    changes = payload.get("changes", [])
    if changes:
        lines.append("Status changes:")
        for item in changes:
            if not isinstance(item, dict):
                continue
            changed = item.get("changed", {})
            if not changed:
                lines.append(f"- {item.get('adapter')}: no status change")
                continue
            parts = []
            if isinstance(changed, dict):
                for key, values in changed.items():
                    if isinstance(values, dict):
                        parts.append(f"{key}: {values.get('before')} -> {values.get('after')}")
            lines.append(f"- {item.get('adapter')}: " + ", ".join(parts))
    if payload.get("shell_snippet"):
        lines.extend(
            [
                "Current shell:",
                '- eval "$(ait init --shell)"',
            ]
        )
    return "\n".join(lines)
