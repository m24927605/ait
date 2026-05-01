from __future__ import annotations

from datetime import UTC, datetime

from ait.db import utc_now

from .models import MemorySearchResult


def _apply_temporal_recall_ranking(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
    now = _parse_memory_time(utc_now()) or datetime.now(tz=UTC)
    ranked = [_temporal_ranked_result(result, now=now) for result in results]
    ranked.sort(
        key=lambda result: (
            -float(result.metadata.get("temporal_score", result.score)),
            -result.score,
            result.kind,
            result.id,
        )
    )
    return ranked


def _normalize_recall_ranker_scores(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
    by_ranker: dict[str, list[MemorySearchResult]] = {}
    for result in results:
        by_ranker.setdefault(str(result.metadata.get("ranker") or "unknown"), []).append(result)

    normalized: list[MemorySearchResult] = []
    for ranker_results in by_ranker.values():
        scores = [result.score for result in ranker_results]
        minimum = min(scores)
        maximum = max(scores)
        for result in ranker_results:
            if maximum == minimum:
                score = 1.0
            else:
                score = (result.score - minimum) / (maximum - minimum)
            metadata = dict(result.metadata)
            metadata["ranker_raw_score"] = round(result.score, 6)
            metadata["ranker_normalized_score"] = round(score, 6)
            normalized.append(
                MemorySearchResult(
                    kind=result.kind,
                    id=result.id,
                    score=score,
                    title=result.title,
                    text=result.text,
                    metadata=metadata,
                )
            )
    return normalized


def _temporal_ranked_result(result: MemorySearchResult, *, now: datetime) -> MemorySearchResult:
    metadata = dict(result.metadata)
    temporal_kind = str(metadata.get("kind") or result.kind or "note")
    normalized_kind, unknown_kind = _normalize_temporal_kind(temporal_kind)
    anchor = _parse_memory_time(str(metadata.get("updated_at") or metadata.get("valid_from") or ""))
    age_days = (now - anchor).total_seconds() / 86400.0 if anchor else None
    if age_days is not None and age_days < 0:
        metadata["temporal_future_anchor"] = True
        age_days = None
    time_factor = _temporal_time_factor(normalized_kind, age_days)
    confidence_factor = _temporal_confidence_factor(str(metadata.get("confidence") or ""))
    kind_factor = _temporal_kind_factor(normalized_kind)
    temporal_score = result.score * time_factor * confidence_factor * kind_factor
    metadata.update(
        {
            "temporal_ranker": "temporal-v1",
            "temporal_kind": temporal_kind,
            "temporal_effective_kind": normalized_kind,
            "temporal_base_score": round(result.score, 6),
            "temporal_factor": round(time_factor * confidence_factor * kind_factor, 6),
            "temporal_score": round(temporal_score, 6),
        }
    )
    if unknown_kind:
        metadata["temporal_unknown_kind"] = True
    if age_days is not None:
        metadata["temporal_age_days"] = round(age_days, 3)
    return MemorySearchResult(
        kind=result.kind,
        id=result.id,
        score=temporal_score,
        title=result.title,
        text=result.text,
        metadata=metadata,
    )


def _temporal_time_factor(kind: str, age_days: float | None) -> float:
    if age_days is None:
        return 1.0
    half_life_days, minimum = {
        "current_state": (14.0, 0.35),
        "workflow": (45.0, 0.50),
        "failure": (45.0, 0.45),
        "entity": (60.0, 0.50),
        "rule": (90.0, 0.60),
        "decision": (180.0, 0.70),
        "manual": (365.0, 0.85),
        "note": (90.0, 0.55),
    }.get(kind, (90.0, 0.55))
    return minimum + (1.0 - minimum) * (0.5 ** (age_days / half_life_days))


def _temporal_confidence_factor(confidence: str) -> float:
    return {
        "manual": 1.08,
        "high": 1.05,
        "medium": 0.92,
        "low": 0.78,
    }.get(confidence, 0.90)


def _temporal_kind_factor(kind: str) -> float:
    return {
        "decision": 1.04,
        "rule": 1.03,
        "workflow": 1.02,
        "manual": 1.04,
        "current_state": 1.00,
        "entity": 0.96,
        "failure": 0.88,
    }.get(kind, 1.00)


def _normalize_temporal_kind(kind: str) -> tuple[str, bool]:
    known = {
        "current_state",
        "workflow",
        "failure",
        "entity",
        "rule",
        "decision",
        "manual",
        "note",
    }
    return (kind, False) if kind in known else ("note", True)


def _parse_memory_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
