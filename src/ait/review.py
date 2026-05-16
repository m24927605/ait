from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from ait.app import init_repo
from ait.db import (
    NewAttemptReview,
    NewAttemptReviewFinding,
    connect_db,
    get_evidence_summary,
    get_attempt_review,
    insert_attempt_review,
    insert_attempt_review_finding,
    list_attempt_commits,
    list_attempt_review_findings,
    list_attempt_review_overrides,
    list_attempt_reviews,
    list_attempts,
    update_attempt_review_status,
    utc_now,
)
from ait.db.records import AttemptRecord, AttemptReviewFindingRecord
from ait.db.review_repositories import AttemptReviewRecord
from ait.idresolver import IdResolutionError, resolve_attempt_id
from ait.ids import new_ulid
from ait.review_adapter import ReviewAdapterError, ReviewAdapterResult, run_review_adapter
from ait.review_baseline import create_review_baseline_snapshot, render_reviewer_brief, write_review_context_manifest
from ait.review_parser import ParsedReviewFinding, ReviewOutputParseError, parse_review_output
from ait.review_policy import (
    RiskAssessment,
    assess_review_risk,
    evaluate_review_freshness,
    latest_attempt_head_oid,
    review_policy_hash,
    risk_reason_payload,
)
from ait.review_policy import required_review_profiles


LATEST_REVIEWABLE = "latest-reviewable"


class ReviewTargetError(ValueError):
    """Raised when a review target selector cannot be resolved."""


class NoReviewableAttemptError(ReviewTargetError):
    """Raised when no attempt is eligible for latest-reviewable."""


@dataclass(frozen=True, slots=True)
class ReviewTarget:
    attempt_id: str
    selector: str
    verified_status: str
    reported_status: str
    workspace_ref: str
    base_ref_oid: str
    base_ref_name: str | None
    target_head_oid: str | None
    changed_files: tuple[str, ...]
    observed_commands_run: int
    observed_tests_run: int
    observed_tests_passed: int
    observed_tests_failed: int
    result_exit_code: int | None
    raw_trace_ref: str | None


@dataclass(frozen=True, slots=True)
class DeterministicReviewResult:
    target: ReviewTarget
    assessment: RiskAssessment
    review: AttemptReviewRecord
    findings: tuple[AttemptReviewFindingRecord, ...] = ()
    error: str | None = None


def load_review_target(repo_root: str | Path, selector: str) -> ReviewTarget:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        return resolve_review_target(conn, selector)
    finally:
        conn.close()


def create_deterministic_review(
    repo_root: str | Path, selector: str
) -> DeterministicReviewResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        target = resolve_review_target(conn, selector)
        assessment = assess_review_risk(
            changed_files=target.changed_files,
            observed_tests_run=target.observed_tests_run,
        )
        review_id = f"review:{new_ulid()}"
        baseline = create_review_baseline_snapshot(
            init_result.repo_root,
            conn,
            review_id=review_id,
            target=target,
        )
        artifact_ref = _artifact_ref(review_id)
        artifact_payload = _artifact_payload(
            review_id=review_id,
            target=target,
            assessment=assessment,
            baseline_ref=baseline.baseline_ref,
        )
        _write_json_artifact(init_result.repo_root / artifact_ref, artifact_payload)
        review = insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=target.attempt_id,
                mode="light",
                budget="quick",
                profiles=(),
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                risk_reasons=tuple(
                    risk_reason_payload(reason) for reason in assessment.risk_reasons
                ),
                status="passed" if assessment.risk_level == "low" else "warning",
                blocking=False,
                policy_hash=review_policy_hash(
                    init_result.repo_root,
                    mode="light",
                    budget="quick",
                    profiles=(),
                    adapter=None,
                ),
                baseline_policy_hash=baseline.baseline_policy_hash,
                created_at=utc_now(),
                artifact_ref=artifact_ref,
                baseline_ref=baseline.baseline_ref,
                target_head_oid=target.target_head_oid,
                base_ref_oid=target.base_ref_oid,
                summary=f"deterministic risk scan: {assessment.risk_level}",
            ),
        )
        return DeterministicReviewResult(target=target, assessment=assessment, review=review)
    finally:
        conn.close()


