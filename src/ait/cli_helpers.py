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


def _run_query_command(
    repo_root: Path,
    *,
    subject: str,
    expression: str | None,
    limit: int,
    offset: int,
    output_format: str,
) -> int:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        try:
            rows = execute_query(
                conn,
                subject,
                expression,
                limit=limit,
                offset=offset,
            )
        except QueryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    finally:
        conn.close()
    print(_format_rows([dict(row) for row in rows], output_format))
    return 0

def _format_rows(rows: list[dict[str, object]], output_format: str) -> str:
    if output_format == "jsonl":
        return "\n".join(json.dumps(row, sort_keys=True) for row in rows)
    if not rows:
        return ""
    columns = list(rows[0].keys())
    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = max(widths[column], len(str(row.get(column, ""))))
    header = " ".join(column.ljust(widths[column]) for column in columns)
    body = [
        " ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        for row in rows
    ]
    return "\n".join([header, *body])

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

def _format_memory_import(result) -> str:
    lines = ["AIT memory import"]
    if result.imported:
        lines.append("Imported:")
        for note in result.imported:
            lines.append(f"- {note.id} topic={note.topic or 'general'} source={note.source}")
    else:
        lines.append("Imported: none")
    if result.skipped:
        lines.append("Skipped:")
        for item in result.skipped:
            lines.append(f"- {item.get('path')}: {item.get('reason')} ({item.get('source')})")
    return "\n".join(lines)

def _format_memory_facts(facts) -> str:
    lines = ["AIT Memory Facts"]
    if not facts:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for fact in facts:
        lines.append(
            f"- {fact.id} kind={fact.kind} topic={fact.topic} "
            f"status={fact.status} confidence={fact.confidence}"
        )
        source_bits = [
            value
            for value in (
                f"attempt={fact.source_attempt_id}" if fact.source_attempt_id else "",
                f"commit={fact.source_commit_oid}" if fact.source_commit_oid else "",
                f"file={fact.source_file_path}" if fact.source_file_path else "",
            )
            if value
        ]
        if source_bits:
            lines.append("  source: " + " ".join(source_bits))
        lines.append(f"  {fact.summary}")
    return "\n".join(lines) + "\n"

def _format_memory_retrievals(events, facts_by_id) -> str:
    lines = ["AIT Memory Retrievals"]
    if not events:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for event in events:
        short_attempt = event.attempt_id.rsplit(":", 1)[-1][:8]
        lines.append(
            f"- {event.id} attempt={short_attempt} "
            f"facts={len(event.selected_fact_ids)} ranker={event.ranker_version} "
            f"budget={event.budget_chars} created={event.created_at}"
        )
        if event.query:
            lines.append(f"  query: {event.query}")
        if event.selected_fact_ids:
            lines.append("  selected facts:")
            for fact_id in event.selected_fact_ids[:8]:
                fact = facts_by_id.get(fact_id)
                if fact is None:
                    lines.append(f"  - {fact_id} missing")
                else:
                    lines.append(
                        f"  - {fact.id} {fact.kind}/{fact.topic} "
                        f"status={fact.status} confidence={fact.confidence}"
                    )
                    lines.append(f"    {fact.summary}")
            if len(event.selected_fact_ids) > 8:
                lines.append(f"  - ... {len(event.selected_fact_ids) - 8} more")
    return "\n".join(lines) + "\n"

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

def _init_payload(init_result, automation, statuses, memory_import=None, memory_policy=None) -> dict[str, object]:
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
    if ready:
        next_lines = [f"- run {_agent_command_name(ready[0])} ..."]
    elif payload.get("shell_snippet"):
        if any(item.get("direnv_available") and not item.get("direnv_loaded") for item in statuses):
            next_lines = ["- direnv allow"]
        else:
            next_lines = ['- eval "$(ait init --shell)"']
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

def _memory_status_payload(repo_root: Path) -> dict[str, object]:
    try:
        status = agent_memory_status(repo_root).to_dict()
        report_status = _report_status_payload(repo_root)
        state_db_path = repo_root / ".ait" / "state.sqlite3"
        if state_db_path.exists():
            lint_result = lint_memory_notes(repo_root)
            health = memory_health_from_lint(lint_result)
            eval_report = evaluate_memory_retrievals(repo_root)
            eval_next_steps = _memory_eval_next_steps(eval_report.status)
            status.update(
                {
                    "health": health.status,
                    "lint_checked": health.checked,
                    "lint_issue_count": health.issue_count,
                    "lint_error_count": health.error_count,
                    "lint_warning_count": health.warning_count,
                    "lint_info_count": health.info_count,
                    "eval_status": eval_report.status,
                    "eval_event_count": eval_report.event_count,
                    "eval_average_score": eval_report.average_score,
                    "eval_next_steps": eval_next_steps,
                    "report": report_status,
                }
            )
        else:
            health = "ok" if status.get("initialized") else "uninitialized"
            eval_next_steps = _memory_eval_next_steps("pass")
            status.update(
                {
                    "health": health,
                    "lint_checked": 0,
                    "lint_issue_count": 0,
                    "lint_error_count": 0,
                    "lint_warning_count": 0,
                    "lint_info_count": 0,
                    "eval_status": "pass",
                    "eval_event_count": 0,
                    "eval_average_score": 100,
                    "eval_next_steps": eval_next_steps,
                    "report": report_status,
                }
            )
        return status
    except ValueError:
        return {
            "initialized": False,
            "imported_sources": [],
            "candidate_paths": [],
            "pending_paths": [],
            "state_path": "",
            "health": "unavailable",
            "lint_checked": 0,
            "lint_issue_count": 0,
            "lint_error_count": 0,
            "lint_warning_count": 0,
            "lint_info_count": 0,
            "eval_status": "unavailable",
            "eval_event_count": 0,
            "eval_average_score": 0,
            "eval_next_steps": [],
            "report": {},
        }

def _memory_eval_next_steps(status: str) -> list[str]:
    return ["ait memory eval", "ait graph --html"] if status in {"warn", "fail"} else []

def _report_status_payload(repo_root: Path) -> dict[str, object]:
    status_path = repo_root / ".ait" / "report" / "status.json"
    if not status_path.exists():
        return {}
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status_path": str(status_path)}
    if isinstance(payload, dict):
        payload.setdefault("status_path", str(status_path))
        return payload
    return {"status_path": str(status_path)}


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

def _agent_command_name(adapter: str) -> str:
    return "claude" if adapter == "claude-code" else adapter

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
