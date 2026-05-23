from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from ait.db import utc_now


RECENT_SCHEMA_VERSION = 1
RECENT_LIMIT = 40


@dataclass(frozen=True, slots=True)
class RecentActivity:
    kind: str
    repo_root: str
    updated_at: str
    attempt_id: str | None = None
    workspace_ref: str | None = None
    session_id: str | None = None


def record_recent_attempt(
    repo_root: str | Path,
    *,
    attempt_id: str,
    workspace_ref: str | Path,
    updated_at: str | None = None,
) -> Path | None:
    return _record_recent(
        RecentActivity(
            kind="attempt",
            repo_root=str(Path(repo_root).resolve()),
            attempt_id=attempt_id,
            workspace_ref=str(Path(workspace_ref).resolve()),
            session_id=None,
            updated_at=updated_at or utc_now(),
        )
    )


def record_recent_session(
    repo_root: str | Path,
    *,
    session_id: str,
    updated_at: str | None = None,
) -> Path | None:
    return _record_recent(
        RecentActivity(
            kind="session",
            repo_root=str(Path(repo_root).resolve()),
            attempt_id=None,
            workspace_ref=None,
            session_id=session_id,
            updated_at=updated_at or utc_now(),
        )
    )


def list_recent_activities() -> tuple[RecentActivity, ...]:
    path = recent_activity_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    raw_items = payload.get("activities")
    if not isinstance(raw_items, list):
        return ()
    activities: list[RecentActivity] = []
    for item in raw_items:
        activity = _activity_from_payload(item)
        if activity is not None:
            activities.append(activity)
    activities.sort(key=lambda item: item.updated_at, reverse=True)
    return tuple(activities)


def recent_activity_path() -> Path:
    return _state_dir() / "recent.json"


def _record_recent(activity: RecentActivity) -> Path | None:
    try:
        path = recent_activity_path()
        existing = list(list_recent_activities())
        keyed: dict[tuple[str, str, str], RecentActivity] = {
            _activity_key(item): item for item in existing
        }
        keyed[_activity_key(activity)] = activity
        activities = sorted(
            keyed.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )[:RECENT_LIMIT]
        payload = {
            "schema_version": RECENT_SCHEMA_VERSION,
            "activities": [_activity_payload(item) for item in activities],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp_path, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path
    except OSError:
        return None


def _state_dir() -> Path:
    override = os.environ.get("AIT_STATE_DIR")
    if override:
        return Path(override).expanduser()
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "ait"
    return Path.home() / ".local" / "state" / "ait"


def _activity_key(activity: RecentActivity) -> tuple[str, str, str]:
    if activity.kind == "attempt":
        return (activity.kind, activity.repo_root, activity.attempt_id or "")
    if activity.kind == "session":
        return (activity.kind, activity.repo_root, activity.session_id or "")
    return (activity.kind, activity.repo_root, activity.updated_at)


def _activity_payload(activity: RecentActivity) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": activity.kind,
        "repo_root": activity.repo_root,
        "updated_at": activity.updated_at,
    }
    if activity.attempt_id is not None:
        payload["attempt_id"] = activity.attempt_id
    if activity.workspace_ref is not None:
        payload["workspace_ref"] = activity.workspace_ref
    if activity.session_id is not None:
        payload["session_id"] = activity.session_id
    return payload


def _activity_from_payload(payload: object) -> RecentActivity | None:
    if not isinstance(payload, dict):
        return None
    try:
        kind = str(payload["kind"])
        repo_root = str(payload["repo_root"])
        updated_at = str(payload["updated_at"])
    except KeyError:
        return None
    if kind not in {"attempt", "session"}:
        return None
    return RecentActivity(
        kind=kind,
        repo_root=repo_root,
        updated_at=updated_at,
        attempt_id=_optional_str(payload.get("attempt_id")),
        workspace_ref=_optional_str(payload.get("workspace_ref")),
        session_id=_optional_str(payload.get("session_id")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