def create_fake_reviewer_review(
    repo_root: str | Path,
    selector: str,
    *,
    fake_adapter: str,
    budget: str = "standard",
) -> DeterministicReviewResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        target = resolve_review_target(conn, selector)
        assessment = assess_review_risk(
            changed_files=target.changed_files,
            observed_tests_run=target.observed_tests_run,
        )
        review_id = f"review:{new_ulid()}"
        baseline = create_review_baseline_snapshot(
            init_result.repo_root,
            conn,
            review_id=review_id,
            target=target,
        )
        profiles = _profiles_for_fake(assessment)
        brief_ref = _brief_ref(review_id)
        brief = render_reviewer_brief(
            init_result.repo_root,
            review_id=review_id,
            target=target,
            assessment=assessment,
            baseline_ref=baseline.baseline_ref,
            budget=budget,
            profiles=profiles,
        )
        _write_text_artifact(init_result.repo_root / brief_ref, brief)
        context_manifest_ref = write_review_context_manifest(
            init_result.repo_root,
            review_id=review_id,
            target_attempt_id=target.attempt_id,
            baseline_ref=baseline.baseline_ref,
            brief_ref=brief_ref,
            brief_text=brief,
        )
        raw_output = _fake_reviewer_output(fake_adapter, target=target)
        findings: tuple[ParsedReviewFinding, ...] = ()
        parse_error: str | None = None
        try:
            parsed = parse_review_output(raw_output, changed_files=target.changed_files)
            findings = parsed.findings
            summary = parsed.summary
        except ReviewOutputParseError as exc:
            parse_error = str(exc)
            summary = f"reviewer output parse failed: {parse_error}"
        status, blocking = _status_for_parsed_findings(findings, parse_error=parse_error)
        artifact_ref = _artifact_ref(review_id)
        _write_json_artifact(
            init_result.repo_root / artifact_ref,
            _reviewer_artifact_payload(
                review_id=review_id,
                target=target,
                assessment=assessment,
                baseline_ref=baseline.baseline_ref,
                brief_ref=brief_ref,
                context_manifest_ref=context_manifest_ref,
                reviewer_adapter=fake_adapter,
                raw_output=raw_output,
                findings=findings,
                status=status,
                parse_error=parse_error,
            ),
        )
        review = insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=target.attempt_id,
                mode="adversarial",
                budget=budget,
                profiles=profiles,
                reviewer_adapter=fake_adapter,
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                risk_reasons=tuple(
                    risk_reason_payload(reason) for reason in assessment.risk_reasons
                ),
                status=status,
                blocking=blocking,
                policy_hash=review_policy_hash(
                    init_result.repo_root,
                    mode="adversarial",
                    budget=budget,
                    profiles=profiles,
                    adapter=fake_adapter,
                ),
                baseline_policy_hash=baseline.baseline_policy_hash,
                created_at=utc_now(),
                completed_at=utc_now(),
                artifact_ref=artifact_ref,
                baseline_ref=baseline.baseline_ref,
                target_head_oid=target.target_head_oid,
                base_ref_oid=target.base_ref_oid,
                summary=summary,
            ),
        )
        persisted_findings = tuple(
            insert_attempt_review_finding(
                conn,
                NewAttemptReviewFinding(
                    id=f"finding:{new_ulid()}",
                    review_id=review.id,
                    severity=finding.severity,
                    blocking=finding.blocking,
                    lifecycle_status="open",
                    path=finding.path,
                    line=finding.line,
                    hunk_ref=finding.hunk_ref,
                    title=finding.title,
                    body=finding.body,
                    evidence_ref=finding.evidence_ref,
                    suggested_test=finding.suggested_test,
                    confidence=finding.confidence,
                ),
            )
            for finding in findings
        )
        return DeterministicReviewResult(
            target=target,
            assessment=assessment,
            review=review,
            findings=persisted_findings,
            error=parse_error,
        )
    finally:
        conn.close()


