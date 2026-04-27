from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sqlite3
import subprocess

from ait.app import init_repo
from ait.db import connect_db, run_migrations, utc_now
from ait.memory_policy import EXCLUDED_MARKER, MemoryPolicy, load_memory_policy, path_excluded, transcript_excluded
from ait.redaction import redact_text
from ait.repo import resolve_repo_root


@dataclass(frozen=True, slots=True)
class BrainNode:
    id: str
    kind: str
    title: str
    text: str
    confidence: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class BrainEdge:
    source: str
    target: str
    kind: str
    confidence: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class RepoBrain:
    repo_root: str
    generated_at: str
    nodes: tuple[BrainNode, ...]
    edges: tuple[BrainEdge, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "generated_at": self.generated_at,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class BrainQueryResult:
    node: BrainNode
    score: float
    neighbors: tuple[BrainNode, ...]
    edges: tuple[BrainEdge, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "node": asdict(self.node),
            "score": self.score,
            "neighbors": [asdict(node) for node in self.neighbors],
            "edges": [asdict(edge) for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class RepoBrainBriefing:
    query: str
    generated_at: str
    results: tuple[BrainQueryResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "generated_at": self.generated_at,
            "results": [result.to_dict() for result in self.results],
        }


def build_repo_brain(repo_root: str | Path) -> RepoBrain:
    init_result = init_repo(repo_root)
    root = init_result.repo_root
    policy = load_memory_policy(root)
    conn = connect_db(init_result.db_path)
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
    root = init_repo(repo_root).repo_root
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


def build_repo_brain_briefing_from_graph(
    brain: RepoBrain,
    query: str,
    *,
    limit: int = 6,
) -> RepoBrainBriefing:
    return RepoBrainBriefing(
        query=query,
        generated_at=brain.generated_at,
        results=query_repo_brain_graph(brain, query, limit=limit),
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


def render_repo_brain_text(brain: RepoBrain, *, budget_chars: int | None = None) -> str:
    grouped: dict[str, list[BrainNode]] = {}
    for node in brain.nodes:
        grouped.setdefault(node.kind, []).append(node)
    lines = [
        "AIT Repo Brain",
        f"Repo: {brain.repo_root}",
        f"Generated: {brain.generated_at}",
        f"Nodes: {len(brain.nodes)}",
        f"Edges: {len(brain.edges)}",
        "",
    ]
    for kind in sorted(grouped):
        lines.append(f"{kind.title()} Nodes:")
        for node in grouped[kind]:
            lines.append(f"- {node.id} confidence={node.confidence} title={node.title!r}")
            if node.text:
                lines.append(f"  {_compact_line(node.text)}")
        lines.append("")
    lines.append("Edges:")
    if not brain.edges:
        lines.append("- none")
    for edge in brain.edges:
        lines.append(f"- {edge.source} -[{edge.kind}/{edge.confidence}]-> {edge.target}")
    text = "\n".join(lines).rstrip() + "\n"
    if budget_chars is None or budget_chars <= 0 or len(text) <= budget_chars:
        return text
    marker = "\n[ait repo brain compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker


def render_brain_query_results(results: tuple[BrainQueryResult, ...]) -> str:
    if not results:
        return "No repo brain query results.\n"
    lines = ["AIT Repo Brain Query Results"]
    for result in results:
        node = result.node
        lines.append(
            f"- {node.kind} {node.id} score={result.score:.2f} "
            f"confidence={node.confidence} title={node.title!r}"
        )
        if node.text:
            lines.append(f"  {_compact_line(node.text)}")
        if result.neighbors:
            neighbor_text = ", ".join(f"{neighbor.kind}:{neighbor.title}" for neighbor in result.neighbors[:8])
            lines.append(f"  neighbors: {neighbor_text}")
    return "\n".join(lines) + "\n"


def render_repo_brain_briefing(briefing: RepoBrainBriefing, *, budget_chars: int | None = 5000) -> str:
    lines = [
        "AIT Repo Brain Briefing",
        f"Query: {briefing.query}",
        f"Generated: {briefing.generated_at}",
        "",
        "Relevant Project Facts:",
    ]
    if not briefing.results:
        lines.append("- none found; inspect the repository normally")
    for result in briefing.results:
        node = result.node
        if node.kind in {"repo", "topic"}:
            lines.append(f"- {node.kind}:{node.title} confidence={node.confidence}")
            if node.text:
                lines.append(f"  {_compact_line(node.text)}")

    lines.append("")
    lines.append("Relevant Attempts:")
    attempt_lines = _briefing_node_lines(briefing, kinds={"attempt"})
    lines.extend(attempt_lines or ["- none"])

    lines.append("")
    lines.append("Likely Files:")
    file_lines = _briefing_node_lines(briefing, kinds={"file"})
    lines.extend(file_lines or ["- none"])

    lines.append("")
    lines.append("Relevant Docs And Notes:")
    doc_note_lines = _briefing_node_lines(briefing, kinds={"doc", "note"})
    lines.extend(doc_note_lines or ["- none"])

    lines.append("")
    lines.append("Connected Evidence:")
    evidence_lines = _briefing_node_lines(briefing, kinds={"intent", "agent", "commit", "trace"})
    lines.extend(evidence_lines or ["- none"])

    lines.append("")
    lines.append("Use this as advisory memory; verify current files before editing.")
    text = "\n".join(lines).rstrip() + "\n"
    if budget_chars is None or budget_chars <= 0 or len(text) <= budget_chars:
        return text
    marker = "\n[ait repo brain briefing compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker


def _briefing_node_lines(briefing: RepoBrainBriefing, *, kinds: set[str]) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for result in briefing.results:
        candidates = (result.node, *result.neighbors)
        for node in candidates:
            if node.kind not in kinds or node.id in seen:
                continue
            seen.add(node.id)
            lines.append(f"- {node.kind}:{node.title} confidence={node.confidence}")
            if node.text:
                lines.append(f"  {_compact_line(node.text)}")
    return lines


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


def _terms(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9_./:-]+", text.lower()))


def _safe_node_fragment(value: str) -> str:
    compacted = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    return compacted or "general"


def _compact_line(text: str, *, limit: int = 180) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."
