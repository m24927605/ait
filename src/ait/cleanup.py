from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import subprocess

from ait.config import local_config_path
from ait.db import connect_db, list_attempts, run_migrations
from ait.db.records import AttemptRecord
from ait.dev_server import list_dev_servers
from ait.repo import resolve_repo_root
from ait.workspace import get_workspaces_root, remove_attempt_workspace
from ait.workspace_lease import (
    lease_owner_alive,
    read_workspace_lease,
    remove_workspace_lease,
)


DEFAULT_FAILED_RETENTION_DAYS = 14
DEFAULT_ARTIFACT_ALLOWLIST = (
    ".venv",
    "node_modules",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "dist",
    "build",
    "coverage",
    ".coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".turbo",
    ".vite",
)


@dataclass(frozen=True, slots=True)
class CleanupPolicy:
    apply: bool = False
    force: bool = False
    older_than_days: int = DEFAULT_FAILED_RETENTION_DAYS
    include_orphans: bool = False
    worktrees: bool = True
    artifacts: bool = False
    artifact_allowlist: tuple[str, ...] = DEFAULT_ARTIFACT_ALLOWLIST


@dataclass(frozen=True, slots=True)
class CleanupItem:
    path: str
    kind: str
    attempt_id: str | None
    reported_status: str | None
    verified_status: str | None
    action: str
    reason: str
    dirty: bool
    bytes: int
    deleted: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CleanupReport:
    mode: str
    repo_root: str
    workspaces_root: str
    scanned_count: int
    remove_count: int
    skip_count: int
    reclaimed_bytes: int
    would_reclaim_bytes: int
    items: tuple[CleanupItem, ...]


class CleanupError(RuntimeError):
    """Raised when cleanup cannot safely evaluate the repository."""


def cleanup_policy_from_config(
    repo_root: str | Path,
    *,
    apply: bool = False,
    force: bool = False,
    older_than_days: int | None = None,
    include_orphans: bool | None = None,
    worktrees: bool = True,
    artifacts: bool = False,
) -> CleanupPolicy:
    root = resolve_repo_root(repo_root)
    configured = _load_cleanup_config(root)
    retention_days = configured.get("failed_retention_days", DEFAULT_FAILED_RETENTION_DAYS)
    if older_than_days is not None:
        retention_days = older_than_days
    retention_days = int(retention_days)
    if retention_days < 0:
        raise CleanupError("--older-than must be >= 0")

    configured_orphans = bool(configured.get("include_orphans", False))
    allowlist = configured.get("artifact_allowlist", DEFAULT_ARTIFACT_ALLOWLIST)
    return CleanupPolicy(
        apply=apply,
        force=force,
        older_than_days=retention_days,
        include_orphans=configured_orphans if include_orphans is None else include_orphans,
        worktrees=worktrees,
        artifacts=artifacts,
        artifact_allowlist=_coerce_artifact_allowlist(allowlist),
    )


