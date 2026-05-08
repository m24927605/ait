from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ait.decision_codes import cleanup_reason_code
from ait.decision_report import decision_payload, decision_report
from ait.dev_server import dev_servers_for_worktree


def _cleanup_payload(report) -> dict[str, object]:
    return {
        "mode": report.mode,
        "repo_root": report.repo_root,
        "workspaces_root": report.workspaces_root,
        "scanned_count": report.scanned_count,
        "remove_count": report.remove_count,
        "skip_count": report.skip_count,
        "reclaimed_bytes": report.reclaimed_bytes,
        "would_reclaim_bytes": report.would_reclaim_bytes,
        "items": [_cleanup_item_payload(report.repo_root, item) for item in report.items],
    }


def _cleanup_item_payload(repo_root: str, item) -> dict[str, object]:
    payload = asdict(item)
    dev_servers = _dev_server_payload(repo_root, item.path)
    payload["decision_report"] = decision_payload(
        decision_report(
            subject="cleanup",
            subject_id=item.attempt_id,
            decision=item.action,
            safety_level=_cleanup_safety_level(item),
            reason_code=cleanup_reason_code(item.reason),
            reason_message=item.error or item.reason,
            paths=(item.path,),
            debug={
                "kind": item.kind,
                "dirty": item.dirty,
                "deleted": item.deleted,
                "bytes": item.bytes,
                "reported_status": item.reported_status,
                "verified_status": item.verified_status,
                "dev_servers": dev_servers,
            },
        )
    )
    return payload


def _dev_server_payload(repo_root: str, workspace_ref: str) -> list[dict[str, object]]:
    try:
        return [asdict(record) for record in dev_servers_for_worktree(repo_root, workspace_ref)]
    except Exception:
        return []


def _cleanup_safety_level(item) -> str:
    if item.error:
        return "unknown"
    if item.action == "remove":
        return "safe"
    if item.action == "retain":
        return "caution"
    return "unknown"


def _format_cleanup(report) -> str:
    lines = [
        "AIT Cleanup",
        f"Mode: {report.mode}",
        f"Worktrees scanned: {report.scanned_count}",
    ]
    if report.mode == "dry-run":
        lines.append(f"Would reclaim: {_format_bytes(report.would_reclaim_bytes)}")
    else:
        lines.append(f"Reclaimed: {_format_bytes(report.reclaimed_bytes)}")
    lines.append("")
    if not report.items:
        lines.append("No cleanup candidates found.")
    for item in report.items:
        verb = item.action
        if item.deleted:
            verb = "removed"
        elif item.error:
            verb = "error"
        label = Path(item.path).name
        status = item.verified_status or item.reported_status or "unknown"
        detail = item.error or item.reason
        lines.append(
            f"- {verb} {item.kind} {label} {status} {detail} {_format_bytes(item.bytes)}"
        )
    if report.mode == "dry-run" and any(item.action == "remove" for item in report.items):
        lines.extend(["", "Run with --apply to delete removable paths."])
    return "\n".join(lines)


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