def create_command_reviewer_review(
    repo_root: str | Path,
    selector: str,
    *,
    reviewer_adapter: str,
    budget: str = "standard",
) -> DeterministicReviewResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        target = resolve_review_target(conn, selector)
        assessment = assess_review_risk(
            changed_files=target.changed_files,
            observed_tests_run=target.observed_tests_run,
        )
        review_id = f"review:{new_ulid()}"
        baseline = create_review_baseline_snapshot(
            init_result.repo_root,
            conn,
            review_id=review_id,
            target=target,
        )
        profiles = _profiles_for_fake(assessment)
        brief_ref = _brief_ref(review_id)
        brief = render_reviewer_brief(
            init_result.repo_root,
            review_id=review_id,
            target=target,
            assessment=assessment,
            baseline_ref=baseline.baseline_ref,
            budget=budget,
            profiles=profiles,
        )
        _write_text_artifact(init_result.repo_root / brief_ref, brief)
        context_manifest_ref = write_review_context_manifest(
            init_result.repo_root,
            review_id=review_id,
            target_attempt_id=target.attempt_id,
            baseline_ref=baseline.baseline_ref,
            brief_ref=brief_ref,
            brief_text=brief,
        )

        adapter_result: ReviewAdapterResult | None = None
        findings: tuple[ParsedReviewFinding, ...] = ()
        parse_error: str | None = None
        summary = ""
        try:
            adapter_result = run_review_adapter(
                init_result.repo_root,
                review_id=review_id,
                adapter=reviewer_adapter,
                brief=brief,
            )
            if adapter_result.returncode != 0:
                parse_error = f"reviewer adapter exited with code {adapter_result.returncode}"
                summary = parse_error
            else:
                parsed = parse_review_output(adapter_result.stdout, changed_files=target.changed_files)
                findings = parsed.findings
                summary = parsed.summary
        except (ReviewAdapterError, ReviewOutputParseError) as exc:
            parse_error = str(exc)
            summary = f"reviewer invocation failed: {parse_error}"

        status, blocking = _status_for_parsed_findings(findings, parse_error=parse_error)
        artifact_ref = _artifact_ref(review_id)
        _write_json_artifact(
            init_result.repo_root / artifact_ref,
            _reviewer_artifact_payload(
                review_id=review_id,
                target=target,
                assessment=assessment,
                baseline_ref=baseline.baseline_ref,
                brief_ref=brief_ref,
                context_manifest_ref=context_manifest_ref,
                reviewer_adapter=reviewer_adapter,
                raw_output="" if adapter_result is None else adapter_result.stdout,
                findings=findings,
                status=status,
                parse_error=parse_error,
                adapter_result=adapter_result,
            ),
        )
        review = insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=target.attempt_id,
                mode="adversarial",
                budget=budget,
                profiles=profiles,
                reviewer_adapter=reviewer_adapter,
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                risk_reasons=tuple(
                    risk_reason_payload(reason) for reason in assessment.risk_reasons
                ),
                status=status,
                blocking=blocking,
                policy_hash=review_policy_hash(
                    init_result.repo_root,
                    mode="adversarial",
                    budget=budget,
                    profiles=profiles,
                    adapter=reviewer_adapter,
                ),
                baseline_policy_hash=baseline.baseline_policy_hash,
                created_at=utc_now(),
                completed_at=utc_now(),
                artifact_ref=artifact_ref,
                baseline_ref=baseline.baseline_ref,
                target_head_oid=target.target_head_oid,
                base_ref_oid=target.base_ref_oid,
                summary=summary,
            ),
        )
        persisted_findings = tuple(
            insert_attempt_review_finding(
                conn,
                NewAttemptReviewFinding(
                    id=f"finding:{new_ulid()}",
                    review_id=review.id,
                    severity=finding.severity,
                    blocking=finding.blocking,
                    lifecycle_status="open",
                    path=finding.path,
                    line=finding.line,
                    hunk_ref=finding.hunk_ref,
                    title=finding.title,
                    body=finding.body,
                    evidence_ref=finding.evidence_ref,
                    suggested_test=finding.suggested_test,
                    confidence=finding.confidence,
                ),
            )
            for finding in findings
        )
        return DeterministicReviewResult(
            target=target,
            assessment=assessment,
            review=review,
            findings=persisted_findings,
            error=parse_error,
        )
    finally:
        conn.close()


