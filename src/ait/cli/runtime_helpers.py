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
from ait.memory_eval import evaluate_memory_retrievals, render_memory_eval_report
from ait.memory_policy import load_memory_policy
from ait.query import QueryError, execute_query, list_shortcut_expression, parse_blame_target
from ait.repo import resolve_repo_root
from ait.shell_integration import shell_snippet
from ait.cli_installation import (
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_payload,
)


def _format_run_result(result) -> str:
    attempt = result.attempt.attempt
    outcome = result.attempt.outcome or {}
    return "\n".join(
        [
            "AIT run",
            f"Intent: {result.intent_id}",
            f"Attempt: {result.attempt_id}",
            f"Workspace: {result.workspace_ref}",
            f"Exit code: {result.exit_code}",
            f"Status: {attempt.get('verified_status')}",
            f"Outcome: {outcome.get('outcome_class', 'unclassified')}",
        ]
    )

def _format_shell_integration(action: str, result) -> str:
    state = "changed" if result.changed else "already current"
    lines = [
        f"Shell: {result.shell}",
        f"RC file: {result.rc_path}",
        f"Action: {action}",
        f"State: {state}",
    ]
    if action == "installed":
        lines.extend(
            [
                "Next:",
                f"- reload {result.rc_path} or open a new terminal",
                "- run ait doctor --fix once in each repo that should get wrappers",
            ]
        )
    return "\n".join(lines)

def _daemon_status_payload(repo_root: Path) -> dict[str, object]:
    state_dir = repo_root / ".ait"
    if not state_dir.exists():
        return {
            "available": False,
            "reason": "ait not initialized",
            "running": False,
            "pid": None,
            "pid_running": False,
            "pid_matches": False,
            "socket_connectable": False,
            "stale_reason": None,
        }
    try:
        status = daemon_status(repo_root)
    except ValueError as exc:
        return {
            "available": False,
            "reason": str(exc),
            "running": False,
            "pid": None,
            "pid_running": False,
            "pid_matches": False,
            "socket_connectable": False,
            "stale_reason": None,
        }
    return {
        "available": True,
        "running": status.running,
        "pid": status.pid,
        "pid_running": status.pid_running,
        "pid_matches": status.pid_matches,
        "socket_connectable": status.socket_connectable,
        "stale_reason": status.stale_reason,
        "socket_path": str(status.socket_path),
        "pid_file": str(status.pid_file),
    }

def _format_daemon_lines(daemon: dict[str, object]) -> list[str]:
    if daemon.get("available", True):
        lines = [
            "Daemon: "
            f"{'running' if daemon.get('running') else 'stopped'} "
            f"(socket_connectable={daemon.get('socket_connectable', False)}, "
            f"pid_matches={daemon.get('pid_matches', False)})"
        ]
        if daemon.get("pid") is not None:
            lines.append(f"Daemon pid: {daemon.get('pid')}")
        if daemon.get("stale_reason"):
            lines.append(f"Daemon stale reason: {daemon.get('stale_reason')}")
        if daemon.get("socket_path"):
            lines.append(f"Daemon socket: {daemon.get('socket_path')}")
        return lines
    return [f"Daemon: unavailable ({daemon.get('reason', 'not initialized')})"]
