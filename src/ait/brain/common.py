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

def _compact_line(text: str, *, limit: int = 180) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."

def _terms(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9_./:-]+", text.lower()))

def _safe_node_fragment(value: str) -> str:
    compacted = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    return compacted or "general"