def execute_queued_review(repo_root: str | Path, review_id: str) -> DeterministicReviewResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        queued = get_attempt_review(conn, review_id)
        if queued is None:
            raise ReviewTargetError(f"review not found: {review_id}")
        if queued.status not in {"queued", "running"}:
            target = resolve_review_target(conn, queued.target_attempt_id)
            assessment = assess_review_risk(
                changed_files=target.changed_files,
                observed_tests_run=target.observed_tests_run,
            )
            return DeterministicReviewResult(target=target, assessment=assessment, review=queued)
        running = update_attempt_review_status(
            conn,
            review_id,
            status="running",
            blocking=True,
            summary="review running",
        )
        target = resolve_review_target(conn, running.target_attempt_id)
        assessment = assess_review_risk(
            changed_files=target.changed_files,
            observed_tests_run=target.observed_tests_run,
        )
        baseline_ref = running.baseline_ref
        if baseline_ref is None:
            baseline = create_review_baseline_snapshot(
                init_result.repo_root,
                conn,
                review_id=review_id,
                target=target,
            )
            baseline_ref = baseline.baseline_ref
        profiles = running.profiles or _profiles_for_fake(assessment)
        brief_ref = _brief_ref(review_id)
        brief = render_reviewer_brief(
            init_result.repo_root,
            review_id=review_id,
            target=target,
            assessment=assessment,
            baseline_ref=baseline_ref,
            budget=running.budget,
            profiles=profiles,
        )
        _write_text_artifact(init_result.repo_root / brief_ref, brief)
        context_manifest_ref = write_review_context_manifest(
            init_result.repo_root,
            review_id=review_id,
            target_attempt_id=target.attempt_id,
            baseline_ref=baseline_ref,
            brief_ref=brief_ref,
            brief_text=brief,
        )

        adapter = running.reviewer_adapter or "fake:pass"
        adapter_result: ReviewAdapterResult | None = None
        raw_output = ""
        findings: tuple[ParsedReviewFinding, ...] = ()
        parse_error: str | None = None
        summary = ""
        try:
            if adapter.startswith("fake"):
                raw_output = _fake_reviewer_output(adapter, target=target)
            else:
                adapter_result = run_review_adapter(
                    init_result.repo_root,
                    review_id=review_id,
                    adapter=adapter,
                    brief=brief,
                )
                raw_output = adapter_result.stdout
                if adapter_result.returncode != 0:
                    parse_error = f"reviewer adapter exited with code {adapter_result.returncode}"
                    summary = parse_error
            if parse_error is None:
                parsed = parse_review_output(raw_output, changed_files=target.changed_files)
                findings = parsed.findings
                summary = parsed.summary
        except (ReviewAdapterError, ReviewOutputParseError) as exc:
            parse_error = str(exc)
            summary = f"reviewer invocation failed: {parse_error}"

        status, blocking = _status_for_parsed_findings(findings, parse_error=parse_error)
        artifact_ref = _artifact_ref(review_id)
        _write_json_artifact(
            init_result.repo_root / artifact_ref,
            _reviewer_artifact_payload(
                review_id=review_id,
                target=target,
                assessment=assessment,
                baseline_ref=baseline_ref,
                brief_ref=brief_ref,
                context_manifest_ref=context_manifest_ref,
                reviewer_adapter=adapter,
                raw_output=raw_output,
                findings=findings,
                status=status,
                parse_error=parse_error,
                adapter_result=adapter_result,
            ),
        )
        completed = update_attempt_review_status(
            conn,
            review_id,
            status=status,
            blocking=blocking,
            completed_at=utc_now(),
            summary=summary,
            artifact_ref=artifact_ref,
        )
        persisted_findings = tuple(
            insert_attempt_review_finding(
                conn,
                NewAttemptReviewFinding(
                    id=f"finding:{new_ulid()}",
                    review_id=completed.id,
                    severity=finding.severity,
                    blocking=finding.blocking,
                    lifecycle_status="open",
                    path=finding.path,
                    line=finding.line,
                    hunk_ref=finding.hunk_ref,
                    title=finding.title,
                    body=finding.body,
                    evidence_ref=finding.evidence_ref,
                    suggested_test=finding.suggested_test,
                    confidence=finding.confidence,
                ),
            )
            for finding in findings
        )
        return DeterministicReviewResult(
            target=target,
            assessment=assessment,
            review=completed,
            findings=persisted_findings,
            error=parse_error,
        )
    finally:
        conn.close()


