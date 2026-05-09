from __future__ import annotations

import json
import sqlite3

from ait.db.records import (
    AttemptReviewFindingRecord,
    AttemptReviewOverrideRecord,
    AttemptReviewRecord,
    NewAttemptReview,
    NewAttemptReviewFinding,
    NewAttemptReviewOverride,
)


def insert_attempt_review(
    conn: sqlite3.Connection, review: NewAttemptReview
) -> AttemptReviewRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO attempt_reviews(
                id, target_attempt_id, review_attempt_id, mode, budget,
                profiles_json, reviewer_adapter, reviewer_agent_id,
                risk_level, risk_score, risk_reasons_json, status, blocking,
                artifact_ref, baseline_ref, target_head_oid, base_ref_oid,
                policy_hash, baseline_policy_hash, reviewer_model, created_at,
                completed_at, summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.id,
                review.target_attempt_id,
                review.review_attempt_id,
                review.mode,
                review.budget,
                _json_dump(list(review.profiles)),
                review.reviewer_adapter,
                review.reviewer_agent_id,
                review.risk_level,
                review.risk_score,
                _json_dump(list(review.risk_reasons)),
                review.status,
                int(review.blocking),
                review.artifact_ref,
                review.baseline_ref,
                review.target_head_oid,
                review.base_ref_oid,
                review.policy_hash,
                review.baseline_policy_hash,
                review.reviewer_model,
                review.created_at,
                review.completed_at,
                review.summary,
            ),
        )
    fetched = get_attempt_review(conn, review.id)
    if fetched is None:
        raise LookupError(f"attempt review not found after insert: {review.id}")
    return fetched


def get_attempt_review(
    conn: sqlite3.Connection, review_id: str
) -> AttemptReviewRecord | None:
    row = conn.execute("SELECT * FROM attempt_reviews WHERE id = ?", (review_id,)).fetchone()
    if row is None:
        return None
    return _row_to_review(row)


def update_attempt_review_status(
    conn: sqlite3.Connection,
    review_id: str,
    *,
    status: str,
    blocking: bool | None = None,
    completed_at: str | None = None,
    summary: str | None = None,
    artifact_ref: str | None = None,
) -> AttemptReviewRecord:
    updates: list[tuple[str, object]] = [("status", status)]
    if blocking is not None:
        updates.append(("blocking", int(blocking)))
    if completed_at is not None:
        updates.append(("completed_at", completed_at))
    if summary is not None:
        updates.append(("summary", summary))
    if artifact_ref is not None:
        updates.append(("artifact_ref", artifact_ref))
    assignments = ", ".join(f"{name} = ?" for name, _value in updates)
    values = [value for _name, value in updates]
    values.append(review_id)
    with conn:
        conn.execute(
            f"UPDATE attempt_reviews SET {assignments} WHERE id = ?",
            values,
        )
    review = get_attempt_review(conn, review_id)
    if review is None:
        raise LookupError(f"attempt review not found: {review_id}")
    return review


def list_attempt_reviews(
    conn: sqlite3.Connection, *, target_attempt_id: str | None = None
) -> list[AttemptReviewRecord]:
    if target_attempt_id is None:
        rows = conn.execute(
            "SELECT * FROM attempt_reviews ORDER BY created_at ASC, rowid ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM attempt_reviews
            WHERE target_attempt_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (target_attempt_id,),
        ).fetchall()
    return [_row_to_review(row) for row in rows]


def insert_attempt_review_finding(
    conn: sqlite3.Connection, finding: NewAttemptReviewFinding
) -> AttemptReviewFindingRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO attempt_review_findings(
                id, review_id, severity, blocking, lifecycle_status, path,
                line, hunk_ref, title, body, evidence_ref, suggested_test,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.id,
                finding.review_id,
                finding.severity,
                int(finding.blocking),
                finding.lifecycle_status,
                finding.path,
                finding.line,
                finding.hunk_ref,
                finding.title,
                finding.body,
                finding.evidence_ref,
                finding.suggested_test,
                finding.confidence,
            ),
        )
    rows = list_attempt_review_findings(conn, finding.review_id)
    for row in rows:
        if row.id == finding.id:
            return row
    raise LookupError(f"attempt review finding not found after insert: {finding.id}")


