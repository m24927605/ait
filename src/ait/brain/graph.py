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

from .common import _compact_line, _safe_node_fragment
from .render import render_repo_brain_text
from .setup import _ensure_brain_repo

def build_repo_brain(repo_root: str | Path) -> RepoBrain:
    root, db_path = _ensure_brain_repo(repo_root)
    policy = load_memory_policy(root)
    conn = connect_db(db_path)
    try:
        run_migrations(conn)
        return build_repo_brain_with_connection(conn, repo_root=root, policy=policy)
    finally:
        conn.close()

def build_repo_brain_with_connection(
    conn: sqlite3.Connection,
    *,
    repo_root: str | Path,
    policy: MemoryPolicy | None = None,
) -> RepoBrain:
    root = Path(repo_root).resolve()
    resolved_policy = policy or load_memory_policy(root)
    nodes: dict[str, BrainNode] = {}
    edges: dict[tuple[str, str, str], BrainEdge] = {}

    repo_id = "repo:root"
    _add_node(
        nodes,
        BrainNode(
            id=repo_id,
            kind="repo",
            title=root.name,
            text=str(root),
            confidence="extracted",
            metadata={"path": str(root)},
        ),
    )

    _add_doc_nodes(root, policy=resolved_policy, nodes=nodes, edges=edges, repo_id=repo_id)
    _add_note_nodes(conn, nodes=nodes, edges=edges, repo_id=repo_id)
    _add_attempt_nodes(conn, repo_root=root, policy=resolved_policy, nodes=nodes, edges=edges, repo_id=repo_id)

    return RepoBrain(
        repo_root=str(root),
        generated_at=utc_now(),
        nodes=tuple(sorted(nodes.values(), key=lambda node: (node.kind, node.id))),
        edges=tuple(sorted(edges.values(), key=lambda edge: (edge.source, edge.kind, edge.target))),
    )

