from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ait.bug_report import collector as collector_mod
from ait.bug_report.collector import CollectedEntry
from ait.bug_report.seen_store import load_seen, record_seen


@dataclass
class FlushDecision:
    action: str   # "prompt" | "silent" | "reprompt"
    to_prompt: list[CollectedEntry]


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decide_prompt(*, now: str, reprompt_days: int = 7) -> FlushDecision:
    entries = collector_mod.collector().entries()
    if not entries:
        return FlushDecision(action="silent", to_prompt=[])
    seen = load_seen()
    now_dt = _parse(now)
    to_prompt: list[CollectedEntry] = []
    for entry in entries:
        e = seen.get(entry.fingerprint)
        if e is None:
            to_prompt.append(entry)
            continue
        if e.submitted_issue_url and (e.last_known_state or "open") == "open":
            # Silent. Update count and last_seen_at per spec dedup table.
            record_seen(entry.fingerprint, category=entry.category, now=now)
            continue
        if e.submitted_issue_url and e.last_known_state in ("closed", "locked"):
            to_prompt.append(entry)  # regression re-prompt
            continue
        if not e.submitted_issue_url:
            last = _parse(e.last_seen_at) if e.last_seen_at else now_dt
            age = (now_dt - last).days
            if age >= reprompt_days:
                to_prompt.append(entry)
            else:
                # Silent. Update count and last_seen_at per spec dedup table.
                record_seen(entry.fingerprint, category=entry.category, now=now)
    action = "prompt" if to_prompt else "silent"
    return FlushDecision(action=action, to_prompt=to_prompt)
