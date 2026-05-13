from __future__ import annotations

from dataclasses import asdict
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
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
        rows_as_dicts = [dict(row) for row in rows]
        if subject == "attempt" and output_format == "table":
            rendered = _format_attempt_rows(conn, rows_as_dicts)
        else:
            rendered = _format_rows(rows_as_dicts, output_format)
    finally:
        conn.close()
    print(rendered)
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


def _format_attempt_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, object]],
) -> str:
    if not rows:
        return "No attempts."

    attempt_ids = [str(row.get("id", "")) for row in rows]
    all_attempt_ids = [
        str(row["id"]) for row in conn.execute("SELECT id FROM attempts").fetchall()
    ]
    intent_titles = _intent_titles(conn, rows)
    changed_counts = _changed_file_counts(conn, attempt_ids)

    compact_rows: list[dict[str, object]] = []
    for row in rows:
        attempt_id = str(row.get("id", ""))
        intent_id = str(row.get("intent_id", ""))
        compact_rows.append(
            {
                "attempt": _short_object_id(attempt_id, all_attempt_ids),
                "status": _attempt_status(row),
                "agent": _attempt_agent(row),
                "exit": row.get("result_exit_code")
                if row.get("result_exit_code") is not None
                else "-",
                "files": changed_counts.get(attempt_id, 0),
                "started": _short_timestamp(row.get("started_at")),
                "intent": _clip(intent_titles.get(intent_id, intent_id), 48),
            }
        )
    return _format_rows(compact_rows, "table")


def _intent_titles(
    conn: sqlite3.Connection,
    rows: list[dict[str, object]],
) -> dict[str, str]:
    intent_ids = sorted({str(row.get("intent_id", "")) for row in rows if row.get("intent_id")})
    if not intent_ids:
        return {}
    placeholders = ",".join("?" for _ in intent_ids)
    return {
        str(row["id"]): str(row["title"])
        for row in conn.execute(
            f"SELECT id, title FROM intents WHERE id IN ({placeholders})",
            tuple(intent_ids),
        ).fetchall()
    }


def _changed_file_counts(
    conn: sqlite3.Connection,
    attempt_ids: list[str],
) -> dict[str, int]:
    if not attempt_ids:
        return {}
    placeholders = ",".join("?" for _ in attempt_ids)
    return {
        str(row["attempt_id"]): int(row["count"])
        for row in conn.execute(
            f"""
            SELECT attempt_id, COUNT(*) AS count
            FROM evidence_files
            WHERE kind = 'changed' AND attempt_id IN ({placeholders})
            GROUP BY attempt_id
            """,
            tuple(attempt_ids),
        ).fetchall()
    }


def _short_object_id(value: str, all_values: list[str], *, min_chars: int = 8) -> str:
    tail = value.rsplit(":", 1)[-1] or value
    if len(tail) <= 12:
        return tail
    for width in range(min(min_chars, len(tail)), len(tail) + 1):
        candidate = tail[-width:]
        if sum(1 for item in all_values if candidate in item) == 1:
            return candidate
    return tail


def _attempt_status(row: dict[str, object]) -> str:
    reported = str(row.get("reported_status") or "")
    verified = str(row.get("verified_status") or "")
    if reported in {"created", "running", "interrupted"}:
        return reported
    if verified and verified != "pending":
        return verified
    return reported or verified or "-"


def _attempt_agent(row: dict[str, object]) -> str:
    harness = str(row.get("agent_harness") or "")
    if harness:
        return harness
    agent_id = str(row.get("agent_id") or "")
    return agent_id.split(":", 1)[0] if agent_id else "-"


def _short_timestamp(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    if len(text) >= 16 and text[4] == "-" and text[7] == "-" and text[10] == "T":
        return f"{text[5:10]} {text[11:16]}"
    return _clip(text, 16)


def _clip(value: object, max_chars: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
