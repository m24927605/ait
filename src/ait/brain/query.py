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

from .common import _compact_line, _safe_node_fragment, _terms
from .graph import _append_source, build_repo_brain, build_repo_brain_with_connection, write_repo_brain
from .setup import _ensure_brain_repo

def query_repo_brain(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 8,
) -> tuple[BrainQueryResult, ...]:
    brain = build_repo_brain(repo_root)
    return query_repo_brain_graph(brain, query, limit=limit)

def build_repo_brain_briefing(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 6,
) -> RepoBrainBriefing:
    brain = write_repo_brain(repo_root)
    return build_repo_brain_briefing_from_graph(brain, query, limit=limit)

def build_auto_repo_brain_briefing(
    repo_root: str | Path,
    *,
    intent_title: str | None = None,
    description: str | None = None,
    kind: str | None = None,
    command: tuple[str, ...] = (),
    agent_id: str | None = None,
    limit: int = 6,
) -> RepoBrainBriefing:
    auto_query = build_auto_briefing_query(
        repo_root,
        intent_title=intent_title,
        description=description,
        kind=kind,
        command=command,
        agent_id=agent_id,
    )
    brain = write_repo_brain(repo_root)
    return build_repo_brain_briefing_from_graph(
        brain,
        auto_query.query,
        limit=limit,
        sources=auto_query.sources,
    )

def build_auto_briefing_query(
    repo_root: str | Path,
    *,
    intent_title: str | None = None,
    description: str | None = None,
    kind: str | None = None,
    command: tuple[str, ...] = (),
    agent_id: str | None = None,
) -> AutoBriefingQuery:
    root, db_path = _ensure_brain_repo(repo_root)
    policy = load_memory_policy(root)
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        sources: list[BriefingQuerySource] = []
        _append_source(sources, "intent_title", intent_title)
        _append_source(sources, "intent_description", description)
        _append_source(sources, "intent_kind", kind)
        _append_source(sources, "agent", agent_id)
        if command:
            _append_source(sources, "command_args", " ".join(command))
        for title in _recent_failed_attempt_titles(conn, limit=3):
            _append_source(sources, "recent_failed_attempt", title)
        for file_path in _hot_file_paths(conn, policy=policy, limit=5):
            _append_source(sources, "hot_file", file_path)
        for topic in _memory_note_topics(conn, limit=5):
            _append_source(sources, "memory_topic", topic)
    finally:
        conn.close()
    query = _compact_query(" ".join(source.value for source in sources))
    if not query:
        query = Path(root).name
        sources = [BriefingQuerySource("repo", query)]
    return AutoBriefingQuery(query=query, sources=tuple(sources))

def build_repo_brain_briefing_from_graph(
    brain: RepoBrain,
    query: str,
    *,
    limit: int = 6,
    sources: tuple[BriefingQuerySource, ...] = (),
) -> RepoBrainBriefing:
    return RepoBrainBriefing(
        query=query,
        generated_at=brain.generated_at,
        results=query_repo_brain_graph(brain, query, limit=limit),
        sources=sources,
    )

def query_repo_brain_graph(
    brain: RepoBrain,
    query: str,
    *,
    limit: int = 8,
) -> tuple[BrainQueryResult, ...]:
    if limit < 0:
        raise ValueError("repo brain query limit must be non-negative")
    terms = _terms(query)
    if not terms:
        return ()
    node_by_id = {node.id: node for node in brain.nodes}
    results: list[BrainQueryResult] = []
    for node in brain.nodes:
        score = _score_node(node, terms)
        if score <= 0:
            continue
        connected_edges = tuple(edge for edge in brain.edges if edge.source == node.id or edge.target == node.id)
        neighbor_ids = {
            edge.target if edge.source == node.id else edge.source
            for edge in connected_edges
        }
        neighbors = tuple(sorted((node_by_id[node_id] for node_id in neighbor_ids), key=lambda item: item.id))
        results.append(
            BrainQueryResult(
                node=node,
                score=score,
                neighbors=neighbors,
                edges=connected_edges,
            )
        )
    results.sort(key=lambda result: (-result.score, result.node.kind, result.node.id))
    return tuple(results[:limit])

def _recent_failed_attempt_titles(conn: sqlite3.Connection, *, limit: int) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT i.title
        FROM attempts AS a
        JOIN intents AS i ON i.id = a.intent_id
        WHERE a.verified_status = 'failed'
        ORDER BY a.started_at DESC, a.ordinal DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return tuple(str(row["title"]) for row in rows)

def _hot_file_paths(conn: sqlite3.Connection, *, policy: MemoryPolicy, limit: int) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path, COUNT(*) AS touch_count
        FROM evidence_files
        WHERE kind IN ('changed', 'touched')
        GROUP BY file_path
        ORDER BY touch_count DESC, file_path ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))

def _memory_note_topics(conn: sqlite3.Connection, *, limit: int) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT DISTINCT topic
        FROM memory_notes
        WHERE active = 1 AND topic IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return tuple(str(row["topic"]) for row in rows if row["topic"] is not None)

def _score_node(node: BrainNode, query_terms: tuple[str, ...]) -> float:
    haystack = _terms(" ".join([node.kind, node.title, node.text, " ".join(str(v) for v in node.metadata.values())]))
    if not haystack:
        return 0.0
    counts = {term: haystack.count(term) for term in set(haystack)}
    score = 0.0
    for term in query_terms:
        if term in counts:
            score += 2.0 + counts[term]
        elif any(candidate.startswith(term) or term.startswith(candidate) for candidate in counts):
            score += 0.75
    return score

def _compact_query(text: str, *, limit: int = 1200) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[:limit].rstrip()