def cleanup_repo(repo_root: str | Path, policy: CleanupPolicy) -> CleanupReport:
    root = resolve_repo_root(repo_root)
    config_path = local_config_path(root)
    db_path = root / ".ait" / "state.sqlite3"
    if not config_path.exists() or not db_path.exists():
        raise CleanupError("not an initialized AIT repo; run `ait init` first")

    workspaces_root = get_workspaces_root(root).resolve()
    workspaces_root.mkdir(parents=True, exist_ok=True)
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        attempts = tuple(list_attempts(conn))
    finally:
        conn.close()

    candidates = _workspace_candidates(workspaces_root, attempts)
    items: list[CleanupItem] = []
    removed_any_worktree = False

    if policy.worktrees:
        for candidate in candidates:
            if candidate.anomaly_reason is not None or candidate.path is None:
                items.append(_anomalous_item(candidate))
                continue
            item = _evaluate_worktree(workspaces_root, candidate.path, candidate.attempt, policy)
            if policy.apply and item.action == "remove":
                item = _delete_worktree_item(item, candidate.attempt, workspaces_root)
                removed_any_worktree = removed_any_worktree or item.deleted
            items.append(item)

    if policy.artifacts:
        for worktree_item in tuple(items):
            if worktree_item.kind != "worktree" or worktree_item.action not in {"retain", "skip"}:
                continue
            if worktree_item.reason not in {"reviewable", "active", "pending", "retention-window"}:
                continue
            worktree_path = Path(worktree_item.path)
            if not _path_is_inside(worktree_path, workspaces_root) or not worktree_path.exists():
                continue
            for artifact_path in _artifact_candidate_paths(worktree_path, policy.artifact_allowlist):
                artifact = _evaluate_artifact(worktree_path, artifact_path, worktree_item)
                if policy.apply and artifact.action == "remove":
                    artifact = _delete_artifact_item(artifact)
                items.append(artifact)

    if removed_any_worktree:
        _git(root, "worktree", "prune", allow_failure=True)

    remove_count = sum(1 for item in items if item.action == "remove")
    skip_count = sum(1 for item in items if item.action == "skip")
    reclaimed_bytes = sum(item.bytes for item in items if item.deleted)
    would_reclaim_bytes = sum(item.bytes for item in items if item.action == "remove" and not item.deleted)
    return CleanupReport(
        mode="apply" if policy.apply else "dry-run",
        repo_root=str(root),
        workspaces_root=str(workspaces_root),
        scanned_count=len(candidates),
        remove_count=remove_count,
        skip_count=skip_count,
        reclaimed_bytes=reclaimed_bytes,
        would_reclaim_bytes=would_reclaim_bytes,
        items=tuple(items),
    )


