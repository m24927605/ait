from __future__ import annotations

from pathlib import Path
import uuid

from ait.db import utc_now
from ait.db.repositories import NewMemoryRetrievalEvent
from ait.memory_policy import (
    MemoryPolicy,
    load_memory_policy,
    path_excluded,
    recall_source_allowed,
    recall_source_blocked,
)
from ait.repo import resolve_repo_root

from .common import _attempt_memory_note_advisory
from .lint import lint_memory_notes
from .live_sources import search_live_memory_sources, write_recall_record
from .models import (
    MemorySearchResult,
    RelevantMemoryItem,
    RelevantMemoryRecall,
)
from .render import _render_relevant_memory_text, render_relevant_memory_recall
from .repository import MemoryRepository, open_memory_repository
from .search import (
    render_memory_search_results,
    search_repo_memory,
    search_repo_memory_with_connection,
)
from .temporal import _apply_temporal_recall_ranking, _normalize_recall_ranker_scores


def build_relevant_memory_recall(
    repo_root: str | Path,
    query: str,
    *,
    limit: int = 6,
    budget_chars: int = 4000,
    include_unhealthy: bool = False,
    attempt_id: str | None = None,
    include_live_sources: bool = True,
    live_paths: tuple[str, ...] = (),
    include_global: bool = False,
    include_docs: bool = False,
    include_all_live_sources: bool = False,
    record: bool = False,
    query_sources: object = None,
) -> RelevantMemoryRecall:
    root = resolve_repo_root(repo_root)
    policy = load_memory_policy(root)
    candidates: tuple[MemorySearchResult, ...] = ()
    state_db_path = root / ".ait" / "state.sqlite3"
    if state_db_path.exists():
        candidates = search_repo_memory(root, query, limit=max(limit * 3, 12), policy=policy)
    live_manifest: tuple[dict[str, object], ...] = ()
    live_skipped: tuple[dict[str, object], ...] = ()
    if include_live_sources:
        live_results, live_manifest, live_skipped = search_live_memory_sources(
            root,
            query,
            paths=live_paths,
            include_global=include_global,
            include_docs=include_docs,
            limit=max(limit * 3, 12),
            policy=policy,
            include_unmatched=include_all_live_sources,
        )
        candidates = tuple(candidates) + tuple(live_results)
    blocked_notes = (
        _lint_note_codes_by_severity(root, severities=policy.recall_lint_block_severities)
        if state_db_path.exists() and not include_unhealthy
        else {}
    )
    eligible: list[MemorySearchResult] = []
    skipped: list[dict[str, object]] = list(live_skipped)
    for result in candidates:
        source = str(result.metadata.get("source", ""))
        if result.kind == "fact":
            status = str(result.metadata.get("status", ""))
            if status != "accepted":
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": f"memory fact status is {status}",
                    }
                )
                continue
            blocked_reason = _fact_recall_blocked_reason(result.metadata, policy)
            if blocked_reason:
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": blocked_reason,
                    }
                )
                continue
        elif result.kind == "live_source":
            if result.metadata.get("policy_status") != "allowed":
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": str(result.metadata.get("policy_reason") or "blocked by memory policy"),
                    }
                )
                continue
            if not bool(result.metadata.get("source_of_truth", False)):
                skipped.append(
                    {
                        "kind": result.kind,
                        "id": result.id,
                        "source": source,
                        "reason": "live source missing source-of-truth marker",
                    }
                )
                continue
        elif result.kind != "note":
            skipped.append({"kind": result.kind, "id": result.id, "reason": "not a memory note"})
            continue
        if result.kind == "note" and recall_source_blocked(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source blocked by memory policy",
                }
            )
            continue
        if result.kind == "note" and not recall_source_allowed(source, policy):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "source not allowed by memory policy",
                }
            )
            continue
        if result.kind == "note" and result.id in blocked_notes:
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "lint issue",
                    "lint_codes": blocked_notes[result.id],
                }
            )
            continue
        if result.kind == "note" and (
            _attempt_memory_note_advisory(source, result.text)
            or str(result.metadata.get("attempt_memory_confidence") or "") == "advisory"
            or str(result.metadata.get("attempt_memory_verified_status") or "")
            in {"failed", "failed_interrupted", "needs_review"}
        ):
            skipped.append(
                {
                    "kind": result.kind,
                    "id": result.id,
                    "source": source,
                    "reason": "attempt memory is advisory",
                }
            )
            continue
        eligible.append(result)
    ranked = _apply_temporal_recall_ranking(_normalize_recall_ranker_scores(eligible))
    selected_results = ranked[:limit]
    selected_result_ids = {result.id for result in selected_results if result.kind == "live_source"}
    if live_manifest:
        live_manifest = tuple(
            {**item, "selected": item.get("source_id") in selected_result_ids}
            for item in live_manifest
        )
    for result in ranked[limit:]:
        skipped.append(
            {
                "kind": result.kind,
                "id": result.id,
                "source": str(result.metadata.get("source", "")),
                "reason": "over selection limit",
            }
        )
    selected = [
        RelevantMemoryItem(
            kind=result.kind,
            id=result.id,
            source=str(result.metadata.get("source", "")),
            topic=result.title,
            score=result.score,
            text=result.text,
            metadata=result.metadata,
        )
        for result in selected_results
    ]

    rendered, compacted = _render_relevant_memory_text(
        query=query,
        selected=tuple(selected),
        budget_chars=budget_chars,
    )
    if attempt_id:
        _record_memory_retrieval_event(
            root,
            attempt_id=attempt_id,
            query=query,
            selected=tuple(selected),
            budget_chars=budget_chars,
        )
    recall = RelevantMemoryRecall(
        query=query,
        selected=tuple(selected),
        skipped=tuple(skipped),
        budget_chars=budget_chars,
        rendered_chars=len(rendered),
        compacted=compacted,
        source_manifest=live_manifest,
        write_mode="attempt_context" if attempt_id else ("recorded" if record else "read_only"),
    )
    if record and not attempt_id:
        record_ref = write_recall_record(root, recall, query_sources=query_sources)
        recall = RelevantMemoryRecall(
            query=recall.query,
            selected=recall.selected,
            skipped=recall.skipped,
            budget_chars=recall.budget_chars,
            rendered_chars=recall.rendered_chars,
            compacted=recall.compacted,
            source_manifest=recall.source_manifest,
            write_mode="recorded",
            record_ref=record_ref,
        )
    return recall


