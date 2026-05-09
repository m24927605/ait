from __future__ import annotations

import unittest
from pathlib import Path

from ait.review_benchmark import load_benchmark_cases, run_review_benchmark


class ReviewBenchmarkTests(unittest.TestCase):
    def test_load_benchmark_cases_validates_fixture(self) -> None:
        cases = load_benchmark_cases(_fixture_path())

        self.assertEqual(("auth-bypass", "benign-doc"), tuple(str(case["id"]) for case in cases))

    def test_fake_case_reviewer_reports_metrics_without_network(self) -> None:
        result = run_review_benchmark(_fixture_path(), fake_reviewer="fake:case")
        payload = result.to_dict()

        self.assertEqual(2, payload["case_count"])
        self.assertEqual(1.0, payload["finding_recall"])
        self.assertEqual(0, payload["false_positive_count"])
        self.assertEqual(1.0, payload["evidence_completeness"])
        self.assertEqual(0, payload["blocked_memory_source_recall_count"])
        self.assertEqual(0.0, payload["trusted_baseline_contamination_rate"])
        self.assertIn("latency_ms", payload)
        self.assertIn("non_actionable_warning_count", payload)

    def test_fake_warning_reviewer_counts_non_actionable_warnings(self) -> None:
        result = run_review_benchmark(_fixture_path(), fake_reviewer="fake:warn")

        self.assertGreater(result.non_actionable_warning_count, 0)


def _fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "review_benchmark" / "cases.json"


if __name__ == "__main__":
    unittest.main()
