from __future__ import annotations

import uuid

from ait.db import utc_now
from ait.db.repositories import NewMemoryFact

from .models import MemoryCandidate
from .repository import MemoryRepository


def upsert_memory_fact_for_candidate(
    repo: MemoryRepository,
    *,
    attempt_id: str,
    candidate: MemoryCandidate,
    durable: bool,
) -> None:
    now = utc_now()
    fact_id = f"{attempt_id}:memory-fact:{uuid.uuid5(uuid.NAMESPACE_URL, attempt_id + ':' + candidate.body).hex}"
    repo.upsert_candidate_fact(
        NewMemoryFact(
            id=fact_id,
            kind=memory_fact_kind(candidate.kind),
            topic=candidate.topic,
            body=candidate.body,
            summary=memory_fact_summary(candidate.body),
            status="accepted" if durable else "candidate",
            confidence="medium" if durable else "low",
            source_attempt_id=attempt_id,
            source_trace_ref=candidate.source_ref,
            human_review_state="pending" if durable else "pending",
            provenance="commit" if durable else "transcript",
            valid_from=now,
            created_at=now,
            updated_at=now,
        )
    )


def memory_fact_kind(candidate_kind: str) -> str:
    return {
        "constraint": "rule",
        "decision": "decision",
        "workflow": "workflow",
        "test": "workflow",
        "failure": "failure",
        "open-question": "current_state",
    }.get(candidate_kind, "entity")


def memory_fact_summary(body: str) -> str:
    compacted = " ".join(body.split())
    return compacted[:160]
