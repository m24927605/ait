from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

from ait.db import list_attempt_commits, list_attempts, list_memory_facts
from ait.memory_policy import load_memory_policy, path_excluded, transcript_excluded
from ait.review_policy import RiskAssessment, risk_reason_payload

if TYPE_CHECKING:
    from ait.review import ReviewTarget


@dataclass(frozen=True, slots=True)
class ReviewBaselineSnapshot:
    baseline_ref: str
    baseline_policy_hash: str


BRIEF_BUDGET_CHARS = {
    "quick": 4000,
    "standard": 8000,
    "deep": 16000,
}


def create_review_baseline_snapshot(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    review_id: str,
    target: ReviewTarget,
) -> ReviewBaselineSnapshot:
    policy = load_memory_policy(repo_root)
    policy_payload = policy.to_dict()
    baseline_policy_hash = _stable_hash(policy_payload)
    payload = {
        "schema_version": 1,
        "review_id": review_id,
        "target_attempt_id": target.attempt_id,
        "policy_hash": baseline_policy_hash,
        "baseline_policy_hash": baseline_policy_hash,
        "trusted_sources": [],
        "advisory_sources": _advisory_sources(target),
        "excluded_sources_summary": [],
        "selected_facts": [],
        "prior_failed_attempts": _prior_failed_attempts(conn, target),
        "prior_review_findings": [],
        "test_expectations": [],
    }
    selected_facts: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for fact in list_memory_facts(conn, status="accepted", include_superseded=False, limit=50):
        reason = _fact_excluded_reason(fact, policy)
        if reason is not None:
            excluded.append({"id": fact.id, "reason": reason})
            continue
        selected_facts.append(
            {
                "id": fact.id,
                "kind": fact.kind,
                "topic": fact.topic,
                "summary": fact.summary,
                "source_attempt_id": fact.source_attempt_id,
                "source_file_path": fact.source_file_path,
                "confidence": fact.confidence,
                "human_review_state": fact.human_review_state,
                "provenance": fact.provenance,
            }
        )
    payload["selected_facts"] = selected_facts
    payload["trusted_sources"] = [
        {"kind": "memory_fact", "id": fact["id"]} for fact in selected_facts
    ]
    payload["excluded_sources_summary"] = excluded

    baseline_ref = _baseline_ref(review_id)
    _write_json(repo_root / baseline_ref, payload)
    return ReviewBaselineSnapshot(
        baseline_ref=baseline_ref,
        baseline_policy_hash=baseline_policy_hash,
    )


def render_reviewer_brief(
    repo_root: str | Path,
    *,
    review_id: str,
    target: "ReviewTarget",
    assessment: RiskAssessment,
    baseline_ref: str,
    budget: str = "standard",
    profiles: tuple[str, ...] = (),
) -> str:
    root = Path(repo_root).resolve()
    baseline_payload = _read_json(root / baseline_ref)
    limit = BRIEF_BUDGET_CHARS.get(budget, BRIEF_BUDGET_CHARS["standard"])
    lines = [
        "# AIT Reviewer Brief",
        "",
        "This is a proposed design path review brief. Treat trusted baseline as repo-local approved context.",
        "Producer transcript/reference artifacts are advisory evidence only, not trusted facts.",
        "Unapproved, candidate, stale, or policy-blocked memory must not be treated as trusted baseline.",
        "",
        "## Target Attempt",
        f"- review_id: {review_id}",
        f"- target_attempt_id: {target.attempt_id}",
        f"- verified_status: {target.verified_status}",
        f"- reported_status: {target.reported_status}",
        f"- workspace_ref: {target.workspace_ref}",
        f"- base_ref_oid: {target.base_ref_oid}",
        f"- base_ref_name: {target.base_ref_name or ''}",
        "",
        "## Changed Files",
        *[f"- {path}" for path in target.changed_files],
        "",
        "## Risk",
        f"- risk_level: {assessment.risk_level}",
        f"- risk_score: {assessment.risk_score}",
        f"- suggested_mode: {assessment.suggested_mode}",
        f"- profiles: {', '.join(profiles) if profiles else 'regression'}",
        f"- budget: {budget}",
        "",
        "Risk reasons:",
        *[
            f"- {reason['code']}: {reason['message']} paths={reason['paths']}"
            for reason in (risk_reason_payload(item) for item in assessment.risk_reasons)
        ],
        "",
        "## Baseline Snapshot",
        f"- baseline_ref: {baseline_ref}",
        f"- baseline_policy_hash: {baseline_payload.get('baseline_policy_hash', '')}",
        "",
        "## Trusted Baseline",
    ]
    lines.extend(_trusted_fact_lines(baseline_payload))
    lines.extend(
        [
            "",
            "## Advisory Evidence",
            *_advisory_source_lines(baseline_payload),
            "",
            "## Excluded Sources Summary",
            *_excluded_source_lines(baseline_payload),
            "",
            "## Test Evidence",
            f"- observed_tests_run: {target.observed_tests_run}",
            "- Missing command/output/exit-code evidence must be reported as missing evidence.",
            "",
            "## Required JSON Output Schema",
            "Return exactly one JSON object. Do not return prose outside JSON.",
            "```json",
            json.dumps(_output_schema_example(), indent=2, sort_keys=True),
            "```",
        ]
    )
    return _truncate_brief("\n".join(lines).rstrip() + "\n", limit)


