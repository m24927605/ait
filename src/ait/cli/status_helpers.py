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

from ait.cli.adapter_helpers import _agent_cli_message, _agent_cli_summary, _agent_command_name, _doctor_next_steps
from ait.cli.runtime_helpers import _format_daemon_lines
from ait.cli_installation import (
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_payload,
)


def _status_payload(
    result,
    *,
    memory_status: dict[str, object] | None = None,
    installation: dict[str, object] | None = None,
    daemon: dict[str, object] | None = None,
) -> dict[str, object]:
    checks = {check.name: check.ok for check in result.checks}
    payload = {
        "adapter": result.adapter.name,
        "ok": result.ok,
        "git_repo": checks.get("git_repo", False),
        "wrapper_installed": checks.get("wrapper_file", False),
        "path_wrapper_active": checks.get("path_wrapper_active", False),
        "real_claude_binary": checks.get("real_claude_binary", False),
        "real_agent_binary": checks.get("real_agent_binary", checks.get("real_claude_binary", False)),
        "direnv_available": checks.get("direnv_binary", False),
        "direnv_loaded": checks.get("direnv_env_loaded", False),
        "memory": memory_status or {},
        "ait_health": _ait_health_payload(memory_status or {}),
        "daemon": daemon or {},
        "next_steps": _doctor_next_steps(result),
    }
    if installation is not None:
        payload["installation"] = installation
    payload["agent_cli_ready"] = payload["ok"]
    payload["agent_cli_message"] = _agent_cli_message(payload)
    return payload

def _format_status(payload: dict[str, object]) -> str:
    binary_label = "Real Claude binary" if payload["adapter"] == "claude-code" else "Real agent binary"
    installation = payload.get("installation")
    lines = []
    if isinstance(installation, dict):
        lines.extend(_format_installation_alert_lines(installation))
    lines.extend([
        f"Agent CLI: {_agent_cli_summary(payload)}",
        f"Adapter: {payload['adapter']}",
        f"OK: {payload['ok']}",
        f"Git repo: {payload['git_repo']}",
        f"Wrapper installed: {payload['wrapper_installed']}",
        f"PATH uses wrapper: {payload['path_wrapper_active']}",
        f"{binary_label}: {payload['real_agent_binary']}",
        f"direnv available: {payload['direnv_available']}",
        f"direnv loaded: {payload['direnv_loaded']}",
        f"Agent CLI ready: {payload['agent_cli_ready']}",
        f"Agent CLI detail: {payload['agent_cli_message']}",
    ])
    if isinstance(installation, dict):
        lines.extend(_format_installation_lines(installation, include_next_steps=False))
    daemon = payload.get("daemon", {})
    if isinstance(daemon, dict) and daemon:
        lines.extend(_format_daemon_lines(daemon))
    ait_health = payload.get("ait_health", {})
    if isinstance(ait_health, dict):
        lines.append(f"AIT health: {ait_health.get('status', 'unknown')}")
        reasons = ait_health.get("reasons", [])
        if reasons:
            lines.append("Health reasons:")
            lines.extend(f"- {reason}" for reason in reasons)
        health_next = ait_health.get("next_steps", [])
        if health_next:
            lines.append("Health next:")
            lines.extend(f"- {step}" for step in health_next)
    memory = payload.get("memory", {})
    if isinstance(memory, dict):
        imported = memory.get("imported_sources", [])
        pending = memory.get("pending_paths", [])
        lines.append(f"Memory initialized: {memory.get('initialized', False)}")
        lines.append(f"Memory health: {memory.get('health', 'unknown')}")
        lines.append(
            "Memory lint issues: "
            f"{memory.get('lint_issue_count', 0)} "
            f"(errors={memory.get('lint_error_count', 0)}, "
            f"warnings={memory.get('lint_warning_count', 0)}, "
            f"info={memory.get('lint_info_count', 0)})"
        )
        lines.append(f"Memory imported sources: {len(imported) if isinstance(imported, list) else 0}")
        lines.append(
            "Memory eval: "
            f"{memory.get('eval_status', 'unknown')} "
            f"(events={memory.get('eval_event_count', 0)}, "
            f"average_score={memory.get('eval_average_score', 0)})"
        )
        eval_next_steps = memory.get("eval_next_steps", [])
        if eval_next_steps:
            lines.append("Memory eval next:")
            lines.extend(f"- {step}" for step in eval_next_steps)
        report = memory.get("report", {})
        if isinstance(report, dict) and report.get("status_path"):
            lines.append(f"Last report: {report.get('status_path')}")
            if report.get("graph_html_path"):
                lines.append(f"Graph report: {report.get('graph_html_path')}")
        if pending:
            lines.append("Memory pending:")
            lines.extend(f"- {path}" for path in pending)
    next_steps = payload.get("next_steps", [])
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(lines)

def _ait_health_payload(memory_status: dict[str, object]) -> dict[str, object]:
    report = memory_status.get("report", {})
    if isinstance(report, dict):
        health = report.get("health", {})
        if isinstance(health, dict) and health.get("status"):
            return {
                "status": str(health.get("status", "unknown")),
                "reasons": [str(item) for item in health.get("reasons", []) if str(item)],
                "next_steps": [str(item) for item in health.get("next_steps", []) if str(item)],
            }
    eval_status = str(memory_status.get("eval_status", "unknown"))
    next_steps = memory_status.get("eval_next_steps", [])
    if eval_status == "fail":
        return {
            "status": "fail",
            "reasons": ["memory eval failed"],
            "next_steps": [str(item) for item in next_steps],
        }
    if eval_status == "warn":
        return {
            "status": "warn",
            "reasons": ["memory eval warning"],
            "next_steps": [str(item) for item in next_steps],
        }
    return {"status": "pass" if eval_status == "pass" else "unknown", "reasons": [], "next_steps": []}

def _format_status_all(payload: list[dict[str, object]]) -> str:
    lines = []
    if payload:
        installation = payload[0].get("installation")
        if isinstance(installation, dict):
            lines.extend(_format_installation_alert_lines(installation))
    lines.append("AIT Agent CLI Readiness")
    if payload:
        installation = payload[0].get("installation")
        if isinstance(installation, dict):
            lines.extend(_format_installation_lines(installation, include_next_steps=False))
    for item in payload:
        command = _agent_command_name(str(item["adapter"]))
        daemon = item.get("daemon", {})
        daemon_label = "running" if isinstance(daemon, dict) and daemon.get("running") else "stopped"
        lines.append(
            f"- {command}: {_agent_cli_summary(item)}"
        )
        lines.append(
            "  details: "
            f"adapter={item['adapter']} "
            f"wrapper={item['wrapper_installed']} "
            f"path={item['path_wrapper_active']} "
            f"real_binary={item['real_agent_binary']} "
            f"memory={item.get('memory', {}).get('initialized', False) if isinstance(item.get('memory'), dict) else False} "
            f"memory_health={item.get('memory', {}).get('health', 'unknown') if isinstance(item.get('memory'), dict) else 'unknown'} "
            f"memory_eval={item.get('memory', {}).get('eval_status', 'unknown') if isinstance(item.get('memory'), dict) else 'unknown'} "
            f"daemon={daemon_label}"
        )
        memory = item.get("memory", {})
        eval_next_steps = memory.get("eval_next_steps", []) if isinstance(memory, dict) else []
        if eval_next_steps:
            lines.append(f"  memory next: {', '.join(str(step) for step in eval_next_steps)}")
        next_steps = item.get("next_steps", [])
        if next_steps:
            lines.append(f"  next: {', '.join(str(step) for step in next_steps)}")
    return "\n".join(lines)
