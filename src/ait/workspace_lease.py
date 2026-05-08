from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path


LEASE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WorkspaceLease:
    schema_version: int
    attempt_id: str
    intent_id: str | None
    repo_root: str
    workspace_ref: str
    base_ref_oid: str
    base_ref_name: str | None
    created_at: str
    last_touched_at: str
    owner_pid: int | None
    owner_command: str | None
    state: str
    cleanup_policy: str
    preserve_reason: str | None


def workspace_lease_path(workspace_ref: str | Path) -> Path:
    worktree_path = Path(workspace_ref).resolve()
    return worktree_path.parent.parent / "leases" / f"{worktree_path.name}.json"


def _legacy_workspace_lease_path(workspace_ref: str | Path) -> Path:
    worktree_path = Path(workspace_ref).resolve()
    return worktree_path.parent / f"{worktree_path.name}.lease.json"


def create_workspace_lease(
    *,
    repo_root: str | Path,
    workspace_ref: str | Path,
    attempt_id: str,
    base_ref_oid: str,
    base_ref_name: str | None,
    intent_id: str | None = None,
    owner_command: str | None = None,
    state: str = "active",
    cleanup_policy: str = "auto",
    preserve_reason: str | None = None,
) -> WorkspaceLease:
    now = _utc_now()
    lease = WorkspaceLease(
        schema_version=LEASE_SCHEMA_VERSION,
        attempt_id=attempt_id,
        intent_id=intent_id,
        repo_root=str(Path(repo_root).resolve()),
        workspace_ref=str(Path(workspace_ref).resolve()),
        base_ref_oid=base_ref_oid,
        base_ref_name=base_ref_name,
        created_at=now,
        last_touched_at=now,
        owner_pid=os.getpid(),
        owner_command=owner_command,
        state=state,
        cleanup_policy=cleanup_policy,
        preserve_reason=preserve_reason,
    )
    write_workspace_lease(lease)
    return lease


def read_workspace_lease(workspace_ref: str | Path) -> WorkspaceLease | None:
    path = workspace_lease_path(workspace_ref)
    if not path.exists():
        legacy_path = _legacy_workspace_lease_path(workspace_ref)
        if legacy_path.exists():
            path = legacy_path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _lease_from_payload(payload)


def write_workspace_lease(lease: WorkspaceLease) -> None:
    path = workspace_lease_path(lease.workspace_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(lease)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def update_workspace_lease(
    workspace_ref: str | Path,
    *,
    attempt_id: str | None = None,
    intent_id: str | None = None,
    repo_root: str | Path | None = None,
    base_ref_oid: str | None = None,
    base_ref_name: str | None = None,
    owner_pid: int | None = None,
    owner_command: str | None = None,
    state: str | None = None,
    cleanup_policy: str | None = None,
    preserve_reason: str | None = None,
    clear_preserve_reason: bool = False,
) -> WorkspaceLease | None:
    lease = read_workspace_lease(workspace_ref)
    if lease is None:
        return None
    values: dict[str, object] = {
        "last_touched_at": _utc_now(),
    }
    if attempt_id is not None:
        values["attempt_id"] = attempt_id
    if intent_id is not None:
        values["intent_id"] = intent_id
    if repo_root is not None:
        values["repo_root"] = str(Path(repo_root).resolve())
    if base_ref_oid is not None:
        values["base_ref_oid"] = base_ref_oid
    if base_ref_name is not None:
        values["base_ref_name"] = base_ref_name
    if owner_pid is not None:
        values["owner_pid"] = owner_pid
    if owner_command is not None:
        values["owner_command"] = owner_command
    if state is not None:
        values["state"] = state
    if cleanup_policy is not None:
        values["cleanup_policy"] = cleanup_policy
    if preserve_reason is not None or clear_preserve_reason:
        values["preserve_reason"] = preserve_reason
    updated = replace(lease, **values)
    write_workspace_lease(updated)
    return updated


def remove_workspace_lease(workspace_ref: str | Path) -> None:
    for path in (workspace_lease_path(workspace_ref), _legacy_workspace_lease_path(workspace_ref)):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def lease_owner_alive(lease: WorkspaceLease) -> bool:
    if lease.owner_pid is None:
        return False
    try:
        os.kill(lease.owner_pid, 0)
    except OSError:
        return False
    return True


def lease_payload(workspace_ref: str | Path) -> dict[str, object] | None:
    lease = read_workspace_lease(workspace_ref)
    if lease is None:
        return None
    payload = asdict(lease)
    payload["lease_path"] = str(workspace_lease_path(workspace_ref))
    payload["owner_alive"] = lease_owner_alive(lease)
    return payload


def _lease_from_payload(payload: object) -> WorkspaceLease | None:
    if not isinstance(payload, dict):
        return None
    try:
        return WorkspaceLease(
            schema_version=int(payload.get("schema_version", LEASE_SCHEMA_VERSION)),
            attempt_id=str(payload["attempt_id"]),
            intent_id=_str_or_none(payload.get("intent_id")),
            repo_root=str(payload["repo_root"]),
            workspace_ref=str(payload["workspace_ref"]),
            base_ref_oid=str(payload.get("base_ref_oid", "")),
            base_ref_name=_str_or_none(payload.get("base_ref_name")),
            created_at=str(payload.get("created_at") or _utc_now()),
            last_touched_at=str(payload.get("last_touched_at") or _utc_now()),
            owner_pid=_int_or_none(payload.get("owner_pid")),
            owner_command=_str_or_none(payload.get("owner_command")),
            state=str(payload.get("state") or "orphan"),
            cleanup_policy=str(payload.get("cleanup_policy") or "auto"),
            preserve_reason=_str_or_none(payload.get("preserve_reason")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