def create_fake_multi_reviewer_review(
    repo_root: str | Path,
    selector: str,
    *,
    profiles: tuple[str, ...] = (),
    profile_adapters: dict[str, str] | None = None,
    budget: str = "standard",
) -> DeterministicReviewResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        target = resolve_review_target(conn, selector)
        assessment = assess_review_risk(
            changed_files=target.changed_files,
            observed_tests_run=target.observed_tests_run,
        )
        required_profiles = profiles or required_review_profiles(
            init_result.repo_root,
            changed_files=target.changed_files,
            risk_level=assessment.risk_level,
        )
        adapters = profile_adapters or {}
        review_id = f"review:{new_ulid()}"
        baseline = create_review_baseline_snapshot(
            init_result.repo_root,
            conn,
            review_id=review_id,
            target=target,
        )
        missing_profiles = tuple(profile for profile in required_profiles if profile not in adapters)
        profile_results: list[dict[str, object]] = []
        parsed_findings: list[ParsedReviewFinding] = []
        consensus_reason = ""
        if missing_profiles:
            status = "blocked"
            blocking = True
            summary = "missing required profile review: " + ", ".join(missing_profiles)
            consensus_reason = "missing_required_profile"
        else:
            disagreement = False
            parse_error = None
            for profile in required_profiles:
                adapter = adapters[profile]
                raw_output = _fake_reviewer_output(adapter, target=target)
                if adapter == "fake:disagree":
                    disagreement = True
                    raw_output = json.dumps({"summary": "Profile disagreement.", "findings": []})
                try:
                    parsed = parse_review_output(raw_output, changed_files=target.changed_files)
                    findings = parsed.findings
                    parsed_findings.extend(findings)
                    profile_status, profile_blocking = _status_for_parsed_findings(
                        findings,
                        parse_error=None,
                    )
                    profile_results.append(
                        {
                            "profile": profile,
                            "adapter": adapter,
                            "status": profile_status,
                            "blocking": profile_blocking,
                            "raw_output": raw_output,
                            "finding_count": len(findings),
                        }
                    )
                except ReviewOutputParseError as exc:
                    parse_error = str(exc)
                    profile_results.append(
                        {
                            "profile": profile,
                            "adapter": adapter,
                            "status": "failed",
                            "blocking": True,
                            "raw_output": raw_output,
                            "error": parse_error,
                            "finding_count": 0,
                        }
                    )
            status, blocking, summary, consensus_reason = _multi_consensus(
                parsed_findings,
                profile_results=profile_results,
                disagreement=disagreement,
            )
        artifact_ref = _artifact_ref(review_id)
        _write_json_artifact(
            init_result.repo_root / artifact_ref,
            {
                "schema_version": 1,
                "review_id": review_id,
                "target_attempt_id": target.attempt_id,
                "mode": "multi",
                "profiles": list(required_profiles),
                "status": status,
                "blocking": blocking,
                "consensus_reason": consensus_reason,
                "profile_results": profile_results,
                "baseline_ref": baseline.baseline_ref,
                "findings": [
                    {
                        "severity": finding.severity,
                        "blocking": finding.blocking,
                        "path": finding.path,
                        "line": finding.line,
                        "title": finding.title,
                        "body": finding.body,
                        "confidence": finding.confidence,
                    }
                    for finding in parsed_findings
                ],
            },
        )
        review = insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=target.attempt_id,
                mode="multi",
                budget=budget,
                profiles=required_profiles,
                reviewer_adapter="fake-multi",
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                risk_reasons=tuple(
                    risk_reason_payload(reason) for reason in assessment.risk_reasons
                ),
                status=status,
                blocking=blocking,
                policy_hash=review_policy_hash(
                    init_result.repo_root,
                    mode="multi",
                    budget=budget,
                    profiles=required_profiles,
                    adapter="fake-multi",
                ),
                baseline_policy_hash=baseline.baseline_policy_hash,
                created_at=utc_now(),
                completed_at=utc_now(),
                artifact_ref=artifact_ref,
                baseline_ref=baseline.baseline_ref,
                target_head_oid=target.target_head_oid,
                base_ref_oid=target.base_ref_oid,
                summary=summary,
            ),
        )
        persisted_findings = tuple(
            insert_attempt_review_finding(
                conn,
                NewAttemptReviewFinding(
                    id=f"finding:{new_ulid()}",
                    review_id=review.id,
                    severity=finding.severity,
                    blocking=finding.blocking,
                    lifecycle_status="open",
                    path=finding.path,
                    line=finding.line,
                    hunk_ref=finding.hunk_ref,
                    title=finding.title,
                    body=finding.body,
                    evidence_ref=finding.evidence_ref,
                    suggested_test=finding.suggested_test,
                    confidence=finding.confidence,
                ),
            )
            for finding in parsed_findings
        )
        return DeterministicReviewResult(
            target=target,
            assessment=assessment,
            review=review,
            findings=persisted_findings,
        )
    finally:
        conn.close()


