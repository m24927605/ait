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
