from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ait.bug_report.config import state_dir

SCHEMA_VERSION = 1


@dataclass
class SeenEntry:
    fingerprint: str
    category: str
    count: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""
    submitted_issue_url: str | None = None
    submitted_method: str | None = None
    submitted_at: str | None = None
    last_status_check_at: str | None = None
    last_known_state: str | None = None  # "open" | "closed" | "locked" | None


def _path() -> Path:
    return state_dir() / "seen.json"


def load_seen() -> dict[str, SeenEntry]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, SeenEntry] = {}
    for fp, raw in (data.get("entries") or {}).items():
        out[fp] = SeenEntry(
            fingerprint=fp,
            category=raw.get("category", ""),
            count=int(raw.get("count", 0)),
            first_seen_at=raw.get("first_seen_at", ""),
            last_seen_at=raw.get("last_seen_at", ""),
            submitted_issue_url=raw.get("submitted_issue_url"),
            submitted_method=raw.get("submitted_method"),
            submitted_at=raw.get("submitted_at"),
            last_status_check_at=raw.get("last_status_check_at"),
            last_known_state=raw.get("last_known_state"),
        )
    return out


def save_seen(store: dict[str, SeenEntry]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "entries": {fp: _entry_to_json(e) for fp, e in store.items()},
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def _entry_to_json(e: SeenEntry) -> dict:
    d = asdict(e)
    d.pop("fingerprint", None)
    return d


def record_seen(fingerprint: str, *, category: str, now: str) -> None:
    store = load_seen()
    e = store.get(fingerprint)
    if e is None:
        e = SeenEntry(
            fingerprint=fingerprint,
            category=category,
            count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
    else:
        e.count += 1
        e.last_seen_at = now
    store[fingerprint] = e
    save_seen(store)


def record_submitted(
    fingerprint: str,
    *,
    issue_url: str | None,
    method: str,
    now: str,
) -> None:
    store = load_seen()
    e = store.get(fingerprint)
    if e is None:
        # First record-submit without record-seen — shouldn't happen but be safe.
        e = SeenEntry(
            fingerprint=fingerprint,
            category="",
            count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
    e.submitted_issue_url = issue_url
    e.submitted_method = method
    e.submitted_at = now
    if issue_url:
        e.last_known_state = "open"
    store[fingerprint] = e
    save_seen(store)
