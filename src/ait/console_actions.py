from __future__ import annotations

import json
from pathlib import Path

from ait.app import show_attempt
from ait.db import connect_db, utc_now
from ait.ids import new_ulid
from ait.repo import resolve_repo_root
from ait.review import latest_review_summary
from ait.team_policy import TeamPolicyEnforcementError, enforce_team_policy

CONSOLE_ACTION_SCHEMA = "ait.console_action"
CONSOLE_ACTION_SCHEMA_VERSION = 1
CONSOLE_ACTION_JOURNAL = ".ait/actions/console-actions.jsonl"


def run_console_action(
    repo_root: str | Path,
    *,
    action: str,
    attempt_id: str,
    dry_run: bool = True,
    actor_label: str = "local-user",
) -> dict[str, object]:
    root = resolve_repo_root(repo_root)
    action_id = f"act_{new_ulid()}"
    started_at = utc_now()
    domain_command = _domain_command(action, attempt_id)
    preflight = _preflight(root, action=action, attempt_id=attempt_id)
    try:
        policy_enforcement = enforce_team_policy(root, operation="console_action", attempt_id=attempt_id)
    except TeamPolicyEnforcementError as exc:
        policy_enforcement = exc.payload
        preflight = {
            "status": "blocked",
            "checks": [
                *list(preflight.get("checks", [])),
                *[
                    {
                        "name": f"team_policy:{check.get('name')}",
                        "status": check.get("status"),
                        "message": check.get("message"),
                    }
                    for check in policy_enforcement.get("checks", [])
                ],
            ],
        }
    if dry_run:
        status = "planned" if preflight["status"] == "passed" else "blocked"
        error = None if status == "planned" else "preflight blocked action"
    else:
        status = "failed"
        error = "console action execution is not implemented; use the CLI domain command"
    payload = {
        "schema": CONSOLE_ACTION_SCHEMA,
        "schema_version": CONSOLE_ACTION_SCHEMA_VERSION,
        "action_id": action_id,
        "repo_root": str(root),
        "actor_label": actor_label,
        "action": action,
        "target": {"attempt_id": attempt_id},
        "dry_run": dry_run,
        "preflight": preflight,
        "policy_enforcement": policy_enforcement,
        "domain_command": domain_command,
        "started_at": started_at,
        "ended_at": utc_now(),
        "status": status,
        "error": error,
        "rollback_hint": None if dry_run else "retry the equivalent CLI command after inspecting repository state",
        "will_execute": False,
    }
    _append_journal(root, payload)
    return payload


def _preflight(repo_root: Path, *, action: str, attempt_id: str) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    try:
        shown = show_attempt(repo_root, attempt_id=attempt_id)
        attempt = shown.attempt
        resolved_attempt_id = str(attempt["id"])
        checks.append(_check("attempt_exists", True, resolved_attempt_id))
    except Exception as exc:
        checks.append(_check("attempt_exists", False, str(exc)))
        return {"status": "blocked", "checks": checks}
    verified = str(attempt.get("verified_status") or "")
    workspace_ref = str(attempt.get("workspace_ref") or "")
    if action == "apply_attempt":
        checks.append(_check("attempt_succeeded", verified in {"succeeded", "promoted"}, verified))
        checks.append(_check("workspace_ref_present", bool(workspace_ref), workspace_ref))
        review = _latest_review(repo_root, resolved_attempt_id)
        blocked = review.get("status") in {"blocked", "failed"} or bool(review.get("blocking"))
        checks.append(_check("review_gate_clear", not blocked, str(review.get("status") or "none")))
        checks.append(_check("root_dirty_check_deferred", True, "domain apply path performs dirty checkout safety checks"))
    elif action == "recover_attempt":
        checks.append(_check("workspace_ref_present", bool(workspace_ref), workspace_ref))
        checks.append(_check("attempt_not_discarded", verified != "discarded", verified))
    elif action == "discard_attempt":
        checks.append(_check("attempt_not_promoted", verified != "promoted", verified))
        checks.append(_check("workspace_not_root", Path(workspace_ref).resolve() != repo_root.resolve() if workspace_ref else False, workspace_ref))
    else:
        checks.append(_check("known_action", False, action))
    status = "passed" if all(item["status"] == "passed" for item in checks) else "blocked"
    return {"status": status, "checks": checks}


def _latest_review(repo_root: Path, attempt_id: str) -> dict[str, object]:
    db_path = repo_root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return {}
    conn = connect_db(db_path)
    try:
        return latest_review_summary(conn, attempt_id, repo_root=repo_root)
    finally:
        conn.close()


def _domain_command(action: str, attempt_id: str) -> list[str]:
    if action == "apply_attempt":
        return ["ait", "apply", attempt_id, "--format", "json"]
    if action == "recover_attempt":
        return ["ait", "recover", attempt_id, "--format", "json"]
    if action == "discard_attempt":
        return ["ait", "attempt", "discard", attempt_id]
    return ["ait", "console", "action", action, "--attempt", attempt_id]


def _check(name: str, passed: bool, message: str) -> dict[str, object]:
    return {"name": name, "status": "passed" if passed else "blocked", "message": message}


def _append_journal(repo_root: Path, payload: dict[str, object]) -> None:
    path = repo_root / CONSOLE_ACTION_JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


__all__ = [
    "CONSOLE_ACTION_JOURNAL",
    "CONSOLE_ACTION_SCHEMA",
    "CONSOLE_ACTION_SCHEMA_VERSION",
    "run_console_action",
]
