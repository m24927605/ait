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

from ait.cli.adapter_helpers import _doctor_next_steps
from ait.cli.status_helpers import _status_payload
from ait.cli_installation import (
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_payload,
)


def _maybe_emit_automation_hint(args, repo_root: Path, result) -> None:
    if args.no_hints or result.ok:
        return
    hint_key = (
        "claude_code_automation_hint_v1"
        if result.adapter.name == "claude-code"
        else f"{result.adapter.name}_automation_hint_v1"
    )
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        return
    hints_path = root / ".ait" / "hints.json"
    hints = _read_hints(hints_path)
    if hints.get(hint_key):
        return
    next_steps = _doctor_next_steps(result)
    install_step = next((step for step in next_steps if step.startswith("install ")), None)
    if install_step is not None:
        hint = f"ait hint: {install_step}."
    else:
        hint = "ait hint: run ait init once to enable detected agent automation in this repo."
    print(hint, file=sys.stderr)
    hints[hint_key] = True
    _write_hints(hints_path, hints)

def _maybe_emit_status_all_hint(args, repo_root: Path, results) -> None:
    results = tuple(results)
    if args.no_hints or all(result.ok for result in results):
        return
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        return
    hints_path = root / ".ait" / "hints.json"
    hints = _read_hints(hints_path)
    hint_key = "all_agent_automation_hint_v1"
    if hints.get(hint_key):
        return
    missing_real = [
        result.adapter.command_name
        for result in results
        if result.adapter.command_name
        and not _status_payload(result)["real_agent_binary"]
    ]
    if missing_real and len(missing_real) == len(results):
        hint = "ait hint: install an agent CLI such as claude, codex, aider, gemini, or cursor first."
    else:
        hint = "ait hint: run ait init once to enable detected agent automation in this repo."
    print(hint, file=sys.stderr)
    hints[hint_key] = True
    _write_hints(hints_path, hints)

def _read_hints(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data

def _write_hints(path: Path, hints: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hints, indent=2, sort_keys=True) + "\n", encoding="utf-8")