def write_repo_brain(repo_root: str | Path) -> RepoBrain:
    root, _ = _ensure_brain_repo(repo_root)
    brain = build_repo_brain(root)
    brain_dir = root / ".ait" / "brain"
    brain_dir.mkdir(parents=True, exist_ok=True)
    graph_path = brain_dir / "graph.json"
    existing = _load_existing_graph(graph_path)
    if existing and _same_graph(existing, brain.to_dict()):
        brain = RepoBrain(
            repo_root=brain.repo_root,
            generated_at=str(existing.get("generated_at", brain.generated_at)),
            nodes=brain.nodes,
            edges=brain.edges,
        )
    graph_path.write_text(
        json.dumps(brain.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (brain_dir / "REPORT.md").write_text(render_repo_brain_text(brain), encoding="utf-8")
    return brain

def _load_existing_graph(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None

def _same_graph(left: dict[str, object], right: dict[str, object]) -> bool:
    comparable_left = {key: value for key, value in left.items() if key != "generated_at"}
    comparable_right = {key: value for key, value in right.items() if key != "generated_at"}
    return comparable_left == comparable_right

def _add_doc_nodes(
    root: Path,
    *,
    policy: MemoryPolicy,
    nodes: dict[str, BrainNode],
    edges: dict[tuple[str, str, str], BrainEdge],
    repo_id: str,
) -> None:
    for relative in _tracked_markdown_paths(root):
        if path_excluded(relative, policy):
            continue
        path = root / relative
        text = _read_text_head(path, limit=1400)
        if not text:
            continue
        if transcript_excluded(text, policy):
            continue
        summary, redacted = redact_text(_doc_summary(text))
        node_id = f"doc:{relative}"
        _add_node(
            nodes,
            BrainNode(
                id=node_id,
                kind="doc",
                title=relative,
                text=summary,
                confidence="extracted",
                metadata={"path": relative, "redacted": redacted},
            ),
        )
        _add_edge(edges, BrainEdge(repo_id, node_id, "has_doc", "extracted", {}))

def _add_note_nodes(
    conn: sqlite3.Connection,
    *,
    nodes: dict[str, BrainNode],
    edges: dict[tuple[str, str, str], BrainEdge],
    repo_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT id, topic, body, source, updated_at
        FROM memory_notes
        WHERE active = 1
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()
    for row in rows:
        note_id = str(row["id"])
        topic_raw = str(row["topic"]) if row["topic"] is not None else "general"
        topic, topic_redacted = redact_text(topic_raw)
        source, source_redacted = redact_text(str(row["source"]))
        body, redacted = redact_text(str(row["body"]))
        if _advisory_attempt_memory_note(source, body):
            continue
        topic_id = f"topic:{_safe_node_fragment(topic)}"
        _add_node(
            nodes,
            BrainNode(
                id=note_id,
                kind="note",
                title=topic,
                text=body,
                confidence="extracted",
                metadata={
                    "source": source,
                    "updated_at": str(row["updated_at"]),
                    "redacted": redacted or topic_redacted or source_redacted,
                },
            ),
        )
        _add_node(
            nodes,
            BrainNode(
                id=topic_id,
                kind="topic",
                title=topic,
                text="",
                confidence="inferred",
                metadata={},
            ),
        )
        _add_edge(edges, BrainEdge(repo_id, note_id, "has_note", "extracted", {}))
        _add_edge(edges, BrainEdge(note_id, topic_id, "about_topic", "inferred", {}))

def _add_attempt_nodes(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    policy: MemoryPolicy,
    nodes: dict[str, BrainNode],
    edges: dict[tuple[str, str, str], BrainEdge],
    repo_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT
          a.id AS attempt_id,
          a.agent_id,
          a.verified_status,
          a.result_exit_code,
          a.raw_trace_ref,
          a.started_at,
          i.id AS intent_id,
          i.title AS intent_title,
          i.description AS intent_description,
          i.kind AS intent_kind
        FROM attempts AS a
        JOIN intents AS i ON i.id = a.intent_id
        ORDER BY a.started_at DESC, a.ordinal DESC
        """
    ).fetchall()
    for row in rows:
        intent_id = f"intent:{row['intent_id']}"
        attempt_id = f"attempt:{row['attempt_id']}"
        agent_id = f"agent:{row['agent_id']}"
        changed_files = _changed_files(conn, str(row["attempt_id"]), policy=policy)
        commit_oids = _commit_oids(conn, str(row["attempt_id"]))
        status = str(row["verified_status"])
        intent_title, title_redacted = redact_text(str(row["intent_title"]))
        intent_description, description_redacted = redact_text(str(row["intent_description"] or ""))
        intent_kind, kind_redacted = redact_text(str(row["intent_kind"] or ""))
        agent_title, agent_redacted = redact_text(str(row["agent_id"]))
        if transcript_excluded(" ".join([intent_title, intent_description, intent_kind, agent_title]), policy):
            intent_title = EXCLUDED_MARKER
            intent_description = ""
            intent_kind = ""
            agent_title = EXCLUDED_MARKER
        _add_node(
            nodes,
            BrainNode(
                id=intent_id,
                kind="intent",
                title=intent_title,
                text=" ".join(
                    part
                    for part in (
                        intent_description,
                        intent_kind,
                    )
                    if part
                ),
                confidence="extracted",
                metadata={
                    "intent_id": str(row["intent_id"]),
                    "redacted": title_redacted or description_redacted or kind_redacted,
                },
            ),
        )
        _add_node(
            nodes,
            BrainNode(
                id=attempt_id,
                kind="attempt",
                title=intent_title,
                text=(
                    f"status={status} agent={agent_title} "
                    f"changed={' '.join(changed_files)} commits={' '.join(commit_oids)}"
                ),
                confidence="extracted",
                metadata={
                    "attempt_id": str(row["attempt_id"]),
                    "agent_id": agent_title,
                    "verified_status": status,
                    "result_exit_code": row["result_exit_code"],
                    "started_at": str(row["started_at"]),
                    "changed_files": list(changed_files),
                    "commit_oids": list(commit_oids),
                    "redacted": title_redacted or description_redacted or kind_redacted or agent_redacted,
                },
            ),
        )
        _add_node(
            nodes,
            BrainNode(
                id=agent_id,
                kind="agent",
                title=agent_title,
                text="",
                confidence="extracted",
                metadata={"redacted": agent_redacted},
            ),
        )
        _add_edge(edges, BrainEdge(repo_id, intent_id, "has_intent", "extracted", {}))
        _add_edge(edges, BrainEdge(intent_id, attempt_id, "has_attempt", "extracted", {"verified_status": status}))
        _add_edge(edges, BrainEdge(attempt_id, agent_id, "run_by", "extracted", {}))
        raw_trace_ref = str(row["raw_trace_ref"] or "")
        trace_text = _read_trace_text(raw_trace_ref, repo_root=repo_root)
        if trace_text and not transcript_excluded(trace_text, policy):
            trace_text, trace_redacted = redact_text(trace_text)
            trace_text = _compact_line(trace_text, limit=400)
            trace_id = f"trace:{row['attempt_id']}"
            _add_node(
                nodes,
                BrainNode(
                    id=trace_id,
                    kind="trace",
                    title=str(row["attempt_id"]),
                    text=trace_text,
                    confidence="extracted",
                    metadata={
                        "attempt_id": str(row["attempt_id"]),
                        "raw_trace_ref": raw_trace_ref,
                        "redacted": trace_redacted,
                    },
                ),
            )
            _add_edge(edges, BrainEdge(attempt_id, trace_id, "has_trace", "extracted", {}))
        for file_path in changed_files:
            file_id = f"file:{file_path}"
            _add_node(
                nodes,
                BrainNode(
                    id=file_id,
                    kind="file",
                    title=file_path,
                    text=file_path,
                    confidence="extracted",
                    metadata={"path": file_path},
                ),
            )
            _add_edge(edges, BrainEdge(attempt_id, file_id, "changed_file", "extracted", {}))
        for commit_oid in commit_oids:
            commit_id = f"commit:{commit_oid}"
            _add_node(
                nodes,
                BrainNode(
                    id=commit_id,
                    kind="commit",
                    title=commit_oid[:12],
                    text=commit_oid,
                    confidence="extracted",
                    metadata={"commit_oid": commit_oid},
                ),
            )
            _add_edge(edges, BrainEdge(attempt_id, commit_id, "produced_commit", "extracted", {}))

def _add_node(nodes: dict[str, BrainNode], node: BrainNode) -> None:
    existing = nodes.get(node.id)
    if existing is None or (not existing.text and node.text):
        nodes[node.id] = node

def _add_edge(edges: dict[tuple[str, str, str], BrainEdge], edge: BrainEdge) -> None:
    edges.setdefault((edge.source, edge.kind, edge.target), edge)

def _append_source(sources: list[BriefingQuerySource], source: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        return
    redacted, _ = redact_text(str(value).strip())
    if redacted:
        sources.append(BriefingQuerySource(source=source, value=redacted))

def _tracked_markdown_paths(root: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "*.md", "docs/*.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ()
    paths = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    for extra in ("AGENT.md", "CLAUDE.md", "README.md"):
        if (root / extra).is_file():
            paths.add(extra)
    return tuple(sorted(paths))

def _read_text_head(path: Path, *, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""

def _doc_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:8])

def _changed_files(
    conn: sqlite3.Connection,
    attempt_id: str,
    *,
    policy: MemoryPolicy,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT file_path
        FROM evidence_files
        WHERE attempt_id = ? AND kind = 'changed'
        ORDER BY file_path
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["file_path"]) for row in rows if not path_excluded(str(row["file_path"]), policy))

def _commit_oids(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT commit_oid
        FROM attempt_commits
        WHERE attempt_id = ?
        ORDER BY rowid ASC
        """,
        (attempt_id,),
    ).fetchall()
    return tuple(str(row["commit_oid"]) for row in rows)

def _read_trace_text(raw_trace_ref: str, *, repo_root: Path, limit: int = 1400) -> str:
    if not raw_trace_ref:
        return ""
    path = Path(raw_trace_ref)
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""

def _advisory_attempt_memory_note(source: str, body: str) -> bool:
    if not source.startswith("attempt-memory:"):
        return False
    return "confidence=advisory" in body or any(
        f"verified_status={status}" in body
        for status in ("failed", "failed_interrupted", "needs_review")
    )