def latest_review_summary(
    conn: sqlite3.Connection, target_attempt_id: str, repo_root: str | Path | None = None
) -> dict[str, object]:
    reviews = list_attempt_reviews(conn, target_attempt_id=target_attempt_id)
    if not reviews:
        return {}
    latest = reviews[-1]
    findings = list_attempt_review_findings(conn, latest.id)
    overrides = list_attempt_review_overrides(conn, latest.id)
    blocking_findings = [finding for finding in findings if finding.blocking]
    accepted_risk_findings = [
        finding for finding in findings if finding.lifecycle_status == "accepted_risk"
    ]
    open_high_findings = [
        finding
        for finding in findings
        if finding.lifecycle_status == "open" and finding.severity in {"critical", "high"}
    ]
    overridden = latest.status == "overridden" or bool(overrides)
    freshness = None
    if repo_root is not None:
        freshness = evaluate_review_freshness(repo_root, conn, latest)
    payload: dict[str, object] = {
        "review_id": latest.id,
        "status": latest.status,
        "risk_level": latest.risk_level,
        "risk_score": latest.risk_score,
        "mode": latest.mode,
        "budget": latest.budget,
        "profiles": list(latest.profiles),
        "blocking": latest.blocking,
        "finding_count": len(findings),
        "blocking_finding_count": len(blocking_findings),
        "accepted_risk_finding_count": len(accepted_risk_findings),
        "open_high_finding_count": len(open_high_findings),
        "overridden": overridden,
        "override_count": len(overrides),
        "fresh": None if freshness is None else freshness.fresh,
        "freshness_status": "unknown" if freshness is None else freshness.status,
        "freshness_reason": "repo root unavailable" if freshness is None else freshness.reason,
        "artifact_ref": latest.artifact_ref,
        "baseline_ref": latest.baseline_ref,
        "summary": latest.summary,
    }
    if overrides:
        payload["latest_override_id"] = overrides[-1].id
    return payload


