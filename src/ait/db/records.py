from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NewIntent:
    id: str
    repo_id: str
    title: str
    created_at: str
    created_by_actor_type: str
    created_by_actor_id: str
    trigger_source: str
    description: str | None = None
    kind: str | None = None
    parent_intent_id: str | None = None
    root_intent_id: str | None = None
    trigger_prompt_ref: str | None = None
    status: str = "open"
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class IntentRecord:
    id: str
    schema_version: int
    repo_id: str
    title: str
    description: str | None
    kind: str | None
    parent_intent_id: str | None
    root_intent_id: str
    created_at: str
    created_by_actor_type: str
    created_by_actor_id: str
    trigger_source: str
    trigger_prompt_ref: str | None
    status: str
    tags: tuple[str, ...]
    metadata: dict[str, str]

@dataclass(frozen=True)
class NewAttempt:
    id: str
    intent_id: str
    agent_id: str
    workspace_ref: str
    base_ref_oid: str
    started_at: str
    ownership_token: str
    agent_model: str | None = None
    agent_harness: str | None = None
    agent_harness_version: str | None = None
    workspace_kind: str = "worktree"
    base_ref_name: str | None = None
    heartbeat_at: str | None = None
    reported_status: str = "created"
    verified_status: str = "pending"

@dataclass(frozen=True)
class AttemptRecord:
    id: str
    schema_version: int
    intent_id: str
    ordinal: int
    agent_id: str
    agent_model: str | None
    agent_harness: str | None
    agent_harness_version: str | None
    workspace_kind: str
    workspace_ref: str
    base_ref_oid: str
    base_ref_name: str | None
    started_at: str
    ended_at: str | None
    heartbeat_at: str | None
    reported_status: str
    verified_status: str
    ownership_token: str
    raw_trace_ref: str | None
    logs_ref: str | None
    result_promotion_ref: str | None
    result_exit_code: int | None

@dataclass(frozen=True)
class EvidenceSummaryRecord:
    id: str
    schema_version: int
    attempt_id: str
    observed_tool_calls: int
    observed_file_reads: int
    observed_file_writes: int
    observed_commands_run: int
    observed_duration_ms: int
    observed_tests_run: int
    observed_tests_passed: int
    observed_tests_failed: int
    observed_lint_passed: bool | None
    observed_build_passed: bool | None
    raw_prompt_ref: str | None
    raw_trace_ref: str | None
    logs_ref: str | None

@dataclass(frozen=True)
class AttemptCommitRecord:
    attempt_id: str
    commit_oid: str
    base_commit_oid: str
    insertions: int | None
    deletions: int | None
    touched_files: tuple[str, ...]

@dataclass(frozen=True)
class AttemptOutcomeRecord:
    attempt_id: str
    schema_version: int
    outcome_class: str
    confidence: str
    reasons: tuple[str, ...]
    classified_at: str

@dataclass(frozen=True)
class AttemptIdentityRecord:
    attempt_id: str
    handle_index: int
    handle: str
    display_title: str
    deterministic_description: str
    description_source: str
    description_fingerprint: str
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class AttemptAliasRecord:
    alias: str
    attempt_id: str
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class NewMemoryFact:
    id: str
    kind: str
    topic: str
    body: str
    summary: str
    status: str
    confidence: str
    valid_from: str
    created_at: str
    updated_at: str
    source_attempt_id: str | None = None
    source_trace_ref: str | None = None
    source_commit_oid: str | None = None
    source_file_path: str | None = None
    valid_to: str | None = None
    superseded_by: str | None = None
    human_review_state: str = "approved"
    provenance: str = "manual"

@dataclass(frozen=True)
class MemoryFactRecord:
    id: str
    schema_version: int
    kind: str
    topic: str
    body: str
    summary: str
    status: str
    confidence: str
    source_attempt_id: str | None
    source_trace_ref: str | None
    source_commit_oid: str | None
    source_file_path: str | None
    valid_from: str
    valid_to: str | None
    superseded_by: str | None
    created_at: str
    updated_at: str
    human_review_state: str
    provenance: str

@dataclass(frozen=True)
class MemoryFactEntityRecord:
    memory_fact_id: str
    entity: str
    entity_type: str
    weight: float

