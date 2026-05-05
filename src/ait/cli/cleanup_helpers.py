from __future__ import annotations

from dataclasses import asdict
from pathlib import Path


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
        "items": [asdict(item) for item in report.items],
    }


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
