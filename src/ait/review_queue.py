from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ait.app import init_repo
from ait.db import (
    NewAttemptReview,
    connect_db,
    get_attempt_review,
    insert_attempt_review,
    list_attempt_reviews,
    update_attempt_review_status,
    utc_now,
)
from ait.ids import new_ulid
from ait.review import execute_queued_review, resolve_review_target
from ait.review_baseline import create_review_baseline_snapshot
from ait.review_policy import assess_review_risk, review_policy_hash, risk_reason_payload


ACTIVE_REVIEW_STATUSES = {"queued", "running"}
STALE_RUNNING_AFTER = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class ReviewWorkerResult:
    processed: int
    passed: int
    blocked: int
    failed: int
    skipped: int


def enqueue_review(
    repo_root: str | Path,
    selector: str,
    *,
    mode: str = "adversarial",
    budget: str = "standard",
    adapter: str | None = None,
) -> object:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        target = resolve_review_target(conn, selector)
        profiles = ("regression",)
        policy_hash = review_policy_hash(
            init_result.repo_root,
            mode=mode,
            budget=budget,
            profiles=profiles,
            adapter=adapter,
        )
        existing = _active_duplicate(conn, target_attempt_id=target.attempt_id, policy_hash=policy_hash)
        if existing is not None:
            return existing
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
        return insert_attempt_review(
            conn,
            NewAttemptReview(
                id=review_id,
                target_attempt_id=target.attempt_id,
                mode=mode,
                budget=budget,
                profiles=profiles,
                reviewer_adapter=adapter,
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                risk_reasons=tuple(
                    risk_reason_payload(reason) for reason in assessment.risk_reasons
                ),
                status="queued",
                blocking=True,
                policy_hash=policy_hash,
                baseline_policy_hash=baseline.baseline_policy_hash,
                created_at=utc_now(),
                baseline_ref=baseline.baseline_ref,
                target_head_oid=target.target_head_oid,
                base_ref_oid=target.base_ref_oid,
                summary="review queued",
            ),
        )
    finally:
        conn.close()


def list_review_jobs(repo_root: str | Path) -> list[object]:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        reconcile_stale_review_jobs_with_connection(conn)
        return list_attempt_reviews(conn)
    finally:
        conn.close()


def process_review_queue(
    repo_root: str | Path,
    *,
    max_jobs: int = 1,
) -> ReviewWorkerResult:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        reconcile_stale_review_jobs_with_connection(conn)
        jobs = [
            review
            for review in list_attempt_reviews(conn)
            if review.status == "queued"
        ][: max(0, max_jobs)]
    finally:
        conn.close()

    processed = passed = blocked = failed = skipped = 0
    for job in jobs:
        try:
            result = execute_queued_review(init_result.repo_root, job.id)
        except Exception as exc:
            mark_review_failed(init_result.repo_root, job.id, reason=str(exc))
            processed += 1
            failed += 1
            continue
        processed += 1
        if result.review.status == "passed":
            passed += 1
        elif result.review.status == "blocked":
            blocked += 1
        elif result.review.status == "failed":
            failed += 1
        else:
            skipped += 1
    return ReviewWorkerResult(
        processed=processed,
        passed=passed,
        blocked=blocked,
        failed=failed,
        skipped=skipped,
    )


def mark_review_running(repo_root: str | Path, review_id: str):
    return _mark_review(repo_root, review_id, status="running", blocking=True, summary="review running")


def mark_review_passed(repo_root: str | Path, review_id: str):
    return _mark_review(
        repo_root,
        review_id,
        status="passed",
        blocking=False,
        summary="review passed",
        completed=True,
    )


def mark_review_failed(repo_root: str | Path, review_id: str, *, reason: str):
    return _mark_review(
        repo_root,
        review_id,
        status="failed",
        blocking=True,
        summary=reason,
        completed=True,
    )


def reconcile_stale_review_jobs(repo_root: str | Path):
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        return reconcile_stale_review_jobs_with_connection(conn)
    finally:
        conn.close()


def reconcile_stale_review_jobs_with_connection(conn):
    now = datetime.now(tz=UTC)
    updated = []
    for review in list_attempt_reviews(conn):
        if review.status != "running":
            continue
        created_at = _parse_utc(review.created_at)
        if created_at is not None and now - created_at >= STALE_RUNNING_AFTER:
            updated.append(
                update_attempt_review_status(
                    conn,
                    review.id,
                    status="failed",
                    blocking=True,
                    completed_at=utc_now(),
                    summary="review job stale",
                )
            )
    return updated


def _mark_review(
    repo_root: str | Path,
    review_id: str,
    *,
    status: str,
    blocking: bool,
    summary: str,
    completed: bool = False,
):
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        if get_attempt_review(conn, review_id) is None:
            raise LookupError(f"review not found: {review_id}")
        return update_attempt_review_status(
            conn,
            review_id,
            status=status,
            blocking=blocking,
            completed_at=utc_now() if completed else None,
            summary=summary,
        )
    finally:
        conn.close()


def _active_duplicate(
    conn,
    *,
    target_attempt_id: str,
    policy_hash: str,
):
    for review in reversed(list_attempt_reviews(conn, target_attempt_id=target_attempt_id)):
        if review.status in ACTIVE_REVIEW_STATUSES and review.policy_hash == policy_hash:
            return review
    return None


def _parse_utc(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
