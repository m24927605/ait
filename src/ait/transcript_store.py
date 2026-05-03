"""Repo-local transcript storage and retention.

Agent transcripts captured by hooks (Claude Code today, others later)
land under ``.ait/transcripts/``. This module owns the directory layout
and the retention policy that prevents unbounded growth.

The pruner is filesystem-only; it does not touch the SQLite state. It
applies two rules from the memory policy in order:

1. Age — delete files whose mtime is older than ``retain_days``.
2. Total size — if the remaining files exceed ``max_total_bytes``,
   delete oldest first until the cap is met.

A zero or negative limit disables that rule.
"""

from __future__ import annotations

import time
from pathlib import Path

from ait.memory_policy import MemoryPolicy


SECONDS_PER_DAY = 86400


def transcripts_dir(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / ".ait" / "transcripts"


def prune_transcripts(
    repo_root: str | Path,
    *,
    policy: MemoryPolicy,
    now: float | None = None,
) -> tuple[str, ...]:
    """Apply the policy to ``.ait/transcripts/``; return deleted paths.

    Deleted paths are repo-relative POSIX strings. Missing directory is
    a no-op. Failures to delete an individual file are swallowed so one
    permission error does not stop the rest of the sweep.
    """
    root = Path(repo_root).resolve()
    base = root / ".ait" / "transcripts"
    if not base.exists():
        return ()
    current = now if now is not None else time.time()

    files: list[tuple[Path, float, int]] = []
    for entry in base.iterdir():
        if not entry.is_file():
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        files.append((entry, stat.st_mtime, stat.st_size))

    deleted: list[str] = []

    if policy.transcript_retain_days > 0:
        cutoff = current - policy.transcript_retain_days * SECONDS_PER_DAY
        for entry, mtime, _ in list(files):
            if mtime < cutoff:
                _remove(entry, root, deleted)
        files = [item for item in files if item[0].exists()]

    if policy.transcript_max_total_bytes > 0:
        total = sum(size for _, _, size in files)
        if total > policy.transcript_max_total_bytes:
            files.sort(key=lambda item: item[1])  # oldest first
            for entry, _, size in files:
                if total <= policy.transcript_max_total_bytes:
                    break
                if _remove(entry, root, deleted):
                    total -= size

    return tuple(deleted)


def _remove(path: Path, repo_root: Path, deleted: list[str]) -> bool:
    try:
        path.unlink()
    except OSError:
        return False
    deleted.append(path.relative_to(repo_root).as_posix())
    return True
