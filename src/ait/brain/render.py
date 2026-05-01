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

from .common import _compact_line

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
        "Briefing Query Sources:",
    ]
    if not briefing.sources:
        lines.append("- manual query")
    for source in briefing.sources:
        lines.append(f"- {source.source}: {_compact_line(source.value)}")
    lines.extend(
        [
            "",
            "Relevant Project Facts:",
        ]
    )
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
