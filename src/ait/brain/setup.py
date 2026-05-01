from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3
import subprocess

from ait.config import bootstrap_ait_dir, ensure_ait_ignored, ensure_local_config, ensure_repo_identity
from ait.db import connect_db, run_migrations, utc_now
from ait.hooks import install_post_rewrite_hook
from ait.memory_policy import EXCLUDED_MARKER, MemoryPolicy, load_memory_policy, path_excluded, transcript_excluded
from ait.redaction import redact_text
from ait.repo import compose_repo_id, derive_repo_identity, ensure_initial_commit, resolve_repo_root

from .models import (
    AutoBriefingQuery,
    BrainEdge,
    BrainNode,
    BrainQueryResult,
    BriefingQuerySource,
    RepoBrain,
    RepoBrainBriefing,
)

def _ensure_brain_repo(repo_root: str | Path) -> tuple[Path, Path]:
    root = resolve_repo_root(repo_root)
    ait_dir = bootstrap_ait_dir(root)
    config = ensure_local_config(root)
    ensure_ait_ignored(root)
    ensure_initial_commit(root)
    if not config.repo_identity:
        config = ensure_repo_identity(root, derive_repo_identity(root))
    db_path = ait_dir / "state.sqlite3"
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()
    install_post_rewrite_hook(root)
    # Keep repo identity composition exercised here so this helper preserves
    # init-time validation without exposing another public result type.
    compose_repo_id(str(config.repo_identity), config.install_nonce)
    return root, db_path
