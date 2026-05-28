from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ait.bug_report.config import state_dir


@dataclass
class PendingReport:
    fingerprint: str
    title: str
    body: str
    category: str
    created_at: str


def _pending_dir() -> Path:
    return state_dir() / "pending"


def _path_for(fingerprint: str) -> Path:
    # Sanitize: only allow fp:hex form (collector controls input but defense in depth).
    safe = fingerprint.replace("/", "_").replace("\\", "_")
    return _pending_dir() / f"{safe}.json"


def enqueue(report: PendingReport) -> None:
    d = _pending_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = _path_for(report.fingerprint)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def load_pending(fingerprint: str) -> PendingReport | None:
    p = _path_for(fingerprint)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PendingReport(
            fingerprint=data["fingerprint"],
            title=data["title"],
            body=data["body"],
            category=data["category"],
            created_at=data["created_at"],
        )
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def list_pending() -> list[str]:
    d = _pending_dir()
    if not d.exists():
        return []
    out = []
    for entry in d.iterdir():
        if entry.suffix == ".json":
            out.append(entry.stem)
    return out


def remove(fingerprint: str) -> bool:
    p = _path_for(fingerprint)
    if not p.exists():
        return False
    p.unlink()
    return True


def clear_pending() -> int:
    d = _pending_dir()
    if not d.exists():
        return 0
    count = 0
    for entry in list(d.iterdir()):
        if entry.suffix == ".json":
            entry.unlink()
            count += 1
    return count


def prune_old(*, now: dt.datetime, max_age_days: int = 30) -> int:
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    cutoff = now - dt.timedelta(days=max_age_days)
    pruned = 0
    for fp in list_pending():
        report = load_pending(fp)
        if report is None:
            continue
        try:
            created = dt.datetime.fromisoformat(
                report.created_at.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if created < cutoff:
            remove(fp)
            pruned += 1
    return pruned