def list_attempt_review_findings(
    conn: sqlite3.Connection, review_id: str
) -> list[AttemptReviewFindingRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM attempt_review_findings
        WHERE review_id = ?
        ORDER BY rowid ASC
        """,
        (review_id,),
    ).fetchall()
    return [_row_to_finding(row) for row in rows]


def get_attempt_review_finding(
    conn: sqlite3.Connection, finding_id: str
) -> AttemptReviewFindingRecord | None:
    row = conn.execute(
        "SELECT * FROM attempt_review_findings WHERE id = ?",
        (finding_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_finding(row)


def list_review_findings(
    conn: sqlite3.Connection,
    *,
    lifecycle_status: str | None = None,
    severity: str | None = None,
) -> list[AttemptReviewFindingRecord]:
    clauses: list[str] = []
    values: list[object] = []
    if lifecycle_status:
        clauses.append("lifecycle_status = ?")
        values.append(lifecycle_status)
    if severity:
        clauses.append("severity = ?")
        values.append(severity)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM attempt_review_findings
        {where}
        ORDER BY review_id ASC, id ASC
        """,
        values,
    ).fetchall()
    return [_row_to_finding(row) for row in rows]


def update_attempt_review_finding_status(
    conn: sqlite3.Connection, finding_id: str, *, lifecycle_status: str
) -> AttemptReviewFindingRecord:
    with conn:
        conn.execute(
            "UPDATE attempt_review_findings SET lifecycle_status = ? WHERE id = ?",
            (lifecycle_status, finding_id),
        )
    finding = get_attempt_review_finding(conn, finding_id)
    if finding is None:
        raise LookupError(f"attempt review finding not found: {finding_id}")
    return finding


def insert_attempt_review_override(
    conn: sqlite3.Connection, override: NewAttemptReviewOverride
) -> AttemptReviewOverrideRecord:
    with conn:
        conn.execute(
            """
            INSERT INTO attempt_review_overrides(
                id, review_id, reason, created_at, actor, audit_ref
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                override.id,
                override.review_id,
                override.reason,
                override.created_at,
                override.actor,
                override.audit_ref,
            ),
        )
    rows = list_attempt_review_overrides(conn, override.review_id)
    for row in rows:
        if row.id == override.id:
            return row
    raise LookupError(f"attempt review override not found after insert: {override.id}")


def list_attempt_review_overrides(
    conn: sqlite3.Connection, review_id: str
) -> list[AttemptReviewOverrideRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM attempt_review_overrides
        WHERE review_id = ?
        ORDER BY created_at ASC, rowid ASC
        """,
        (review_id,),
    ).fetchall()
    return [_row_to_override(row) for row in rows]


def _row_to_review(row: sqlite3.Row) -> AttemptReviewRecord:
    return AttemptReviewRecord(
        id=str(row["id"]),
        target_attempt_id=str(row["target_attempt_id"]),
        review_attempt_id=_str_or_none(row["review_attempt_id"]),
        mode=str(row["mode"]),
        budget=str(row["budget"]),
        profiles=tuple(str(item) for item in _json_load(row["profiles_json"], [])),
        reviewer_adapter=_str_or_none(row["reviewer_adapter"]),
        reviewer_agent_id=_str_or_none(row["reviewer_agent_id"]),
        risk_level=str(row["risk_level"]),
        risk_score=int(row["risk_score"]),
        risk_reasons=tuple(
            item for item in _json_load(row["risk_reasons_json"], []) if isinstance(item, dict)
        ),
        status=str(row["status"]),
        blocking=bool(row["blocking"]),
        artifact_ref=_str_or_none(row["artifact_ref"]),
        baseline_ref=_str_or_none(row["baseline_ref"]),
        target_head_oid=_str_or_none(row["target_head_oid"]),
        base_ref_oid=_str_or_none(row["base_ref_oid"]),
        policy_hash=str(row["policy_hash"]),
        baseline_policy_hash=str(row["baseline_policy_hash"]),
        reviewer_model=_str_or_none(row["reviewer_model"]),
        created_at=str(row["created_at"]),
        completed_at=_str_or_none(row["completed_at"]),
        summary=str(row["summary"]),
    )


def _row_to_finding(row: sqlite3.Row) -> AttemptReviewFindingRecord:
    return AttemptReviewFindingRecord(
        id=str(row["id"]),
        review_id=str(row["review_id"]),
        severity=str(row["severity"]),
        blocking=bool(row["blocking"]),
        lifecycle_status=str(row["lifecycle_status"]),
        path=str(row["path"]),
        line=None if row["line"] is None else int(row["line"]),
        hunk_ref=_str_or_none(row["hunk_ref"]),
        title=str(row["title"]),
        body=str(row["body"]),
        evidence_ref=_str_or_none(row["evidence_ref"]),
        suggested_test=_str_or_none(row["suggested_test"]),
        confidence=str(row["confidence"]),
    )


def _row_to_override(row: sqlite3.Row) -> AttemptReviewOverrideRecord:
    return AttemptReviewOverrideRecord(
        id=str(row["id"]),
        review_id=str(row["review_id"]),
        reason=str(row["reason"]),
        created_at=str(row["created_at"]),
        actor=_str_or_none(row["actor"]),
        audit_ref=_str_or_none(row["audit_ref"]),
    )


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_load(value: object, default: object) -> object:
    if value is None:
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
