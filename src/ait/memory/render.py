from __future__ import annotations

from .models import RelevantMemoryItem, RelevantMemoryRecall


def render_relevant_memory_recall(recall: RelevantMemoryRecall) -> str:
    rendered, _ = _render_relevant_memory_text(
        query=recall.query,
        selected=recall.selected,
        budget_chars=recall.budget_chars,
    )
    return rendered


def _render_relevant_memory_text(
    *,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> tuple[str, bool]:
    lines = [
        "AIT Relevant Memory",
        f"Query: {query}",
        f"Selected: {len(selected)}",
        f"Budget chars: {budget_chars}",
        "",
    ]
    if not selected:
        lines.append("- none")
    for item in selected:
        text = " ".join(item.text.split())
        lines.append(f"- {item.source} score={item.score:.2f} topic={item.topic}")
        if text:
            lines.append(f"  {text[:800]}")
    text = "\n".join(lines) + "\n"
    if budget_chars <= 0 or len(text) <= budget_chars:
        return text, False
    marker = "\n[ait relevant memory compacted to configured budget]\n"
    keep = max(0, budget_chars - len(marker))
    return text[:keep].rstrip() + marker, True
