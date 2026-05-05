from __future__ import annotations

from pathlib import Path

from ait.brain import (
    build_auto_briefing_query,
    build_repo_brain_briefing_from_graph,
    render_repo_brain_briefing,
    write_repo_brain,
)
from ait.context import build_agent_context, render_agent_context_text
from ait.memory import (
    build_relevant_memory_recall,
    build_repo_memory,
    render_relevant_memory_recall,
    render_repo_memory_text,
)


AIT_CONTEXT_BUDGET_CHARS = 16000


def _write_context_file(
    repo_root: Path,
    workspace: Path,
    intent_id: str,
    *,
    attempt_id: str,
    command: tuple[str, ...] = (),
    agent_id: str | None = None,
) -> Path:
    context = build_agent_context(repo_root, intent_id=intent_id)
    memory = build_repo_memory(repo_root)
    brain = write_repo_brain(repo_root)
    intent = context.intent
    auto_query = build_auto_briefing_query(
        repo_root,
        intent_title=str(intent.get("title") or ""),
        description=str(intent.get("description") or ""),
        kind=str(intent.get("kind") or ""),
        command=command,
        agent_id=agent_id,
    )
    briefing = build_repo_brain_briefing_from_graph(
        brain,
        auto_query.query,
        sources=auto_query.sources,
    )
    recall = build_relevant_memory_recall(
        repo_root,
        auto_query.query,
        budget_chars=4000,
        attempt_id=attempt_id,
    )
    relevant_memory = render_relevant_memory_recall(recall)
    path = workspace / ".ait-context.md"
    context_text = (
        render_agent_context_text(context)
        + "\n"
        + relevant_memory
        + "\n"
        + render_repo_memory_text(
            memory,
            budget_chars=12000,
            include_advisory_attempt_memory=False,
        )
        + "\n"
        + render_repo_brain_briefing(briefing, budget_chars=5000)
    )
    path.write_text(_fit_context_budget(context_text), encoding="utf-8")
    return path


def _fit_context_budget(text: str, *, budget_chars: int = AIT_CONTEXT_BUDGET_CHARS) -> str:
    if budget_chars <= 0:
        return ""
    if len(text) <= budget_chars:
        return text
    marker = (
        "\n\n[ait context truncated: total context exceeded "
        f"{budget_chars} character budget]\n"
    )
    if len(marker) >= budget_chars:
        return marker[:budget_chars]
    return text[: budget_chars - len(marker)].rstrip() + marker