def _fact_recall_blocked_reason(metadata: dict[str, object], policy: MemoryPolicy) -> str:
    sources = tuple(
        str(metadata.get(key) or "")
        for key in ("source_file_path", "source_trace_ref")
        if metadata.get(key)
    )
    if any(recall_source_blocked(source, policy) for source in sources):
        return "fact source blocked by memory policy"
    if any(_looks_like_logical_source(source) and not recall_source_allowed(source, policy) for source in sources):
        return "fact source not allowed by memory policy"
    source_file_path = str(metadata.get("source_file_path") or "")
    if source_file_path and path_excluded(source_file_path, policy):
        return "fact source path excluded by memory policy"
    return ""


def _looks_like_logical_source(source: str) -> bool:
    if "/" in source or "\\" in source:
        return False
    return ":" in source


def _record_memory_retrieval_event(
    repo_root: Path,
    *,
    attempt_id: str,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> None:
    with open_memory_repository(repo_root) as repo:
        _record_memory_retrieval_event_with_repository(
            repo,
            attempt_id=attempt_id,
            query=query,
            selected=selected,
            budget_chars=budget_chars,
        )


def _record_memory_retrieval_event_with_repository(
    repo: MemoryRepository,
    *,
    attempt_id: str,
    query: str,
    selected: tuple[RelevantMemoryItem, ...],
    budget_chars: int,
) -> None:
    selected_fact_ids = tuple(item.id for item in selected if item.kind == "fact")
    repo.insert_retrieval_event(
        NewMemoryRetrievalEvent(
            id=f"{attempt_id}:memory-retrieval:{uuid.uuid4().hex}",
            attempt_id=attempt_id,
            query=query,
            selected_fact_ids=selected_fact_ids,
            ranker_version="hybrid-v1",
            budget_chars=budget_chars,
            created_at=utc_now(),
        )
    )


def _lint_note_codes_by_severity(
    repo_root: str | Path,
    *,
    severities: tuple[str, ...],
) -> dict[str, list[str]]:
    if not severities:
        return {}
    blocked_severities = set(severities)
    result = lint_memory_notes(repo_root)
    blocked: dict[str, list[str]] = {}
    for issue in result.issues:
        if issue.severity not in blocked_severities:
            continue
        blocked.setdefault(issue.note_id, []).append(issue.code)
    return blocked


__all__ = [
    "build_relevant_memory_recall",
    "render_memory_search_results",
    "render_relevant_memory_recall",
    "search_repo_memory",
    "search_repo_memory_with_connection",
]
