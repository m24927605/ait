from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time
import uuid

from ait.memory_policy import (
    MemoryPolicy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
)
from ait.redaction import redact_text
from ait.repo import resolve_repo_root

from .common import _compact_line, _literal_snippet, _normalize_search_text, _terms
from .importers import AGENT_MEMORY_CANDIDATES
from .models import LiveMemorySource, MemorySearchResult, RelevantMemoryRecall


LIVE_MEMORY_MAX_SOURCE_BYTES = 256 * 1024
LIVE_MEMORY_DEFAULT_READ_CHARS = 6000
LIVE_MEMORY_DIR_FILE_LIMIT = 128


def discover_live_memory_sources(
    repo_root: str | Path,
    *,
    source: str = "auto",
    paths: tuple[str, ...] = (),
    include_docs: bool = False,
    include_global: bool = False,
    policy: MemoryPolicy | None = None,
) -> tuple[LiveMemorySource, ...]:
    root = resolve_repo_root(repo_root)
    resolved_policy = policy or load_memory_policy(root)
    source_names = tuple(AGENT_MEMORY_CANDIDATES) if source == "auto" else (source,)
    candidates = _candidate_paths(
        root,
        source_names=source_names,
        paths=paths,
        include_docs=include_docs,
    )
    sources: list[LiveMemorySource] = []
    seen: set[str] = set()
    for source_name, candidate_path in candidates:
        sources.extend(
            _sources_for_candidate(
                root=root,
                source_name=source_name,
                candidate_path=candidate_path,
                include_global=include_global,
                policy=resolved_policy,
                seen=seen,
            )
        )
    return tuple(sources)


