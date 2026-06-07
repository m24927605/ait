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
    get_attempt,
    get_memory_fact,
    list_attempt_commits,
    list_attempts,
    list_memory_facts,
    list_memory_retrieval_events,
    refresh_attempt_identity,
    run_migrations,
)
from ait.decision_codes import StatusCode
from ait.decision_report import daily_step, decision_payload, decision_report
from ait.dev_server import dev_servers_for_worktree
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
from ait.review import latest_review_summary
from ait.shell_integration import shell_snippet
from ait.workspace import get_workspaces_root
from ait.workspace_lease import lease_payload, workspace_lease_path
from ait.cleanup import (
    DEFAULT_FAILED_RETENTION_DAYS,
    classify_terminal,
    cleanup_policy_from_config,
    path_is_inside,
    safe_resolve_workspace_ref,
)

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
    check_details = {check.name: check.detail for check in result.checks}
    payload = {
        "adapter": result.adapter.name,
        "ok": result.ok,
        "git_repo": checks.get("git_repo", False),
        "wrapper_installed": checks.get("wrapper_file", False),
        "path_wrapper_active": checks.get("path_wrapper_active", False),
        "wrapper_path": check_details.get("wrapper_file"),
        "active_binary": _active_binary_detail(
            check_details.get("path_wrapper_active"),
            result.adapter.command_name,
        ),
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
    payload["bypass_detection"] = _bypass_detection_payload(payload, result)
    payload["wrap_behavior"] = _wrap_behavior_payload(payload)
    return payload


def _wrap_behavior_payload(payload: dict[str, object]) -> dict[str, str]:
    adapter_name = str(payload.get("adapter", "claude-code"))
    command = _agent_command_name(adapter_name)
    if payload.get("path_wrapper_active"):
        current = f"wrapped ({command} in this shell enters AIT)"
    elif payload.get("wrapper_installed"):
        current = f"unwrapped ({command} not on PATH ahead of .ait/bin)"
    else:
        current = "not configured"
    return {
        "current": current,
        "disable_once": f"AIT_BYPASS=1 {command} ...",
        "disable_shell": "ait off    (re-enable: ait on)",
    }

def _active_binary_detail(detail: str | None, command_name: str) -> str | None:
    if not detail or detail == f"{command_name} not found on PATH":
        return None
    return str(Path(detail).resolve())

def _bypass_detection_payload(payload: dict[str, object], result) -> dict[str, object]:
    adapter = str(payload["adapter"])
    command = _agent_command_name(adapter)
    wrapper_path = str(payload.get("wrapper_path") or "")
    wrapper_dir = str(Path(wrapper_path).parent) if wrapper_path else None
    active_binary = payload.get("active_binary")
    next_steps = [str(item) for item in payload.get("next_steps", []) if str(item)]
    base = {
        "adapter": adapter,
        "command": command,
        "will_use_ait": False,
        "status": "unknown",
        "message": "",
        "wrapper_path": wrapper_path or None,
        "wrapper_dir": wrapper_dir,
        "active_binary": active_binary,
        "next_steps": next_steps,
    }
    if adapter == "shell":
        return {
            **base,
            "status": "unavailable",
            "message": "shell adapter has no fixed agent command to guard",
        }
    if not payload.get("git_repo"):
        return {
            **base,
            "status": "not_initialized",
            "message": "AIT cannot detect wrapper bypass outside a Git repository",
        }
    if not payload.get("wrapper_installed"):
        return {
            **base,
            "status": "not_configured",
            "message": f"{command} is not routed through AIT yet; install the repo-local wrapper",
        }
    if payload.get("path_wrapper_active"):
        return {
            **base,
            "will_use_ait": True,
            "status": "wrapped",
            "message": f"running `{command}` in this shell will enter AIT",
        }
    if active_binary:
        return {
            **base,
            "status": "bypass_risk",
            "message": (
                f"running `{command}` in this shell will bypass AIT and call "
                f"{active_binary}; put {wrapper_dir or '.ait/bin'} first on PATH"
            ),
        }
    return {
        **base,
        "status": "wrapper_not_on_path",
        "message": (
            f"{command} is not on PATH in this shell; put {wrapper_dir or '.ait/bin'} "
            "first on PATH before running the agent"
        ),
    }

def _status_payload_with_recovery(payload: dict[str, object], repo_root: str | Path) -> dict[str, object]:
    updated = dict(payload)
    updated["recovery"] = _recovery_dashboard_payload(repo_root)
    return updated


def _recovery_dashboard_payload(repo_root: str | Path) -> dict[str, object]:
    # When invoked from inside an attempt worktree (e.g. cwd is
    # `<host>/.ait/workspaces/attempt-<n>-<ulid>/...`), the literal
    # path has no `.ait/state.sqlite3`, which used to surface as a
    # confusing "not_initialized" — even though the host repo IS
    # initialized. resolve_repo_root walks via `git --git-common-dir`
    # and returns the host root. Fall back to the literal path when
    # we are not in any git repo so the genuine not-initialized case
    # still reports correctly.
    try:
        root = resolve_repo_root(repo_root)
    except ValueError:
        root = Path(repo_root).resolve()
    db_path = root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return {
            "status": "not_initialized",
            "message": "AIT has no recorded attempts in this repo.",
            "cleanup_hint": _empty_cleanup_hint(),
            "decision_report": decision_payload(
                decision_report(
                    subject="status",
                    subject_id=None,
                    decision="not_initialized",
                    safety_level="informational",
                    reason_code=StatusCode.NOT_INITIALIZED,
                    reason_message="AIT has no recorded attempts in this repo.",
                )
            ),
        }
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        attempts = list_attempts(conn)
        if not attempts:
            return {
                "status": "empty",
                "message": "AIT has no recorded attempts in this repo.",
                "cleanup_hint": _empty_cleanup_hint(),
                "decision_report": decision_payload(
                    decision_report(
                        subject="status",
                        subject_id=None,
                        decision="empty",
                        safety_level="informational",
                        reason_code=StatusCode.NO_ATTEMPTS,
                        reason_message="AIT has no recorded attempts in this repo.",
                    )
                ),
            }
        attempt = attempts[-1]
        commits = list_attempt_commits(conn, attempt.id)
        identity = refresh_attempt_identity(conn, attempt.id)
        review = latest_review_summary(conn, attempt.id)
    finally:
        conn.close()
    changed_files = tuple(sorted({path for commit in commits for path in commit.touched_files}))
    cleanup_hint = _compute_cleanup_hint(attempts, root)
    workspace_exists, lease, dev_servers, lease_path_str = _safe_workspace_fields(
        root, attempt.workspace_ref
    )
    status, code, message, next_command = _classify_recovery_attempt(attempt, workspace_exists, lease)
    integration = _integration_artifact_payload(root, attempt.id)
    if integration:
        status = str(integration.get("decision_report", {}).get("decision") or status) if isinstance(integration.get("decision_report"), dict) else status
        code = str(
            (integration.get("decision_report", {}).get("reasons") or [{}])[0].get("code")
            if isinstance(integration.get("decision_report"), dict)
            else code
        )
        message = "Latest AIT result is an integration attempt."
    report = decision_report(
        subject="status",
        subject_id=attempt.id,
        decision=status,
        safety_level="informational" if status in {"idle", "applied"} else "recoverable",
        reason_code=code,
        reason_message=message,
        paths=changed_files,
        debug={
            "attempt_id": attempt.id,
            "attempt_handle": identity.handle,
            "attempt_description": identity.deterministic_description,
            "workspace_ref": attempt.workspace_ref,
            "workspace_exists": workspace_exists,
            "lease_path": lease_path_str,
            "lease": lease or {},
            "dev_servers": dev_servers,
            "apply_readiness": status,
            "next_step": next_command,
        },
        next_steps=() if next_command is None else (daily_step(next_command, "continue the daily workflow"),),
        metadata={
            "attempt_id": attempt.id,
            "attempt_handle": identity.handle,
            "attempt_description": identity.deterministic_description,
            "reported_status": attempt.reported_status,
            "verified_status": attempt.verified_status,
            "workspace_exists": workspace_exists,
            "changed_files_count": len(changed_files),
            "integration": integration or {},
            "review": review,
        },
    )
    return {
        "status": status,
        "message": message,
        "cleanup_hint": cleanup_hint,
        "attempt_id": attempt.id,
        "attempt_handle": identity.handle,
        "attempt_description": identity.deterministic_description,
        "attempt_short_id": attempt.id.rsplit(":", 1)[-1],
        "reported_status": attempt.reported_status,
        "verified_status": attempt.verified_status,
        "changed_files": list(changed_files),
        "workspace_ref": attempt.workspace_ref,
        "workspace_exists": workspace_exists,
        "lease": lease,
        "lease_path": lease_path_str,
        "dev_servers": dev_servers,
        "integration": integration or {},
        "review": review,
        "next_step": next_command,
        "decision_report": decision_payload(report),
    }


_RECLAIM_PRECEDENCE = {"reclaimable": 3, "retained_succeeded": 2, "not_reclaimable": 1}

_REF_ERRORS = (OSError, ValueError, RuntimeError, TypeError)


def _safe_workspace_fields(root: Path, workspace_ref) -> tuple[bool, object, object, str]:
    """Read latest-attempt workspace fields without crashing on malformed refs.

    ``ait status`` is read-only and must never fail on a malformed/hostile
    ``workspace_ref`` (e.g. embedded null byte). Returns
    ``(exists, lease, dev_servers, lease_path_str)`` with safe fallbacks.
    """
    try:
        exists = Path(workspace_ref).exists()
    except _REF_ERRORS:
        exists = False
    try:
        lease = lease_payload(workspace_ref)
    except _REF_ERRORS:
        lease = None
    try:
        dev_servers = _dev_server_payload(root, workspace_ref)
    except _REF_ERRORS:
        dev_servers = []
    try:
        lease_path_str = str(workspace_lease_path(workspace_ref))
    except _REF_ERRORS:
        lease_path_str = ""
    return exists, lease, dev_servers, lease_path_str


def _cleanup_hint_lines(cleanup_hint: object) -> list[str]:
    """Text lines for the cleanup hint. Empty when nothing to surface.

    Only emits counts (never the raw ref), so no escaping of hostile DB
    values is needed here — anomaly detail lives in JSON.
    """
    if not isinstance(cleanup_hint, dict):
        return []
    lines: list[str] = []
    reclaimable = cleanup_hint.get("reclaimable_worktrees", 0)
    retained = cleanup_hint.get("retained_succeeded_worktrees", 0)
    anomalous = cleanup_hint.get("anomalous_refs", 0)
    if reclaimable:
        lines.append(
            f"清理：約 {reclaimable} 個 worktree 可回收，跑 ait cleanup 確認、--apply 回收"
        )
    if retained:
        lines.append(
            f"清理：{retained} 個 succeeded 保留中，apply 或 discard 後 ait cleanup 回收"
        )
    if anomalous:
        lines.append(
            f"清理：偵測到 {anomalous} 個異常 worktree 參照（corrupted/不安全），"
            "ait status --format json 看 cleanup_hint.anomalies 詳情"
        )
    if cleanup_hint.get("config_warning"):
        lines.append("清理：cleanup config 無效，ait cleanup 可能失敗，請修正 .ait/config.json")
    return lines


def _empty_cleanup_hint() -> dict[str, object]:
    return {
        "reclaimable_worktrees": 0,
        "retained_succeeded_worktrees": 0,
        "anomalous_refs": 0,
        "config_warning": False,
        "next_steps": [],
        "anomalies": [],
    }


def _cleanup_retention_days(repo_root: Path) -> tuple[int, bool]:
    """Return (retention_days, config_warning). Read-only: never raises."""
    try:
        policy = cleanup_policy_from_config(repo_root)
        return int(policy.older_than_days), False
    except Exception:
        return DEFAULT_FAILED_RETENTION_DAYS, True


def _classify_workspace_ref(workspace_ref, workspaces_root: Path) -> tuple[str, object]:
    """Classify a DB workspace_ref for status counting.

    Returns one of:
    - ("anomalous", reason)  — relative/unresolvable/outside-root/exists-error
    - ("missing", None)      — in-root but the worktree no longer exists
    - ("count", resolved)    — in-root and present; eligible for counting
    """
    try:
        candidate = Path(workspace_ref)
    except (TypeError, ValueError):
        return "anomalous", "resolve-error"
    if not candidate.is_absolute():
        return "anomalous", "relative-ref"
    resolved = safe_resolve_workspace_ref(workspace_ref)
    if resolved is None:
        return "anomalous", "resolve-error"
    if not path_is_inside(resolved, workspaces_root):
        return "anomalous", "outside-root"
    try:
        exists = resolved.exists()
    except OSError:
        return "anomalous", "exists-error"
    if not exists:
        return "missing", None
    return "count", resolved


def _cleanup_next_steps(reclaimable: int, retained: int, config_warning: bool) -> list[str]:
    steps: list[str] = []
    if reclaimable > 0:
        steps.append("ait cleanup  # 查看精確清單")
        steps.append("ait cleanup --apply  # 回收")
    if retained > 0:
        steps.append("ait attempt list --verified-status succeeded")
        steps.append("ait apply <attempt> 或 ait attempt discard <attempt>，再 ait cleanup --apply")
    if config_warning:
        steps.append("cleanup config 無效，ait cleanup 可能失敗，請修正 .ait/config.json")
    return steps


def _compute_cleanup_hint(attempts, root: Path) -> dict[str, object]:
    retention_days, config_warning = _cleanup_retention_days(root)
    workspaces_root = get_workspaces_root(root).resolve()
    by_path: dict[str, str] = {}  # resolved-path str -> best category (dedupe + precedence)
    anomalies: dict[str, dict[str, object]] = {}  # raw ref str -> anomaly record
    for attempt in attempts:
        kind, payload = _classify_workspace_ref(attempt.workspace_ref, workspaces_root)
        if kind == "anomalous":
            anomalies.setdefault(
                str(attempt.workspace_ref),
                {
                    "attempt_id": attempt.id,
                    "workspace_ref": str(attempt.workspace_ref),
                    "reason": payload,
                },
            )
        elif kind == "count":
            category = classify_terminal(attempt, retention_days=retention_days).category
            key = str(payload)
            if _RECLAIM_PRECEDENCE[category] > _RECLAIM_PRECEDENCE.get(by_path.get(key, ""), 0):
                by_path[key] = category
        # "missing" → skip (worktree gone, neither reclaimable nor anomalous)
    reclaimable = sum(1 for category in by_path.values() if category == "reclaimable")
    retained = sum(1 for category in by_path.values() if category == "retained_succeeded")
    return {
        "reclaimable_worktrees": reclaimable,
        "retained_succeeded_worktrees": retained,
        "anomalous_refs": len(anomalies),
        "config_warning": config_warning,
        "next_steps": _cleanup_next_steps(reclaimable, retained, config_warning),
        "anomalies": list(anomalies.values()),
    }


def _integration_artifact_payload(repo_root: Path, attempt_id: str) -> dict[str, object] | None:
    path = repo_root / ".ait" / "results" / f"{_safe_attempt_filename(attempt_id)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "integration":
        return None
    return payload


def _safe_attempt_filename(attempt_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in attempt_id.rsplit(":", 1)[-1])


def _classify_recovery_attempt(attempt, workspace_exists: bool, lease: dict[str, object] | None):
    if attempt.verified_status == "promoted":
        return "applied", StatusCode.LATEST_APPLIED, "Latest AIT result is already applied.", None
    if attempt.verified_status == "discarded":
        return "discarded", StatusCode.LATEST_DISCARDED, "Latest AIT result was discarded.", None
    if lease and lease.get("state") == "conflict":
        return "needs_recovery", StatusCode.CONFLICT, "Latest AIT result is held for recovery.", "ait recover latest"
    if lease and lease.get("state") == "active":
        return "running", StatusCode.ACTIVE, "AIT has an active attempt.", None
    if attempt.verified_status == "succeeded" and workspace_exists:
        return "ready_to_apply", StatusCode.READY_TO_APPLY, "Latest AIT result is ready to apply.", "ait apply latest"
    if attempt.verified_status == "failed" or attempt.reported_status == "crashed":
        return "needs_recovery", StatusCode.FAILED, "Latest AIT result failed and is recoverable if its state is still present.", "ait recover latest"
    if not workspace_exists:
        return "held", StatusCode.MISSING_RECOVERY_STATE, "Latest AIT result has no recoverable workspace.", "ait recover latest --debug"
    return "held", StatusCode.REVIEWABLE, "Latest AIT result is held for review.", "ait recover latest"


def _shell_integration_probe() -> dict[str, object]:
    """Probe which shell helpers the user's shell has.

    Relies on the snippet emitted by `ait shell probe-env` having
    been eval'd before invoking `ait doctor`. When the snippet was
    not eval'd, this returns conservatively "MISSING" for every
    helper — the worst case is one false "missing" warning, never
    a false "defined". See spec § `ait doctor` shell-integration probe.
    """
    def _check(env_var: str) -> str:
        return "defined" if os.environ.get(env_var) == "1" else "MISSING"

    ait_wrapper = _check("AIT_SHELL_PROBE_AIT")
    continue_should_cd = _check("AIT_SHELL_PROBE_CONTINUE_SHOULD_CD")
    continue_reminder = _check("AIT_SHELL_PROBE_CONTINUE_REMINDER")
    needs_fix = "MISSING" in (continue_should_cd, continue_reminder)
    return {
        "ait_wrapper": ait_wrapper,
        "continue_should_cd": continue_should_cd,
        "continue_reminder": continue_reminder,
        "needs_fix": needs_fix,
    }


def _format_shell_integration_probe(probe: dict[str, object]) -> str:
    lines = [
        "Shell integration",
        f"  ait() wrapper:           {probe['ait_wrapper']}",
        f"  _ait_continue_should_cd: {probe['continue_should_cd']}",
        f"  _ait_continue_reminder:  {probe['continue_reminder']}",
    ]
    if probe.get("needs_fix"):
        lines.extend([
            '  fix: eval "$(ait shell probe-env)" && ait doctor',
            "       to confirm; if still MISSING, re-source your rc or run",
            "       ait shell install --shell <zsh|bash>",
        ])
    return "\n".join(lines)


def _format_status_condensed(payload: dict[str, object]) -> str:
    """Spec-blessed condensed status output (target ~13 lines).

    Three named blocks: Repo, Workspace, Wrap behavior. Trailing OK
    when healthy; otherwise a single-line failure reason.

    See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md
    § `ait status` redesigned output.
    """
    detected = (
        payload.get("agent_state", {}).get("detected_context", {})
        if isinstance(payload.get("agent_state"), dict)
        else {}
    )
    repo_root = detected.get("repo_root") or "<unknown repo>"

    lines: list[str] = []
    version = _ait_version_label()
    install_method = _detect_install_method()
    bin_path = sys.argv[0] if sys.argv and sys.argv[0] else "ait"
    lines.append(f"AIT {version} · {install_method} · {bin_path}")
    lines.append("")

    # Repo block
    lines.append(f"Repo {repo_root}")
    lines.append(_kv("initialized", "yes" if payload.get("git_repo") else "no"))
    daemon = payload.get("daemon") or {}
    if isinstance(daemon, dict) and daemon.get("running"):
        lines.append(_kv("daemon", f"running (pid {daemon.get('pid')})"))
    else:
        lines.append(_kv("daemon", "not running"))
    memory = payload.get("memory") or {}
    if isinstance(memory, dict):
        issues = memory.get("lint_issue_count", 0)
        lines.append(
            _kv("memory", f"{memory.get('health', 'unknown')} ({issues} lint issues)")
        )
    lines.append(_kv("attempts", _format_attempts_summary(payload.get("recovery"))))
    _recovery = payload.get("recovery")
    if isinstance(_recovery, dict):
        lines.extend(_cleanup_hint_lines(_recovery.get("cleanup_hint")))
    lines.append("")

    # Workspace block
    workspace_line, workspace_details = _workspace_summary(detected)
    lines.append(workspace_line)
    lines.extend(workspace_details)
    lines.append("")

    # Wrap behavior block (introduced in P1.1)
    wb = payload.get("wrap_behavior") or {}
    if isinstance(wb, dict) and wb:
        lines.append("Wrap behavior")
        lines.append(_kv("current", str(wb.get("current", "unknown"))))
        lines.append(_kv("disable once", str(wb.get("disable_once", ""))))
        lines.append(_kv("disable shell", str(wb.get("disable_shell", ""))))
        lines.append("")

    if payload.get("ok") and payload.get("agent_cli_ready"):
        lines.append("OK")
    else:
        lines.append(f"NOT OK: {payload.get('agent_cli_message') or 'see --verbose'}")

    return "\n".join(lines)


def _kv(key: str, value: str) -> str:
    return f"  {key:<14}{value}"


def _ait_version_label() -> str:
    try:
        return metadata.version("ait")
    except metadata.PackageNotFoundError:
        return "unknown"


def _detect_install_method() -> str:
    exe = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else Path()
    parts = exe.parts
    if "pipx" in parts:
        return "pipx"
    if "Homebrew" in parts or "homebrew" in parts:
        return "brew"
    if ".venv" in parts:
        return "dev"
    return "pip"


def _format_attempts_summary(recovery: object) -> str:
    if not isinstance(recovery, dict):
        return "unknown"
    active = recovery.get("active_count", 0)
    archived = recovery.get("archived_count", 0)
    return f"{active} active, {archived} archived"


def _workspace_summary(detected: dict[str, object]) -> tuple[str, list[str]]:
    if detected.get("is_ait_workspace"):
        attempt_id = str(detected.get("attempt_id") or "?")
        short_id = attempt_id.split(":")[-1][:9].upper()
        target = detected.get("target_branch") or "unknown"
        head = detected.get("current_branch") or "detached"
        dirty = detected.get("dirty")
        dirty_str = "yes" if dirty else "no"
        return (
            f"Workspace ⟶  attempt {short_id} (you are here)",
            [
                _kv("target", str(target)),
                _kv("HEAD", str(head)),
                _kv("dirty", dirty_str),
            ],
        )
    return (
        "Workspace ⟶  primary checkout (no active attempt)",
        [_kv("next", "run `claude` to enter an attempt")],
    )


def _format_status(payload: dict[str, object], *, debug: bool = False) -> str:
    binary_label = "Real Claude binary" if payload["adapter"] == "claude-code" else "Real agent binary"
    installation = payload.get("installation")
    lines = []
    if isinstance(installation, dict):
        lines.extend(_format_installation_alert_lines(installation))
    lines.extend(_format_status_current_work(payload.get("recovery"), debug=debug))
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
    bypass = payload.get("bypass_detection")
    if isinstance(bypass, dict):
        lines.append(f"Bypass detection: {bypass.get('status', 'unknown')}")
        message = bypass.get("message")
        if message:
            lines.append(f"Bypass detail: {message}")
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

def _format_status_current_work(recovery: object, *, debug: bool = False) -> list[str]:
    lines = ["AIT Status"]
    if not isinstance(recovery, dict):
        return lines
    lines.append(f"Latest result: {recovery.get('status', 'unknown')}")
    if recovery.get("attempt_handle"):
        lines.append(f"Attempt: {recovery.get('attempt_handle')}")
    if recovery.get("attempt_description"):
        lines.append(f"Description: {recovery.get('attempt_description')}")
    message = recovery.get("message")
    if message:
        lines.append(str(message))
    changed_files = recovery.get("changed_files", [])
    if isinstance(changed_files, list) and changed_files:
        lines.append(f"Changed: {len(changed_files)} files")
    review = recovery.get("review")
    if isinstance(review, dict) and review:
        lines.append(
            "Review: "
            f"{review.get('status', 'unknown')} "
            f"risk={review.get('risk_level', 'unknown')} "
            f"findings={review.get('finding_count', 0)}"
        )
        if review.get("overridden"):
            lines.append("Review override: true")
    next_step = _recovery_next_step_for_text(recovery)
    if next_step:
        lines.append(f"Next: {next_step}")
    lines.append("Adapter health: run ait doctor for install and wrapper checks")
    lines.extend(_cleanup_hint_lines(recovery.get("cleanup_hint")))
    if debug:
        lines.append("Recovery debug:")
        lines.append(f"  Canonical ID: {recovery.get('attempt_id')}")
        lines.append(f"  Workspace: {recovery.get('workspace_ref')}")
        lines.append(f"  Lease: {recovery.get('lease_path')}")
        lines.append(f"  Apply readiness: {recovery.get('status', 'unknown')}")
        if next_step:
            lines.append(f"  Recover next: {next_step}")
        dev_servers = recovery.get("dev_servers", [])
        if isinstance(dev_servers, list) and dev_servers:
            for server in dev_servers:
                if isinstance(server, dict):
                    lines.append(
                        "  Dev server: "
                        f"pid={server.get('pid')} port={server.get('port')} "
                        f"log={server.get('log_path')}"
                    )
        integration = recovery.get("integration")
        if isinstance(integration, dict) and integration:
            lines.append(f"  Base attempt: {integration.get('base_attempt_id')}")
            lines.append(f"  Strategy: {integration.get('strategy')}")
            lines.append(f"  Classification: {integration.get('classification')}")
        decision = recovery.get("decision_report", {})
        if isinstance(decision, dict):
            reasons = decision.get("reasons", [])
            if isinstance(reasons, (list, tuple)) and reasons:
                first = reasons[0]
                if isinstance(first, dict):
                    lines.append(f"  Reason code: {first.get('code')}")
    return lines


def _recovery_next_step_for_text(recovery: dict[str, object]) -> str | None:
    next_step = recovery.get("next_step")
    if not next_step:
        return None
    handle = recovery.get("attempt_handle")
    if handle:
        return str(next_step).replace(" latest", f" {handle}", 1)
    return str(next_step)

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

def _format_status_all(payload: list[dict[str, object]], *, debug: bool = False) -> str:
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
        recovery = payload[0].get("recovery")
        if isinstance(recovery, dict):
            lines.append("AIT Recovery")
            lines.append(f"- latest: {recovery.get('status', 'unknown')}")
            if recovery.get("attempt_handle"):
                lines.append(f"  attempt: {recovery.get('attempt_handle')}")
            if recovery.get("attempt_description"):
                lines.append(f"  description: {recovery.get('attempt_description')}")
            message = recovery.get("message")
            if message:
                lines.append(f"  detail: {message}")
            changed_files = recovery.get("changed_files", [])
            if isinstance(changed_files, list) and changed_files:
                lines.append(f"  changed: {len(changed_files)} files")
            review = recovery.get("review")
            if isinstance(review, dict) and review:
                lines.append(
                    "  review: "
                    f"{review.get('status', 'unknown')} "
                    f"risk={review.get('risk_level', 'unknown')} "
                    f"findings={review.get('finding_count', 0)}"
                )
                if review.get("overridden"):
                    lines.append("  review override: true")
            next_step = recovery.get("next_step")
            if next_step:
                lines.append(f"  next: {next_step}")
            if debug:
                lines.append(f"  canonical id: {recovery.get('attempt_id')}")
                lines.append(f"  workspace: {recovery.get('workspace_ref')}")
                lines.append(f"  lease: {recovery.get('lease_path')}")
                dev_servers = recovery.get("dev_servers", [])
                if isinstance(dev_servers, list) and dev_servers:
                    for server in dev_servers:
                        if isinstance(server, dict):
                            lines.append(
                                "  dev server: "
                                f"pid={server.get('pid')} port={server.get('port')} "
                                f"log={server.get('log_path')}"
                            )
                decision = recovery.get("decision_report", {})
                if isinstance(decision, dict):
                    reasons = decision.get("reasons", [])
                    if isinstance(reasons, (list, tuple)) and reasons and isinstance(reasons[0], dict):
                        lines.append(f"  reason code: {reasons[0].get('code')}")
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
            f"bypass={item.get('bypass_detection', {}).get('status', 'unknown') if isinstance(item.get('bypass_detection'), dict) else 'unknown'} "
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


def _dev_server_payload(repo_root: str | Path, workspace_ref: str) -> list[dict[str, object]]:
    try:
        return [asdict(record) for record in dev_servers_for_worktree(repo_root, workspace_ref)]
    except Exception:
        return []
