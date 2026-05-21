from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess


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
    # P1 fix: PID alone is not sufficient to prove the owner is still
    # alive. Linux and macOS reuse PIDs aggressively after long
    # uptime, so a stale lease whose owner died can be misread as
    # "still active" if a new unrelated process inherited the PID.
    # We additionally record the wall-clock start time of the owning
    # process. Defaults to None for backward compatibility with lease
    # files written before this field existed; on those leases we
    # fall back to PID-only liveness with a known caveat.
    owner_started_at: str | None = None


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
    owner_pid = os.getpid()
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
        owner_pid=owner_pid,
        owner_command=owner_command,
        state=state,
        cleanup_policy=cleanup_policy,
        preserve_reason=preserve_reason,
        owner_started_at=_pid_started_at(owner_pid),
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
        # When the owning PID is reassigned (e.g. the daemon hand-off),
        # refresh the recorded start time so the liveness check stays
        # consistent.
        values["owner_started_at"] = _pid_started_at(owner_pid)
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
    """Whether the lease's owning process is still alive.

    P1 fix: a bare ``os.kill(pid, 0)`` check is vulnerable to PID
    reuse on long-uptime hosts — the original owner exits, another
    unrelated process gets the same PID, and the lease is incorrectly
    treated as held. When the lease records an ``owner_started_at``
    timestamp, we verify the current process with that PID has the
    same start time. Mismatch ⇒ the PID was reused ⇒ owner is dead.

    Leases written before ``owner_started_at`` existed (or on
    platforms where we cannot determine the start time) fall back to
    the original PID-only check.
    """
    if lease.owner_pid is None:
        return False
    try:
        os.kill(lease.owner_pid, 0)
    except OSError:
        return False
    if lease.owner_started_at is None:
        return True
    current_started_at = _pid_started_at(lease.owner_pid)
    if current_started_at is None:
        # Cannot determine start time now (platform regression,
        # permissions, etc.). Trust the PID check rather than
        # falsely declaring the lease dead.
        return True
    return current_started_at == lease.owner_started_at


def _pid_started_at(pid: int) -> str | None:
    """Best-effort wall-clock start time of ``pid``.

    Returned as an opaque string we only need to be equal for the
    same process instance and unequal across PID reuse. Returns None
    if we cannot determine the start time (Windows, permission
    issues, race with process exit, etc.); callers MUST treat None
    as "do not use for liveness".

    Linux: ``/proc/<pid>/stat`` field 22 (start time in clock ticks
    since boot) combined with ``/proc/stat`` ``btime``.
    macOS / BSD: ``ps -o lstart= -p <pid>`` (opaque date string).
    """
    if pid <= 0:
        return None
    # Linux fast path
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        if stat_path.exists():
            content = stat_path.read_text(encoding="utf-8", errors="replace")
            # The comm field (field 2) may contain spaces or parens;
            # split from the right of the last ')'.
            tail = content.rsplit(")", 1)
            if len(tail) == 2:
                fields = tail[1].split()
                # fields[0] is state (field 3), fields[19] is field 22 (starttime).
                if len(fields) > 19:
                    ticks = int(fields[19])
                    boot_time: int | None = None
                    try:
                        with open("/proc/stat", encoding="utf-8") as f:
                            for line in f:
                                if line.startswith("btime "):
                                    boot_time = int(line.split()[1])
                                    break
                    except OSError:
                        boot_time = None
                    if boot_time is not None:
                        try:
                            hz = os.sysconf("SC_CLK_TCK")
                        except (ValueError, OSError):
                            hz = 100
                        start_epoch = boot_time + (ticks / hz)
                        return (
                            datetime.fromtimestamp(start_epoch, tz=UTC)
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        )
    except (OSError, ValueError, IndexError):
        pass
    # macOS / BSD fallback
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if result.returncode == 0:
            stamp = result.stdout.strip()
            if stamp:
                return stamp
    except (OSError, subprocess.SubprocessError):
        pass
    return None


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
            owner_started_at=_str_or_none(payload.get("owner_started_at")),
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
