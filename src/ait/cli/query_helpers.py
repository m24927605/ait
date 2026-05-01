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
