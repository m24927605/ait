from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from ait.adapters import (
    ADAPTERS,
    AdapterError,
    bootstrap_adapter,
    bootstrap_shell_snippet,
    doctor_adapter,
    doctor_automation,
    enable_available_adapters,
    get_adapter,
    list_adapters,
    setup_adapter,
)
from ait.brain import (
    build_auto_briefing_query,
    build_auto_repo_brain_briefing,
    build_repo_brain_briefing,
    build_repo_brain,
    query_repo_brain,
    render_repo_brain_briefing,
    render_brain_query_results,
    render_repo_brain_text,
    write_repo_brain,
)
from ait.context import build_agent_context, render_agent_context_text
from ait.app import (
    abandon_intent,
    create_commit_for_attempt,
    create_attempt,
    create_intent,
    discard_attempt,
    init_repo,
    promote_attempt,
    rebase_attempt,
    show_attempt,
    show_intent,
    supersede_intent,
    verify_attempt,
)
from ait.daemon import daemon_status, prune_daemon, serve_daemon, start_daemon, stop_daemon
from ait.db import (
    connect_db,
    get_memory_fact,
    list_memory_facts,
    list_memory_retrieval_events,
    run_migrations,
)
from ait.memory import (
    add_memory_note,
    agent_memory_status,
    build_relevant_memory_recall,
    build_repo_memory,
    ensure_agent_memory_imported,
    import_agent_memory,
    lint_memory_notes,
    list_memory_notes,
    memory_health_from_lint,
    remove_memory_note,
    render_repo_memory_text,
    render_relevant_memory_recall,
    render_memory_search_results,
    render_memory_lint_result,
    search_repo_memory,
)
from ait.memory.eval import evaluate_memory_retrievals, render_memory_eval_report
from ait.memory_policy import init_memory_policy, load_memory_policy
from ait.query import QueryError, blame_path, execute_query, list_shortcut_expression, parse_blame_target
from ait.reconcile import reconcile_repo
from ait.report import build_work_graph, render_work_graph_text, write_work_graph_html
from ait.repo import resolve_repo_root
from ait.runner import run_agent_command
from ait.shell_integration import (
    ShellIntegrationError,
    install_shell_integration,
    shell_snippet,
    uninstall_shell_integration,
)
from ait.workspace import WorkspaceError
from ait.cli_installation import (
    _classify_ait_source,
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_next_steps,
    _installation_payload as _default_installation_payload,
    package_version,
)
from ait.cli.adapter_helpers import (
    _agent_cli_message,
    _agent_cli_summary,
    _agent_command_name,
    _doctor_next_steps,
    _format_adapter,
    _format_adapter_doctor,
    _format_auto_enable,
    _format_bootstrap,
)
from ait.cli.hint_helpers import (
    _maybe_emit_automation_hint,
    _maybe_emit_status_all_hint,
    _read_hints,
    _write_hints,
)
from ait.cli.init_helpers import (
    _format_init,
    _format_repair,
    _init_payload,
    _maybe_auto_install_shell_hook,
    _repair_payload,
)
from ait.cli.memory_helpers import (
    _format_memory_facts,
    _format_memory_import,
    _format_memory_retrievals,
    _memory_eval_next_steps,
    _memory_status_payload,
    _report_status_payload,
)
from ait.cli.query_helpers import (
    _format_rows,
    _run_query_command,
)
from ait.cli.runtime_helpers import (
    _daemon_status_payload,
    _format_daemon_lines,
    _format_run_result,
    _format_shell_integration,
)
from ait.cli.status_helpers import (
    _ait_health_payload,
    _format_status,
    _format_status_all,
    _status_payload,
)

def _installation_payload() -> dict[str, object]:
    import ait.cli as cli_compat

    return cli_compat.__dict__.get("_installation_payload", _default_installation_payload)()

__all__ = [name for name in globals() if not name.startswith("__")]