def resolve_review_target(conn: sqlite3.Connection, selector: str) -> ReviewTarget:
    if selector == LATEST_REVIEWABLE:
        target = _latest_reviewable(conn, selector=selector)
        if target is None:
            raise NoReviewableAttemptError("No reviewable attempt found.")
        return target

    try:
        attempt_id = resolve_attempt_id(conn, selector)
    except IdResolutionError as exc:
        raise ReviewTargetError(str(exc)) from exc
    attempts = {attempt.id: attempt for attempt in list_attempts(conn)}
    attempt = attempts.get(attempt_id)
    if attempt is None:
        raise ReviewTargetError(f"unknown attempt: {attempt_id}")
    target = _target_if_reviewable(conn, attempt, selector=selector)
    if target is None:
        raise ReviewTargetError(f"attempt is not reviewable: {attempt_id}")
    return target


def _latest_reviewable(conn: sqlite3.Connection, *, selector: str) -> ReviewTarget | None:
    for attempt in reversed(list_attempts(conn)):
        target = _target_if_reviewable(conn, attempt, selector=selector)
        if target is not None:
            return target
    return None


def _target_if_reviewable(
    conn: sqlite3.Connection, attempt: AttemptRecord, *, selector: str
) -> ReviewTarget | None:
    if attempt.reported_status != "finished":
        return None
    if attempt.verified_status != "succeeded":
        return None
    if attempt.result_promotion_ref:
        return None
    changed_files = _changed_files(conn, attempt.id)
    if not changed_files:
        return None
    evidence = get_evidence_summary(conn, attempt.id)
    return ReviewTarget(
        attempt_id=attempt.id,
        selector=selector,
        verified_status=attempt.verified_status,
        reported_status=attempt.reported_status,
        workspace_ref=attempt.workspace_ref,
        base_ref_oid=attempt.base_ref_oid,
        base_ref_name=attempt.base_ref_name,
        target_head_oid=latest_attempt_head_oid(conn, attempt.id),
        changed_files=changed_files,
        observed_commands_run=0 if evidence is None else evidence.observed_commands_run,
        observed_tests_run=0 if evidence is None else evidence.observed_tests_run,
        observed_tests_passed=0 if evidence is None else evidence.observed_tests_passed,
        observed_tests_failed=0 if evidence is None else evidence.observed_tests_failed,
        result_exit_code=attempt.result_exit_code,
        raw_trace_ref=attempt.raw_trace_ref or (None if evidence is None else evidence.raw_trace_ref),
    )


def _changed_files(conn: sqlite3.Connection, attempt_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                file_path
                for commit in list_attempt_commits(conn, attempt_id)
                for file_path in commit.touched_files
            }
        )
    )


def _artifact_ref(review_id: str) -> str:
    return f".ait/reviews/{review_id.replace(':', '_')}.json"


def _brief_ref(review_id: str) -> str:
    return f".ait/review-briefs/{review_id.replace(':', '_')}.md"


def _artifact_payload(
    *,
    review_id: str,
    target: ReviewTarget,
    assessment: RiskAssessment,
    baseline_ref: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "review_id": review_id,
        "target_attempt_id": target.attempt_id,
        "mode": "light",
        "risk_level": assessment.risk_level,
        "risk_score": assessment.risk_score,
        "risk_reasons": [
            risk_reason_payload(reason) for reason in assessment.risk_reasons
        ],
        "baseline_ref": baseline_ref,
        "findings": [],
    }


