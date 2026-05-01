from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
import uuid

from ait.db import connect_db, insert_memory_retrieval_event, run_migrations, utc_now
from ait.db.repositories import NewMemoryFact, NewMemoryRetrievalEvent, upsert_memory_fact
from ait.memory_policy import (
    EXCLUDED_MARKER,
    MemoryPolicy,
    default_memory_policy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
    transcript_excluded,
)
from ait.redaction import has_redactions, redact_text
from ait.repo import resolve_repo_root
from ait.workspace import commit_message

from .models import (
    AgentMemoryStatus,
    MemoryAttempt,
    MemoryCandidate,
    MemoryHealth,
    MemoryImportResult,
    MemoryLintFix,
    MemoryLintIssue,
    MemoryLintResult,
    MemoryNote,
    MemorySearchResult,
    RelevantMemoryItem,
    RelevantMemoryRecall,
    RepoMemory,
)

from .notes import add_memory_note

AGENT_MEMORY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "claude": (
        "CLAUDE.md",
        ".claude/memory.md",
        ".claude/CLAUDE.md",
    ),
    "codex": (
        "AGENTS.md",
        ".codex/memory.md",
        ".codex/AGENTS.md",
    ),
    "cursor": (
        ".cursor/rules",
        ".cursor/rules.md",
        ".cursorrules",
    ),
}

def import_agent_memory(
    repo_root: str | Path,
    *,
    source: str = "auto",
    paths: tuple[str, ...] = (),
    topic: str = "agent-memory",
    max_chars: int = 6000,
) -> MemoryImportResult:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    source_names = tuple(AGENT_MEMORY_CANDIDATES) if source == "auto" else (source,)
    if source != "auto" and source not in AGENT_MEMORY_CANDIDATES:
        source_names = (source,)
    candidates = _agent_memory_candidates(root, source_names=source_names, paths=paths)
    imported: list[MemoryNote] = []
    skipped: list[dict[str, str]] = []
    existing = _existing_import_bodies(root)
    for source_name, relative_path, path in candidates:
        if relative_path in {item["path"] for item in skipped}:
            continue
        if path_excluded(relative_path, policy):
            skipped.append({"path": relative_path, "source": source_name, "reason": "excluded by memory policy"})
            continue
        if not path.exists():
            skipped.append({"path": relative_path, "source": source_name, "reason": "not found"})
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                child_relative = child.relative_to(root).as_posix()
                if path_excluded(child_relative, policy):
                    skipped.append({"path": child_relative, "source": source_name, "reason": "excluded by memory policy"})
                    continue
                _import_one_agent_memory_file(
                    root,
                    source_name=source_name,
                    relative_path=child_relative,
                    path=child,
                    topic=topic,
                    max_chars=max_chars,
                    existing=existing,
                    imported=imported,
                    skipped=skipped,
                )
            continue
        _import_one_agent_memory_file(
            root,
            source_name=source_name,
            relative_path=relative_path,
            path=path,
            topic=topic,
            max_chars=max_chars,
            existing=existing,
            imported=imported,
            skipped=skipped,
        )
    return MemoryImportResult(imported=tuple(imported), skipped=tuple(skipped))

def ensure_agent_memory_imported(repo_root: str | Path) -> MemoryImportResult:
    root = resolve_repo_root(repo_root)
    state_path = _agent_memory_import_state_path(root)
    signature = _agent_memory_signature(root)
    state = _read_agent_memory_import_state(state_path)
    status = agent_memory_status(root)
    if state.get("signature") == signature and status.initialized and not status.pending_paths:
        return MemoryImportResult(imported=(), skipped=())
    result = import_agent_memory(root)
    _write_agent_memory_import_state(state_path, signature=signature, result=result)
    return result

def agent_memory_status(repo_root: str | Path) -> AgentMemoryStatus:
    root = resolve_repo_root(repo_root)
    candidates = _existing_agent_memory_files(root)
    imported_sources = _existing_agent_memory_sources(root)
    imported_paths = {
        source.split(":", 2)[2]
        for source in imported_sources
        if source.startswith("agent-memory:") and len(source.split(":", 2)) == 3
    }
    candidate_paths = tuple(relative_path for _, relative_path, _ in candidates)
    pending_paths = tuple(path for path in candidate_paths if path not in imported_paths)
    return AgentMemoryStatus(
        initialized=bool(imported_sources) or not candidate_paths,
        imported_sources=imported_sources,
        candidate_paths=candidate_paths,
        pending_paths=pending_paths,
        state_path=str(_agent_memory_import_state_path(root)),
    )

