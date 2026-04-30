from __future__ import annotations

import json
from pathlib import Path

from ait.app import show_attempt
from ait.db.core import utc_now
from ait.memory_eval import evaluate_memory_retrievals
from ait.report import build_work_graph, write_work_graph_html
from ait.repo import resolve_repo_root


def refresh_run_reports(repo_root: str | Path, *, latest_attempt_id: str | None = None) -> dict[str, object]:
    root = resolve_repo_root(repo_root)
    report_dir = root / ".ait" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    graph = build_work_graph(root)
    graph_path = write_work_graph_html(graph, report_dir / "graph.html")
    memory_eval = evaluate_memory_retrievals(root)
    latest_attempt = _latest_attempt_payload(root, latest_attempt_id)
    health = _health_rollup(
        latest_attempt=latest_attempt,
        memory_eval_status=memory_eval.status,
        memory_eval_next_steps=_memory_eval_next_steps(memory_eval.status),
    )
    payload = {
        "generated_at": utc_now(),
        "repo_root": str(root),
        "latest_attempt": latest_attempt,
        "health": health,
        "memory_eval": {
            "status": memory_eval.status,
            "event_count": memory_eval.event_count,
            "average_score": memory_eval.average_score,
            "next_steps": _memory_eval_next_steps(memory_eval.status),
        },
        "graph_html_path": str(graph_path),
        "recommended_next_steps": health["next_steps"],
    }
    status_path = report_dir / "status.json"
    status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["status_path"] = str(status_path)
    return payload


def _latest_attempt_payload(repo_root: Path, attempt_id: str | None) -> dict[str, object] | None:
    if not attempt_id:
        return None
    try:
        shown = show_attempt(repo_root, attempt_id=attempt_id)
    except LookupError:
        return {"attempt_id": attempt_id}
    outcome = shown.outcome or {}
    attempt = shown.attempt
    return {
        "attempt_id": attempt_id,
        "intent_id": attempt.get("intent_id"),
        "agent_id": attempt.get("agent_id"),
        "reported_status": attempt.get("reported_status"),
        "verified_status": attempt.get("verified_status"),
        "outcome_class": outcome.get("outcome_class"),
        "workspace_ref": attempt.get("workspace_ref"),
    }


def _memory_eval_next_steps(status: str) -> list[str]:
    return ["ait memory eval", "ait graph --html"] if status in {"warn", "fail"} else []


def _recommended_next_steps(memory_eval_status: str) -> list[str]:
    return _memory_eval_next_steps(memory_eval_status)


def _health_rollup(
    *,
    latest_attempt: dict[str, object] | None,
    memory_eval_status: str,
    memory_eval_next_steps: list[str],
) -> dict[str, object]:
    status = "pass"
    reasons: list[str] = []
    next_steps: list[str] = []
    if memory_eval_status == "fail":
        status = "fail"
        reasons.append("memory eval failed")
        next_steps.extend(memory_eval_next_steps)
    elif memory_eval_status == "warn":
        status = "warn"
        reasons.append("memory eval warning")
        next_steps.extend(memory_eval_next_steps)
    if latest_attempt and _latest_attempt_failed(latest_attempt):
        if status != "fail":
            status = "warn"
        reasons.append("latest attempt failed")
        next_steps.append("ait graph --html")
    return {
        "status": status,
        "reasons": _dedupe(reasons),
        "next_steps": _dedupe(next_steps),
    }


def _latest_attempt_failed(latest_attempt: dict[str, object]) -> bool:
    verified = str(latest_attempt.get("verified_status") or "")
    outcome = str(latest_attempt.get("outcome_class") or "")
    return verified == "failed" or outcome.startswith("failed")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