def _write_json_artifact(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text_artifact(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_reviewer_output(fake_adapter: str, *, target: ReviewTarget | None = None) -> str:
    scenario = fake_adapter.removeprefix("fake").removeprefix(":") or "pass"
    finding_path = (target.changed_files[0] if target and target.changed_files else "src/example.py")
    if scenario == "pass":
        return json.dumps({"summary": "No findings.", "findings": []})
    if scenario == "low":
        return json.dumps(
            {
                "summary": "One low severity finding.",
                "findings": [
                    {
                        "severity": "low",
                        "blocking": False,
                        "path": finding_path,
                        "title": "Missing edge-case test",
                        "body": "The change has no direct edge-case regression test.",
                        "confidence": "medium",
                    }
                ],
            }
        )
    if scenario == "high":
        return json.dumps(
            {
                "summary": "One blocking finding.",
                "findings": [
                    {
                        "severity": "high",
                        "blocking": True,
                        "path": finding_path,
                        "line": 1,
                        "hunk_ref": "diff-hunk-1",
                        "title": "Potential regression",
                        "body": "The modified path lacks evidence for a sensitive behavior change.",
                        "evidence_ref": "diff-hunk-1",
                        "suggested_test": "Add a focused regression test.",
                        "confidence": "medium",
                    }
                ],
            }
        )
    if scenario == "malformed":
        return "Looks fine to me."
    return json.dumps({"summary": "No findings.", "findings": []})


def _status_for_parsed_findings(
    findings: tuple[ParsedReviewFinding, ...],
    *,
    parse_error: str | None,
) -> tuple[str, bool]:
    if parse_error is not None:
        return "failed", True
    if any(finding.blocking and finding.severity in {"critical", "high"} for finding in findings):
        return "blocked", True
    if findings:
        return "warning", False
    return "passed", False


def _multi_consensus(
    findings: list[ParsedReviewFinding],
    *,
    profile_results: list[dict[str, object]],
    disagreement: bool,
) -> tuple[str, bool, str, str]:
    if disagreement:
        return "blocked", True, "review_disagreement", "review_disagreement"
    if any(result.get("status") == "failed" for result in profile_results):
        return "failed", True, "required profile review failed", "profile_failed"
    if any(finding.blocking and finding.severity in {"critical", "high"} for finding in findings):
        return "blocked", True, "blocking high severity profile finding", "blocking_finding"
    if any(result.get("status") != "passed" for result in profile_results):
        return "warning", False, "non-blocking profile findings", "profile_warning"
    return "passed", False, "all required profiles passed", "all_profiles_passed"


def _profiles_for_fake(assessment: RiskAssessment) -> tuple[str, ...]:
    if any(reason.code == "sensitive_path" for reason in assessment.risk_reasons):
        return ("security", "regression")
    return ("regression",)


def _reviewer_artifact_payload(
    *,
    review_id: str,
    target: ReviewTarget,
    assessment: RiskAssessment,
    baseline_ref: str,
    brief_ref: str,
    context_manifest_ref: str | None,
    reviewer_adapter: str,
    raw_output: str,
    findings: tuple[ParsedReviewFinding, ...],
    status: str,
    parse_error: str | None,
    adapter_result: ReviewAdapterResult | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "review_id": review_id,
        "target_attempt_id": target.attempt_id,
        "mode": "adversarial",
        "reviewer_adapter": reviewer_adapter,
        "status": status,
        "risk_level": assessment.risk_level,
        "risk_score": assessment.risk_score,
        "risk_reasons": [
            risk_reason_payload(reason) for reason in assessment.risk_reasons
        ],
        "baseline_ref": baseline_ref,
        "brief_ref": brief_ref,
        "context_manifest_ref": context_manifest_ref,
        "raw_output": raw_output,
        "parse_error": parse_error,
        "findings": [
            {
                "severity": finding.severity,
                "blocking": finding.blocking,
                "path": finding.path,
                "line": finding.line,
                "hunk_ref": finding.hunk_ref,
                "title": finding.title,
                "body": finding.body,
                "evidence_ref": finding.evidence_ref,
                "suggested_test": finding.suggested_test,
                "mitigation": finding.mitigation,
                "cross_file": finding.cross_file,
                "confidence": finding.confidence,
            }
            for finding in findings
        ],
    }
    if adapter_result is not None:
        payload["adapter_invocation"] = {
            "command": list(adapter_result.command),
            "cwd": adapter_result.cwd,
            "returncode": adapter_result.returncode,
            "stdout": adapter_result.stdout,
            "stderr": adapter_result.stderr,
            "timeout_seconds": adapter_result.timeout_seconds,
            "resolved_binary_path": adapter_result.resolved_binary_path,
            "blocked_env": adapter_result.blocked_env,
        }
    return payload