def search_live_memory_sources(
    repo_root: str | Path,
    query: str,
    *,
    source: str = "auto",
    paths: tuple[str, ...] = (),
    include_docs: bool = False,
    include_global: bool = False,
    limit: int = 8,
    max_chars: int = LIVE_MEMORY_DEFAULT_READ_CHARS,
    policy: MemoryPolicy | None = None,
    include_unmatched: bool = False,
) -> tuple[tuple[MemorySearchResult, ...], tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    root = resolve_repo_root(repo_root)
    resolved_policy = policy or load_memory_policy(root)
    sources = discover_live_memory_sources(
        root,
        source=source,
        paths=paths,
        include_docs=include_docs,
        include_global=include_global,
        policy=resolved_policy,
    )
    normalized_query = _normalize_search_text(query)
    query_terms = _terms(query)
    results: list[MemorySearchResult] = []
    manifest: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for source_item in sources:
        if not source_item.allowed_by_policy or not source_item.exists:
            manifest.append(source_item.to_dict())
            if source_item.skip_reason:
                skipped.append(
                    {
                        "kind": "live_source",
                        "id": source_item.source_id,
                        "source": source_item.source_id,
                        "reason": source_item.skip_reason,
                        "path": source_item.path,
                    }
                )
            continue
        text, redacted, bytes_used = read_live_memory_source(source_item, max_chars=max_chars)
        used_source = replace(source_item, bytes_used=bytes_used, redacted=redacted)
        manifest.append(used_source.to_dict())
        score = _score_live_text(
            title=used_source.path,
            text=text,
            normalized_query=normalized_query,
            query_terms=query_terms,
        )
        if score <= 0:
            if include_unmatched:
                score = 0.05
            else:
                skipped.append(
                    {
                        "kind": "live_source",
                        "id": used_source.source_id,
                        "source": used_source.source_id,
                        "reason": "query did not match live source",
                        "path": used_source.path,
                    }
                )
                continue
        metadata = {
            "source": used_source.source_id,
            "source_id": used_source.source_id,
            "source_kind": used_source.kind,
            "agent": used_source.source,
            "scope": used_source.scope,
            "path": used_source.path,
            "absolute_path": used_source.absolute_path,
            "sha256": used_source.sha256 or "",
            "mtime": used_source.mtime,
            "size_bytes": used_source.size_bytes,
            "bytes_used": bytes_used,
            "policy_status": used_source.policy_status,
            "policy_reason": used_source.policy_reason,
            "authority": used_source.authority,
            "source_of_truth": used_source.source_of_truth,
            "redacted": redacted,
            "ranker": "live-lexical-v1",
        }
        if normalized_query and normalized_query in _normalize_search_text(text):
            metadata["snippet"] = _literal_snippet(text, normalized_query)
        results.append(
            MemorySearchResult(
                kind="live_source",
                id=used_source.source_id,
                score=score,
                title=used_source.path,
                text=_compact_line(text),
                metadata=metadata,
            )
        )
    results.sort(key=lambda item: (-item.score, item.id))
    selected_ids = {item.id for item in results[:limit]}
    finalized_manifest = tuple(
        {
            **item,
            "selected": item.get("source_id") in selected_ids,
        }
        for item in manifest
    )
    return tuple(results[:limit]), finalized_manifest, tuple(skipped)


def read_live_memory_source(source: LiveMemorySource, *, max_chars: int = LIVE_MEMORY_DEFAULT_READ_CHARS) -> tuple[str, bool, int]:
    path = Path(source.absolute_path)
    try:
        raw = path.read_bytes()[:LIVE_MEMORY_MAX_SOURCE_BYTES]
    except OSError:
        return "", False, 0
    text = raw.decode("utf-8", errors="replace")[:max_chars]
    redacted, changed = redact_text(text)
    return redacted, changed, len(raw)


def write_recall_record(
    repo_root: str | Path,
    recall: RelevantMemoryRecall,
    *,
    query_sources: object = None,
) -> str:
    root = resolve_repo_root(repo_root)
    record_ref = f".ait/memory-retrievals/manual-{int(time.time())}-{uuid.uuid4().hex[:8]}.json"
    payload = {
        "schema_version": 1,
        "kind": "manual_memory_recall",
        "query": recall.query,
        "query_sources": query_sources,
        "selected": [item.to_dict() for item in recall.selected],
        "skipped": list(recall.skipped),
        "source_manifest": list(recall.source_manifest),
        "created_at_unix": time.time(),
    }
    path = root / record_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record_ref


def write_context_manifest(
    repo_root: str | Path,
    *,
    owner_kind: str,
    owner_id: str,
    context_ref: str,
    recall: RelevantMemoryRecall,
    context_text: str = "",
) -> str:
    from ait.context_manifest import write_context_manifest as _write_context_manifest

    return _write_context_manifest(
        repo_root,
        owner_kind=owner_kind,
        owner_id=owner_id,
        context_ref=context_ref,
        recall=recall,
        context_text=context_text,
    )


def _candidate_paths(
    root: Path,
    *,
    source_names: tuple[str, ...],
    paths: tuple[str, ...],
    include_docs: bool,
) -> tuple[tuple[str, Path], ...]:
    candidates: list[tuple[str, Path]] = []
    if paths:
        source_name = source_names[0] if len(source_names) == 1 else "custom"
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            candidates.append((source_name, path if path.is_absolute() else root / path))
    else:
        for source_name in source_names:
            for pattern in AGENT_MEMORY_CANDIDATES.get(source_name, ()):
                candidates.append((source_name, root / pattern))
    if include_docs:
        docs = [root / "README.md"]
        docs.extend(sorted((root / "docs").glob("**/*.md")) if (root / "docs").exists() else [])
        candidates.extend(("docs", path) for path in docs)
    return tuple(candidates)


def _sources_for_candidate(
    *,
    root: Path,
    source_name: str,
    candidate_path: Path,
    include_global: bool,
    policy: MemoryPolicy,
    seen: set[str],
) -> tuple[LiveMemorySource, ...]:
    path = candidate_path
    outside_repo = not _is_relative_to(path.resolve(strict=False), root)
    if outside_repo and not include_global:
        return (
            _source_for_path(
                root=root,
                source_name=source_name,
                path=path,
                policy=policy,
                exists=path.exists(),
                allowed=False,
                policy_reason="outside repo",
                skip_reason="outside repo; rerun with --global --path to inspect explicit paths",
                scope="global",
            ),
        )
    if not path.exists():
        return ()
    if path.is_symlink() and not include_global and outside_repo:
        return (
            _source_for_path(
                root=root,
                source_name=source_name,
                path=path,
                policy=policy,
                exists=True,
                allowed=False,
                policy_reason="unsafe symlink outside repo",
                skip_reason="unsafe symlink outside repo",
                scope="repo",
            ),
        )
    paths = _iter_source_files(path)
    sources: list[LiveMemorySource] = []
    for child in paths:
        absolute = child.resolve(strict=False)
        key = absolute.as_posix()
        if key in seen:
            continue
        seen.add(key)
        outside_child = not _is_relative_to(absolute, root)
        if outside_child and not include_global:
            sources.append(
                _source_for_path(
                    root=root,
                    source_name=source_name,
                    path=child,
                    policy=policy,
                    exists=True,
                    allowed=False,
                    policy_reason="unsafe symlink outside repo",
                    skip_reason="unsafe symlink outside repo",
                    scope="repo",
                )
            )
            continue
        relative_path = _relative_to_root(child, root)
        if path_excluded(relative_path, policy):
            sources.append(
                _source_for_path(
                    root=root,
                    source_name=source_name,
                    path=child,
                    policy=policy,
                    exists=True,
                    allowed=False,
                    policy_reason="excluded by memory policy",
                    skip_reason="excluded by memory policy",
                    scope="global" if outside_child else "repo",
                )
            )
            continue
        logical_source = _source_id(source_name, relative_path, outside=outside_child)
        policy_source = logical_source.replace("live:", "live-memory:", 1)
        if recall_source_blocked(logical_source, policy) or recall_source_blocked(policy_source, policy):
            sources.append(
                _source_for_path(
                    root=root,
                    source_name=source_name,
                    path=child,
                    policy=policy,
                    exists=True,
                    allowed=False,
                    policy_reason="source blocked by memory policy",
                    skip_reason="source blocked by memory policy",
                    scope="global" if outside_child else "repo",
                )
            )
            continue
        if not recall_source_allowed(policy_source, policy):
            sources.append(
                _source_for_path(
                    root=root,
                    source_name=source_name,
                    path=child,
                    policy=policy,
                    exists=True,
                    allowed=False,
                    policy_reason="source not allowed by memory policy",
                    skip_reason="source not allowed by memory policy",
                    scope="global" if outside_child else "repo",
                )
            )
            continue
        sources.append(
            _source_for_path(
                root=root,
                source_name=source_name,
                path=child,
                policy=policy,
                exists=True,
                allowed=True,
                policy_reason="allowed",
                skip_reason="",
                scope="global" if outside_child else "repo",
            )
        )
    return tuple(sources)


def _iter_source_files(path: Path) -> tuple[Path, ...]:
    if path.is_file() or path.is_symlink():
        return (path,)
    if not path.is_dir():
        return ()
    files = [item for item in path.rglob("*") if item.is_file() or item.is_symlink()]
    return tuple(sorted(files)[:LIVE_MEMORY_DIR_FILE_LIMIT])


def _source_for_path(
    *,
    root: Path,
    source_name: str,
    path: Path,
    policy: MemoryPolicy,
    exists: bool,
    allowed: bool,
    policy_reason: str,
    skip_reason: str,
    scope: str,
) -> LiveMemorySource:
    del policy
    relative_path = _relative_to_root(path, root)
    stat_path = path
    size: int | None = None
    mtime: float | None = None
    digest: str | None = None
    if exists and path.is_file():
        try:
            stat = stat_path.stat()
            size = stat.st_size
            mtime = stat.st_mtime
            digest = _sha256_file(path)
        except OSError:
            allowed = False
            policy_reason = "unreadable"
            skip_reason = "unreadable"
    return LiveMemorySource(
        source_id=_source_id(source_name, relative_path, outside=scope == "global"),
        source=source_name,
        kind="agent_memory" if source_name != "docs" else "repo_doc",
        scope=scope,
        path=relative_path,
        absolute_path=path.resolve(strict=False).as_posix(),
        exists=exists,
        allowed_by_policy=allowed,
        policy_status="allowed" if allowed else "blocked",
        policy_reason=policy_reason,
        skip_reason=skip_reason,
        sha256=digest,
        mtime=mtime,
        size_bytes=size,
    )


def _source_id(source_name: str, path: str, *, outside: bool) -> str:
    normalized = path.replace("\\", "/")
    if outside:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
        return f"live:{source_name}:global:{digest}"
    return f"live:{source_name}:{normalized}"


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.expanduser().resolve(strict=False).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score_live_text(
    *,
    title: str,
    text: str,
    normalized_query: str,
    query_terms: tuple[str, ...],
) -> float:
    haystack = f"{title} {text}"
    normalized_haystack = _normalize_search_text(haystack)
    if normalized_query and normalized_query in normalized_haystack:
        return 12.0 + min(5.0, len(normalized_query) / 8.0)
    if not query_terms:
        return 0.0
    haystack_terms = _terms(haystack)
    if not haystack_terms:
        return 0.0
    score = 0.0
    term_counts = {term: haystack_terms.count(term) for term in set(haystack_terms)}
    for term in query_terms:
        count = term_counts.get(term, 0)
        if count:
            score += 2.0 + count
        elif len(term) >= 3 and any(candidate.startswith(term) or term.startswith(candidate) for candidate in term_counts):
            score += 0.75
    return score


__all__ = [
    "discover_live_memory_sources",
    "read_live_memory_source",
    "search_live_memory_sources",
    "write_context_manifest",
    "write_recall_record",
]
