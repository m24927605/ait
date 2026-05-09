from __future__ import annotations

import unittest

from ait.review_policy import assess_review_risk


class ReviewPolicyTests(unittest.TestCase):
    def test_low_risk_when_changes_have_test_evidence(self) -> None:
        assessment = assess_review_risk(
            changed_files=("docs/readme.md",), observed_tests_run=1
        )

        self.assertEqual("low", assessment.risk_level)
        self.assertEqual(0, assessment.risk_score)
        self.assertEqual("none", assessment.suggested_mode)
        self.assertFalse(assessment.review_required)

    def test_missing_test_evidence_raises_medium_risk(self) -> None:
        assessment = assess_review_risk(
            changed_files=("src/example.py",), observed_tests_run=0
        )

        self.assertEqual("medium", assessment.risk_level)
        self.assertEqual(20, assessment.risk_score)
        self.assertEqual(("missing_test_evidence",), _codes(assessment))
        self.assertEqual("light", assessment.suggested_mode)

    def test_sensitive_path_raises_risk(self) -> None:
        assessment = assess_review_risk(
            changed_files=("src/auth/session.py",), observed_tests_run=1
        )

        self.assertEqual("medium", assessment.risk_level)
        self.assertEqual(30, assessment.risk_score)
        self.assertEqual(("sensitive_path",), _codes(assessment))

    def test_workflow_and_lockfile_accumulate_to_high_risk(self) -> None:
        assessment = assess_review_risk(
            changed_files=(".github/workflows/ci.yml", "uv.lock"),
            observed_tests_run=0,
        )

        self.assertEqual("high", assessment.risk_level)
        self.assertEqual(75, assessment.risk_score)
        self.assertEqual(
            ("sensitive_path", "dependency_change", "missing_test_evidence"),
            _codes(assessment),
        )
        self.assertEqual("adversarial", assessment.suggested_mode)

    def test_score_caps_at_100(self) -> None:
        changed_files = tuple(f"src/auth/generated/file_{index}.png" for index in range(35))

        assessment = assess_review_risk(changed_files=changed_files, observed_tests_run=0)

        self.assertEqual("critical", assessment.risk_level)
        self.assertEqual(100, assessment.risk_score)
        self.assertEqual("adversarial", assessment.suggested_mode)


def _codes(assessment) -> tuple[str, ...]:
    return tuple(reason.code for reason in assessment.risk_reasons)


if __name__ == "__main__":
    unittest.main()
