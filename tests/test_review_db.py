from __future__ import annotations

import unittest

from ait.db import (
    NewAttempt,
    NewAttemptReview,
    NewAttemptReviewFinding,
    NewAttemptReviewOverride,
    NewIntent,
    connect_db,
    get_attempt_review,
    insert_attempt,
    insert_attempt_review,
    insert_attempt_review_finding,
    insert_attempt_review_override,
    insert_intent,
    list_attempt_review_findings,
    list_attempt_review_overrides,
    list_attempt_reviews,
    run_migrations,
)


class ReviewDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:01INTENT",
                repo_id="repo",
                title="Review DB",
                created_at="2026-05-09T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:01ATTEMPT",
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref="/tmp/attempt",
                base_ref_oid="0" * 40,
                started_at="2026-05-09T00:01:00Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_attempt_review_round_trips(self) -> None:
        review = _insert_review(self.conn)

        fetched = get_attempt_review(self.conn, review.id)
        assert fetched is not None
        reviews = list_attempt_reviews(self.conn, target_attempt_id="repo:01ATTEMPT")

        self.assertEqual(review, fetched)
        self.assertEqual([review], reviews)
        self.assertEqual(("security", "regression"), review.profiles)
        self.assertEqual(({"code": "sensitive_path", "paths": ["src/auth.py"]},), review.risk_reasons)
        self.assertTrue(review.blocking)

    def test_review_finding_round_trips(self) -> None:
        review = _insert_review(self.conn)

        finding = insert_attempt_review_finding(
            self.conn,
            NewAttemptReviewFinding(
                id="finding:1",
                review_id=review.id,
                severity="high",
                blocking=True,
                lifecycle_status="open",
                path="src/auth.py",
                line=42,
                hunk_ref="hunk-1",
                title="Authorization bypass",
                body="Ownership check is skipped.",
                evidence_ref=".ait/reviews/review.json#hunk-1",
                suggested_test="Add cross-tenant regression test.",
                confidence="medium",
            ),
        )

        self.assertEqual([finding], list_attempt_review_findings(self.conn, review.id))
        self.assertEqual("src/auth.py", finding.path)
        self.assertEqual(42, finding.line)
        self.assertTrue(finding.blocking)

    def test_review_override_round_trips_without_mutating_review(self) -> None:
        review = _insert_review(self.conn)

        override = insert_attempt_review_override(
            self.conn,
            NewAttemptReviewOverride(
                id="override:1",
                review_id=review.id,
                reason="accepted risk for release",
                created_at="2026-05-09T00:03:00Z",
                actor="maintainer",
                audit_ref=".ait/reviews/override.json",
            ),
        )

        fetched = get_attempt_review(self.conn, review.id)
        assert fetched is not None
        self.assertEqual(review.status, fetched.status)
        self.assertEqual([override], list_attempt_review_overrides(self.conn, review.id))


def _insert_review(conn):
    return insert_attempt_review(
        conn,
        NewAttemptReview(
            id="review:1",
            target_attempt_id="repo:01ATTEMPT",
            mode="light",
            budget="quick",
            profiles=("security", "regression"),
            risk_level="high",
            risk_score=70,
            risk_reasons=({"code": "sensitive_path", "paths": ["src/auth.py"]},),
            status="blocked",
            blocking=True,
            policy_hash="policy",
            baseline_policy_hash="baseline-policy",
            created_at="2026-05-09T00:02:00Z",
            artifact_ref=".ait/reviews/review.json",
            baseline_ref=".ait/review-baselines/review.json",
            target_head_oid="1" * 40,
            base_ref_oid="0" * 40,
            summary="blocked by high severity finding",
        ),
    )


if __name__ == "__main__":
    unittest.main()