@dataclass(frozen=True)
class NewMemoryFactEdge:
    id: str
    source_fact_id: str
    target_fact_id: str
    edge_type: str
    confidence: str
    created_at: str

@dataclass(frozen=True)
class MemoryFactEdgeRecord:
    id: str
    source_fact_id: str
    target_fact_id: str
    edge_type: str
    confidence: str
    created_at: str

@dataclass(frozen=True)
class NewMemoryRetrievalEvent:
    id: str
    attempt_id: str
    query: str
    selected_fact_ids: tuple[str, ...]
    ranker_version: str
    budget_chars: int
    created_at: str

@dataclass(frozen=True)
class MemoryRetrievalEventRecord:
    id: str
    attempt_id: str
    query: str
    selected_fact_ids: tuple[str, ...]
    ranker_version: str
    budget_chars: int
    created_at: str

@dataclass(frozen=True)
class NewAttemptReview:
    id: str
    target_attempt_id: str
    mode: str
    budget: str
    profiles: tuple[str, ...]
    risk_level: str
    risk_score: int
    risk_reasons: tuple[dict[str, object], ...]
    status: str
    blocking: bool
    policy_hash: str
    baseline_policy_hash: str
    created_at: str
    review_attempt_id: str | None = None
    reviewer_adapter: str | None = None
    reviewer_agent_id: str | None = None
    artifact_ref: str | None = None
    baseline_ref: str | None = None
    target_head_oid: str | None = None
    base_ref_oid: str | None = None
    reviewer_model: str | None = None
    completed_at: str | None = None
    summary: str = ""

@dataclass(frozen=True)
class AttemptReviewRecord:
    id: str
    target_attempt_id: str
    review_attempt_id: str | None
    mode: str
    budget: str
    profiles: tuple[str, ...]
    reviewer_adapter: str | None
    reviewer_agent_id: str | None
    risk_level: str
    risk_score: int
    risk_reasons: tuple[dict[str, object], ...]
    status: str
    blocking: bool
    artifact_ref: str | None
    baseline_ref: str | None
    target_head_oid: str | None
    base_ref_oid: str | None
    policy_hash: str
    baseline_policy_hash: str
    reviewer_model: str | None
    created_at: str
    completed_at: str | None
    summary: str

@dataclass(frozen=True)
class NewAttemptReviewFinding:
    id: str
    review_id: str
    severity: str
    blocking: bool
    lifecycle_status: str
    title: str
    body: str
    path: str = ""
    line: int | None = None
    hunk_ref: str | None = None
    evidence_ref: str | None = None
    suggested_test: str | None = None
    confidence: str = "medium"

@dataclass(frozen=True)
class AttemptReviewFindingRecord:
    id: str
    review_id: str
    severity: str
    blocking: bool
    lifecycle_status: str
    path: str
    line: int | None
    hunk_ref: str | None
    title: str
    body: str
    evidence_ref: str | None
    suggested_test: str | None
    confidence: str

@dataclass(frozen=True)
class NewAttemptReviewOverride:
    id: str
    review_id: str
    reason: str
    created_at: str
    actor: str | None = None
    audit_ref: str | None = None

@dataclass(frozen=True)
class AttemptReviewOverrideRecord:
    id: str
    review_id: str
    reason: str
    created_at: str
    actor: str | None
    audit_ref: str | None



__all__ = [

    "NewIntent",

    "IntentRecord",

    "NewAttempt",

    "AttemptRecord",

    "EvidenceSummaryRecord",

    "AttemptCommitRecord",

    "AttemptOutcomeRecord",

    "NewMemoryFact",

    "MemoryFactRecord",

    "MemoryFactEntityRecord",

    "NewMemoryFactEdge",

    "MemoryFactEdgeRecord",

    "NewMemoryRetrievalEvent",

    "MemoryRetrievalEventRecord",

    "NewAttemptReview",

    "AttemptReviewRecord",

    "NewAttemptReviewFinding",

    "AttemptReviewFindingRecord",

    "NewAttemptReviewOverride",

    "AttemptReviewOverrideRecord",

]