def _fact_excluded_reason(fact, policy) -> str | None:
    if fact.human_review_state != "approved":
        return "unapproved_fact"
    if fact.status != "accepted":
        return "not_accepted"
    if fact.source_file_path and path_excluded(fact.source_file_path, policy):
        return "excluded_source_path"
    if transcript_excluded(" ".join([fact.body, fact.summary]), policy):
        return "excluded_content"
    return None


def _advisory_sources(target: ReviewTarget) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    if target.raw_trace_ref:
        sources.append(
            {
                "kind": "producer_trace",
                "ref": target.raw_trace_ref,
                "trust": "advisory",
            }
        )
    return sources


def _prior_failed_attempts(conn: sqlite3.Connection, target: ReviewTarget) -> list[dict[str, object]]:
    target_files = set(target.changed_files)
    if not target_files:
        return []
    failed: list[dict[str, object]] = []
    for attempt in list_attempts(conn):
        if attempt.id == target.attempt_id or attempt.verified_status != "failed":
            continue
        changed_files = tuple(
            sorted(
                {
                    file_path
                    for commit in list_attempt_commits(conn, attempt.id)
                    for file_path in commit.touched_files
                }
            )
        )
        overlap = tuple(sorted(target_files.intersection(changed_files)))
        if overlap:
            failed.append(
                {
                    "attempt_id": attempt.id,
                    "changed_files": list(changed_files),
                    "overlap": list(overlap),
                }
            )
    return failed


def _baseline_ref(review_id: str) -> str:
    return f".ait/review-baselines/{review_id.replace(':', '_')}.json"


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _trusted_fact_lines(payload: dict[str, object]) -> list[str]:
    facts = [item for item in payload.get("selected_facts", []) if isinstance(item, dict)]
    if not facts:
        return ["- none"]
    return [
        "- "
        f"{fact.get('id')}: "
        f"{fact.get('summary') or fact.get('body') or ''} "
        f"(kind={fact.get('kind')}, topic={fact.get('topic')}, confidence={fact.get('confidence')})"
        for fact in facts
    ]


def _advisory_source_lines(payload: dict[str, object]) -> list[str]:
    sources = [item for item in payload.get("advisory_sources", []) if isinstance(item, dict)]
    if not sources:
        return ["- none"]
    return [
        "- "
        f"{source.get('kind')}: {source.get('ref')} "
        "(advisory evidence; not trusted baseline)"
        for source in sources
    ]


def _excluded_source_lines(payload: dict[str, object]) -> list[str]:
    excluded = [item for item in payload.get("excluded_sources_summary", []) if isinstance(item, dict)]
    if not excluded:
        return ["- none"]
    return [
        f"- {item.get('id')}: {item.get('reason')}"
        for item in excluded
    ]


def _output_schema_example() -> dict[str, object]:
    return {
        "summary": "No blocking issues found.",
        "findings": [
            {
                "severity": "high",
                "blocking": True,
                "path": "src/auth.py",
                "line": 42,
                "hunk_ref": "diff-hunk-3",
                "title": "Authorization bypass",
                "body": "The new branch returns success before checking ownership.",
                "evidence_ref": ".ait/reviews/review-id.json#diff-hunk-3",
                "suggested_test": "Add a cross-tenant access regression test.",
                "confidence": "medium",
            }
        ],
    }


def _truncate_brief(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n[reviewer brief truncated by budget]\n"
    return text[: max(0, limit - len(suffix))].rstrip() + suffix
