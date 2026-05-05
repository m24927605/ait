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
from ait.repo import resolve_repo_root
from ait.workspace import get_workspaces_root, remove_attempt_workspace


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

    attempts_by_workspace = {
        str(Path(attempt.workspace_ref).resolve()): attempt for attempt in attempts
    }
    candidate_paths = _workspace_candidate_paths(workspaces_root, attempts)
    items: list[CleanupItem] = []
    removed_any_worktree = False

    if policy.worktrees:
        for path in candidate_paths:
            attempt = attempts_by_workspace.get(str(path.resolve()))
            item = _evaluate_worktree(workspaces_root, path, attempt, policy)
            if policy.apply and item.action == "remove":
                item = _delete_worktree_item(item, attempt)
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
                artifact = _evaluate_artifact(workspaces_root, artifact_path, worktree_item)
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
        scanned_count=len(candidate_paths),
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


def _workspace_candidate_paths(workspaces_root: Path, attempts: tuple[AttemptRecord, ...]) -> tuple[Path, ...]:
    paths: dict[str, Path] = {}
    for attempt in attempts:
        path = Path(attempt.workspace_ref).resolve()
        paths[str(path)] = path
    if workspaces_root.exists():
        for child in workspaces_root.iterdir():
            if child.is_dir() and child.name.startswith("attempt-"):
                paths[str(child.resolve())] = child.resolve()
    return tuple(paths[key] for key in sorted(paths))


def _evaluate_worktree(
    workspaces_root: Path,
    path: Path,
    attempt: AttemptRecord | None,
    policy: CleanupPolicy,
) -> CleanupItem:
    resolved = path.resolve()
    size = _path_size(resolved)
    if not _path_is_inside(resolved, workspaces_root):
        return _item(resolved, attempt, "skip", "outside-ait-root", size=size)
    if attempt is None:
        action = "remove" if policy.include_orphans else "skip"
        return CleanupItem(
            path=str(resolved),
            kind="orphan",
            attempt_id=None,
            reported_status=None,
            verified_status=None,
            action=action,
            reason="unknown-attempt",
            dirty=False,
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


def _terminal_decision(attempt: AttemptRecord, policy: CleanupPolicy) -> tuple[str, str]:
    if attempt.verified_status in {"promoted", "discarded"}:
        return "remove", attempt.verified_status
    if attempt.verified_status == "succeeded":
        return "retain", "reviewable"
    if attempt.verified_status == "failed" or attempt.reported_status == "crashed":
        if _older_than_retention(attempt, policy.older_than_days):
            return "remove", "stale-failed"
        return "retain", "retention-window"
    return "retain", "reviewable"


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


def _delete_worktree_item(item: CleanupItem, attempt: AttemptRecord | None) -> CleanupItem:
    try:
        if attempt is None:
            shutil.rmtree(item.path, ignore_errors=False)
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
        if candidate.exists():
            paths.append(candidate.resolve())
    return tuple(paths)


def _evaluate_artifact(workspaces_root: Path, path: Path, worktree_item: CleanupItem) -> CleanupItem:
    if not _path_is_inside(path, workspaces_root):
        return _replace_item(
            worktree_item,
            path=str(path),
            kind="artifact",
            action="skip",
            reason="outside-ait-root",
            bytes=_path_size(path),
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
    output = _git_stdout(path, "status", "--porcelain", "--untracked-files=all", allow_failure=True)
    return bool(output.strip())


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


def _path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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