def _load_cleanup_config(repo_root: Path) -> dict[str, object]:
    path = local_config_path(repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    cleanup = payload.get("cleanup")
    return cleanup if isinstance(cleanup, dict) else {}


def _coerce_artifact_allowlist(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return DEFAULT_ARTIFACT_ALLOWLIST
    names = []
    for item in value:
        text = str(item).strip()
        if not text or text in {".", ".."} or "/" in text:
            continue
        names.append(text)
    return tuple(names) or DEFAULT_ARTIFACT_ALLOWLIST


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path | None  # original (unresolved) path; None when the ref isn't a valid Path
    raw_ref: str  # raw workspace_ref / dir name, for anomalous reporting
    attempt: AttemptRecord | None
    anomaly_reason: str | None  # set when the ref can't be safely resolved


def _workspace_candidates(
    workspaces_root: Path, attempts: tuple[AttemptRecord, ...]
) -> tuple[_Candidate, ...]:
    """Collect cleanup candidates without crashing or following symlinks.

    Keeps the ORIGINAL (unresolved) path so symlinked worktrees are detected
    later; dedupes by resolved path (or raw ref for unresolvable values);
    emits anomalous candidates for malformed/relative refs instead of raising.
    """
    by_key: dict[str, _Candidate] = {}
    for attempt in attempts:
        raw = str(attempt.workspace_ref)
        resolved = safe_resolve_workspace_ref(attempt.workspace_ref)
        if resolved is None:
            by_key.setdefault(f"anomalous:{raw}", _Candidate(None, raw, attempt, "anomalous-ref"))
            continue
        try:
            original = Path(attempt.workspace_ref)
        except (ValueError, TypeError):
            original = resolved
        # DB-backed attempts win over later orphan entries at the same path.
        by_key[str(resolved)] = _Candidate(original, raw, attempt, None)
    if workspaces_root.exists():
        for child in workspaces_root.iterdir():
            if not child.name.startswith("attempt-"):
                continue
            if not (child.is_symlink() or child.is_dir()):
                continue
            # Symlinks keep a raw key so they are never deduped with (or treated
            # as) their resolved target inside workspaces_root.
            key = f"symlink:{child}" if child.is_symlink() else str(child.resolve())
            by_key.setdefault(key, _Candidate(child, str(child), None, None))
    return tuple(by_key[key] for key in sorted(by_key))


def _anomalous_item(candidate: _Candidate) -> CleanupItem:
    attempt = candidate.attempt
    return CleanupItem(
        path=candidate.raw_ref,
        kind="worktree" if attempt is not None else "orphan",
        attempt_id=attempt.id if attempt is not None else None,
        reported_status=attempt.reported_status if attempt is not None else None,
        verified_status=attempt.verified_status if attempt is not None else None,
        action="skip",
        reason=candidate.anomaly_reason or "anomalous-ref",
        dirty=False,
        bytes=0,
    )


def _evaluate_worktree(
    workspaces_root: Path,
    path: Path,
    attempt: AttemptRecord | None,
    policy: CleanupPolicy,
) -> CleanupItem:
    if path.is_symlink():
        # A symlinked worktree candidate is unsafe: never follow/size/delete it
        # (it could resolve into another worktree or outside the repo).
        return _skip_item(path, attempt, "symlink-skip")
    resolved = path.resolve()
    if not path_is_inside(resolved, workspaces_root):
        # Containment BEFORE sizing: never recursively walk an external path
        # that a corrupted workspace_ref points at (DoS / privacy).
        return _skip_item(resolved, attempt, "outside-ait-root")
    size = _path_size(resolved)
    lease = read_workspace_lease(resolved)
    lease_block = _lease_cleanup_block(lease, attempt)
    if lease_block is not None:
        action, reason = lease_block
        if attempt is None:
            return CleanupItem(
                path=str(resolved),
                kind="orphan",
                attempt_id=None,
                reported_status=None,
                verified_status=None,
                action=action,
                reason=reason,
                dirty=False,
                bytes=size,
            )
        return _item(resolved, attempt, action, reason, size=size)
    if _has_active_dev_server(workspaces_root, resolved):
        if attempt is None:
            return CleanupItem(
                path=str(resolved),
                kind="orphan",
                attempt_id=None,
                reported_status=None,
                verified_status=None,
                action="retain",
                reason="active-dev-server",
                dirty=False,
                bytes=size,
            )
        return _item(resolved, attempt, "retain", "active-dev-server", size=size)
    if attempt is None:
        dirty = _is_dirty_worktree(resolved)
        if dirty and not policy.force:
            return CleanupItem(
                path=str(resolved),
                kind="orphan",
                attempt_id=None,
                reported_status=None,
                verified_status=None,
                action="skip",
                reason="dirty-orphan",
                dirty=True,
                bytes=size,
            )
        action = "remove" if policy.include_orphans else "skip"
        return CleanupItem(
            path=str(resolved),
            kind="orphan",
            attempt_id=None,
            reported_status=None,
            verified_status=None,
            action=action,
            reason="unknown-attempt",
            dirty=dirty,
            bytes=size,
        )
    if attempt.reported_status in {"created", "running"}:
        return _item(resolved, attempt, "retain", "active", size=size)
    if attempt.verified_status == "pending" and attempt.reported_status != "crashed":
        return _item(resolved, attempt, "retain", "pending", size=size)

    dirty = _is_dirty_worktree(resolved)
    action, reason = _terminal_decision(attempt, policy)
    if action == "remove" and dirty and not policy.force:
        return _item(resolved, attempt, "skip", "dirty", dirty=True, size=size)
    return _item(resolved, attempt, action, reason, dirty=dirty, size=size)


def _lease_cleanup_block(lease, attempt: AttemptRecord | None) -> tuple[str, str] | None:
    if lease is None:
        return None
    if lease.preserve_reason:
        return "skip", "lease-preserved"
    if (
        lease.state == "active"
        and lease_owner_alive(lease)
        and attempt is None
    ):
        return "retain", "active-lease"
    if lease.state in {"conflict", "orphan"}:
        return "retain", lease.state
    if (
        lease.state == "active"
        and attempt is not None
        and attempt.reported_status in {"created", "running"}
    ):
        return "retain", "active"
    return None


@dataclass(frozen=True, slots=True)
class TerminalDecision:
    """Read-only classification of an attempt's terminal cleanup category.

    Shared by cleanup (for its remove/retain decision + reason) and by
    ``ait status`` (for read-only reclaimable counting), so the two never
    drift. Only covers the terminal-status layer; cleanup's lease/dirty/
    dev-server/orphan protections live outside this in ``_evaluate_worktree``.
    """

    category: str  # "reclaimable" | "retained_succeeded" | "not_reclaimable"
    reason: str  # promoted | discarded | reviewable | stale-failed | retention-window


def classify_terminal(attempt: AttemptRecord, *, retention_days: int) -> TerminalDecision:
    if attempt.verified_status in {"promoted", "discarded"}:
        return TerminalDecision("reclaimable", attempt.verified_status)
    if attempt.verified_status == "succeeded":
        return TerminalDecision("retained_succeeded", "reviewable")
    if attempt.verified_status == "failed" or attempt.reported_status == "crashed":
        if _older_than_retention(attempt, retention_days):
            return TerminalDecision("reclaimable", "stale-failed")
        return TerminalDecision("not_reclaimable", "retention-window")
    return TerminalDecision("not_reclaimable", "reviewable")


def _terminal_decision(attempt: AttemptRecord, policy: CleanupPolicy) -> tuple[str, str]:
    decision = classify_terminal(attempt, retention_days=policy.older_than_days)
    action = "remove" if decision.category == "reclaimable" else "retain"
    return action, decision.reason


def _has_active_dev_server(workspaces_root: Path, worktree_path: Path) -> bool:
    repo_root = workspaces_root.parent.parent
    try:
        records = list_dev_servers(repo_root)
    except Exception:
        return False
    resolved = worktree_path.resolve()
    for record in records:
        try:
            if Path(record.worktree_path).resolve() == resolved:
                return True
        except OSError:
            continue
    return False


def _older_than_retention(attempt: AttemptRecord, days: int) -> bool:
    timestamp = attempt.ended_at or attempt.heartbeat_at or attempt.started_at
    parsed = _parse_utc_timestamp(timestamp)
    if parsed is None:
        return False
    return parsed <= datetime.now(tz=UTC) - timedelta(days=days)


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _item(
    path: Path,
    attempt: AttemptRecord,
    action: str,
    reason: str,
    *,
    dirty: bool = False,
    size: int,
) -> CleanupItem:
    return CleanupItem(
        path=str(path),
        kind="worktree",
        attempt_id=attempt.id,
        reported_status=attempt.reported_status,
        verified_status=attempt.verified_status,
        action=action,
        reason=reason,
        dirty=dirty,
        bytes=size,
    )


def _skip_item(path: Path, attempt: AttemptRecord | None, reason: str, *, size: int = 0) -> CleanupItem:
    """Build a skip item for either a DB-backed attempt or an orphan (None)."""
    if attempt is None:
        return CleanupItem(
            path=str(path),
            kind="orphan",
            attempt_id=None,
            reported_status=None,
            verified_status=None,
            action="skip",
            reason=reason,
            dirty=False,
            bytes=size,
        )
    return _item(path, attempt, "skip", reason, size=size)


def _delete_worktree_item(
    item: CleanupItem, attempt: AttemptRecord | None, workspaces_root: Path
) -> CleanupItem:
    # Delete-time containment recheck: between evaluation and deletion the path
    # could have been swapped for a symlink or moved outside workspaces_root.
    # Re-verify against item.path (the evaluated path) before any destructive op.
    target = Path(item.path)
    if target.is_symlink() or not path_is_inside(target, workspaces_root):
        return _replace_item(item, action="skip", reason="delete-time-unsafe", deleted=False)
    try:
        if attempt is None:
            shutil.rmtree(item.path, ignore_errors=False)
            remove_workspace_lease(item.path)
        else:
            remove_attempt_workspace(attempt.workspace_ref)
    except Exception as exc:
        return _replace_item(item, deleted=False, error=str(exc))
    return _replace_item(item, deleted=True)


def _artifact_candidate_paths(worktree_path: Path, allowlist: tuple[str, ...]) -> tuple[Path, ...]:
    paths = []
    for name in allowlist:
        if "/" in name or name in {"", ".", ".."}:
            continue
        candidate = worktree_path / name
        # Keep the ORIGINAL candidate (not resolved) so symlinks are detected in
        # _evaluate_artifact and deletion targets the link, not its target.
        # is_symlink() also catches broken symlinks that exists() would miss.
        if candidate.is_symlink() or candidate.exists():
            paths.append(candidate)
    return tuple(paths)


def _evaluate_artifact(worktree_path: Path, path: Path, worktree_item: CleanupItem) -> CleanupItem:
    if path.is_symlink():
        # A symlinked artifact is unsafe: it could resolve into another worktree
        # and be sized/deleted as the target. Skip without resolving.
        return _replace_item(
            worktree_item,
            path=str(path),
            kind="artifact",
            action="skip",
            reason="symlink-skip",
            bytes=0,
        )
    if not path_is_inside(path, worktree_path):
        # Containment relative to the OWNING worktree (not just workspaces_root),
        # and BEFORE sizing — never walk a path outside the worktree.
        return _replace_item(
            worktree_item,
            path=str(path),
            kind="artifact",
            action="skip",
            reason="outside-worktree",
            bytes=0,
        )
    return CleanupItem(
        path=str(path),
        kind="artifact",
        attempt_id=worktree_item.attempt_id,
        reported_status=worktree_item.reported_status,
        verified_status=worktree_item.verified_status,
        action="remove",
        reason="allowlisted-artifact",
        dirty=False,
        bytes=_path_size(path),
    )


def _delete_artifact_item(item: CleanupItem) -> CleanupItem:
    try:
        path = Path(item.path)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except Exception as exc:
        return _replace_item(item, deleted=False, error=str(exc))
    return _replace_item(item, deleted=True)


def _replace_item(item: CleanupItem, **changes: object) -> CleanupItem:
    values = {
        "path": item.path,
        "kind": item.kind,
        "attempt_id": item.attempt_id,
        "reported_status": item.reported_status,
        "verified_status": item.verified_status,
        "action": item.action,
        "reason": item.reason,
        "dirty": item.dirty,
        "bytes": item.bytes,
        "deleted": item.deleted,
        "error": item.error,
    }
    values.update(changes)
    return CleanupItem(**values)


def _is_dirty_worktree(path: Path) -> bool:
    if not path.exists():
        return False
    if not _is_git_toplevel(path):
        return False
    output = _git_stdout(path, "status", "--porcelain", "--untracked-files=all", allow_failure=True)
    return bool(output.strip())


def _is_git_toplevel(path: Path) -> bool:
    top = _git_stdout(path, "rev-parse", "--show-toplevel", allow_failure=True)
    return bool(top) and Path(top).resolve() == path.resolve()


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        try:
            total += child.lstat().st_size
        except OSError:
            continue
    return total


def path_is_inside(path: Path, parent: Path) -> bool:
    """Whether resolved ``path`` is within resolved ``parent``.

    Catches resolve()/relative_to filesystem errors (not just ``ValueError``)
    so read-only callers like ``ait status`` never crash on hostile refs.
    """
    try:
        path.resolve().relative_to(parent.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True


def _path_is_inside(path: Path, parent: Path) -> bool:
    return path_is_inside(path, parent)


def safe_resolve_workspace_ref(workspace_ref: str | Path) -> Path | None:
    """Resolve a DB ``workspace_ref`` without crashing on malformed values.

    Returns the resolved absolute Path, or ``None`` when the ref is relative
    or cannot be resolved (``OSError``/``RuntimeError``/``ValueError``/
    ``TypeError`` — e.g. an embedded null byte). Containment is not checked
    here; callers decide what to do with the result.
    """
    try:
        path = Path(workspace_ref)
        if not path.is_absolute():
            return None
        return path.resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None


def _git(cwd: Path, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise CleanupError(f"git {' '.join(args)} failed: {stderr}")
    return completed


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    completed = _git(cwd, *args, allow_failure=allow_failure)
    if completed.returncode != 0 and allow_failure:
        return ""
    return completed.stdout.strip()