def _existing_agent_memory_sources(root: Path) -> tuple[str, ...]:
    db_path = root / ".ait" / "state.sqlite3"
    if not db_path.exists():
        return ()
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        rows = conn.execute(
            """
            SELECT source
            FROM memory_notes
            WHERE active = 1 AND topic = 'agent-memory' AND source LIKE 'agent-memory:%'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        return tuple(str(row["source"]) for row in rows)
    finally:
        conn.close()

def _agent_memory_import_state_path(root: Path) -> Path:
    return root / ".ait" / "memory" / "agent-import-state.json"

def _agent_memory_signature(root: Path) -> list[dict[str, object]]:
    signature: list[dict[str, object]] = []
    for source_name, relative_path, path in _existing_agent_memory_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append(
            {
                "source": source_name,
                "path": relative_path,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
        )
    return signature

def _existing_agent_memory_files(root: Path) -> tuple[tuple[str, str, Path], ...]:
    policy = load_memory_policy(root)
    files: list[tuple[str, str, Path]] = []
    seen: set[str] = set()
    candidates = _agent_memory_candidates(
        root,
        source_names=tuple(AGENT_MEMORY_CANDIDATES),
        paths=(),
    )
    for source_name, relative_path, path in candidates:
        if not path.exists():
            continue
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                child_relative = child.relative_to(root).as_posix()
                if child_relative in seen or path_excluded(child_relative, policy):
                    continue
                files.append((source_name, child_relative, child))
                seen.add(child_relative)
            continue
        if relative_path in seen or path_excluded(relative_path, policy):
            continue
        files.append((source_name, relative_path, path))
        seen.add(relative_path)
    return tuple(files)

def _read_agent_memory_import_state(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def _write_agent_memory_import_state(
    path: Path,
    *,
    signature: list[dict[str, object]],
    result: MemoryImportResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "signature": signature,
                "last_result": result.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

def _agent_memory_candidates(
    root: Path,
    *,
    source_names: tuple[str, ...],
    paths: tuple[str, ...],
) -> tuple[tuple[str, str, Path], ...]:
    candidates: list[tuple[str, str, Path]] = []
    if paths:
        source_name = source_names[0] if len(source_names) == 1 else "custom"
        for raw_path in paths:
            path = Path(raw_path)
            resolved = path if path.is_absolute() else root / path
            relative = _relative_to_root(resolved, root)
            candidates.append((source_name, relative, resolved))
        return tuple(candidates)
    for source_name in source_names:
        for pattern in AGENT_MEMORY_CANDIDATES.get(source_name, ()):
            path = root / pattern
            candidates.append((source_name, pattern, path))
    return tuple(candidates)

def _import_one_agent_memory_file(
    root: Path,
    *,
    source_name: str,
    relative_path: str,
    path: Path,
    topic: str,
    max_chars: int,
    existing: set[str],
    imported: list[MemoryNote],
    skipped: list[dict[str, str]],
) -> None:
    if not _looks_like_memory_text_file(path):
        skipped.append({"path": relative_path, "source": source_name, "reason": "unsupported file type"})
        return
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        skipped.append({"path": relative_path, "source": source_name, "reason": str(exc)})
        return
    body = _agent_memory_note_body(
        source_name=source_name,
        relative_path=relative_path,
        text=raw,
        max_chars=max_chars,
    )
    if not body.strip():
        skipped.append({"path": relative_path, "source": source_name, "reason": "empty"})
        return
    if body in existing:
        skipped.append({"path": relative_path, "source": source_name, "reason": "already imported"})
        return
    note = add_memory_note(
        root,
        topic=topic,
        body=body,
        source=f"agent-memory:{source_name}:{relative_path}",
    )
    existing.add(body)
    imported.append(note)

def _agent_memory_note_body(
    *,
    source_name: str,
    relative_path: str,
    text: str,
    max_chars: int,
) -> str:
    redacted, _ = redact_text(text)
    compacted = redacted.strip()
    if max_chars > 0 and len(compacted) > max_chars:
        compacted = compacted[:max_chars].rstrip() + "\n[ait memory import compacted]"
    if not compacted:
        return ""
    return (
        f"Imported agent memory\n"
        f"source={source_name}\n"
        f"path={relative_path}\n"
        f"confidence=advisory\n\n"
        f"{compacted}"
    )

def _existing_import_bodies(repo_root: Path) -> set[str]:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        rows = conn.execute(
            """
            SELECT body
            FROM memory_notes
            WHERE active = 1 AND source LIKE 'agent-memory:%'
            """
        ).fetchall()
        return {str(row["body"]) for row in rows}
    finally:
        conn.close()

def _looks_like_memory_text_file(path: Path) -> bool:
    if path.name in {"AGENTS.md", "CLAUDE.md", ".cursorrules"}:
        return True
    return path.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}

def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
