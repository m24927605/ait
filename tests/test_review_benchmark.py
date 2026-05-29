from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.review_adapter import ReviewAdapterError, ReviewAdapterResult
from ait.review_benchmark import (
    DEFAULT_REAL_REVIEWER_BENCHMARK_TIMEOUT_SECONDS,
    _case_brief,
    _result_from_outputs,
    load_benchmark_cases,
    run_review_benchmark,
    run_review_benchmark_payload,
)


class ReviewBenchmarkTests(unittest.TestCase):
    def test_load_benchmark_cases_validates_fixture(self) -> None:
        cases = load_benchmark_cases(_fixture_path())

        self.assertEqual(10, len(cases))
        self.assertEqual(
            (
                "auth-bypass",
                "billing-rounding-loss",
                "dependency-typosquat",
                "migration-data-loss",
                "ci-secret-leak",
                "missing-regression-test",
                "stale-memory-api",
                "prompt-injection-ignore-tests",
                "benign-doc",
                "benign-refactor",
            ),
            tuple(str(case["id"]) for case in cases),
        )

    def test_fixture_covers_required_risk_areas_and_false_positive_controls(self) -> None:
        cases = load_benchmark_cases(_fixture_path())
        areas = {str(case["risk_area"]) for case in cases}
        no_finding = [case for case in cases if not case["expected_findings"]]
        memory_trust = [case for case in cases if case["expected_blocked_memory_sources"]]

        self.assertTrue(
            {
                "auth",
                "billing",
                "dependency",
                "migration",
                "ci",
                "testing",
                "security",
                "memory-contamination",
                "false-positive-control",
            }.issubset(areas)
        )
        self.assertGreaterEqual(len(no_finding), 2)
        self.assertGreaterEqual(len(memory_trust), 2)

    def test_real_reviewer_case_brief_spells_parser_schema_fields(self) -> None:
        case = load_benchmark_cases(_fixture_path())[0]
        brief = _case_brief(case, reviewer_adapter="codex", permission_profile="read-only")

        for field in ("severity", "blocking", "path", "title", "body", "evidence_ref", "suggested_test", "confidence"):
            self.assertIn(field, brief)
        self.assertIn("Do not use alternate field names", brief)
        self.assertIn("file, issue, details, recommendation", brief)

    def test_fake_case_reviewer_reports_metrics_without_network(self) -> None:
        result = run_review_benchmark(_fixture_path(), fake_reviewer="fake:case")
        payload = result.to_dict()

        self.assertEqual("ait.review_benchmark", payload["schema"])
        self.assertEqual(10, payload["case_count"])
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

    def test_real_reviewer_metrics_match_expected_findings_without_exact_title_match(self) -> None:
        case = {
            "expected_findings": [
                {
                    "severity": "high",
                    "path": "src/auth/session.py",
                    "title": "Authorization bypass",
                }
            ],
            "expected_blocked_memory_sources": [],
            "trusted_baseline_sources": [],
            "expected_summary_contains": "authorization",
            "expected_risk_level": "high",
            "baseline_required_to_find": False,
        }
        output = json.dumps(
            {
                "summary": "authorization bypass found",
                "findings": [
                    {
                        "severity": "critical",
                        "blocking": True,
                        "path": "src/auth/session.py",
                        "title": "Removed ownership check allows unauthorized resource access",
                        "body": "The owner check is removed.",
                        "evidence_ref": "diff",
                        "suggested_test": "Add a cross-user regression test.",
                        "confidence": "high",
                    }
                ],
            }
        )

        result = _result_from_outputs((case,), [output], latency_ms=1)

        self.assertEqual(1.0, result.finding_recall)
        self.assertEqual(0, result.false_positive_count)

    def test_review_benchmark_run_and_report_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.json"
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "ait",
                    "review",
                    "benchmark",
                    "run",
                    "--fixture",
                    str(_fixture_path()),
                    "--fake-reviewer",
                    "fake:case",
                    "--format",
                    "json",
                    "--output",
                    str(output),
                ],
            ):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

            self.assertEqual(0, exit_code)
            payload = json.loads(output.read_text(encoding="utf-8"))
            contract_path = Path(__file__).parent / "fixtures" / "review_benchmark" / "report_schema_v1_contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual("fake:case", payload["reviewer"])
            self.assertEqual(10, payload["case_count"])

            report_stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "ait",
                    "review",
                    "benchmark",
                    "report",
                    "--input",
                    str(output),
                    "--format",
                    "markdown",
                ],
            ):
                with redirect_stdout(report_stdout):
                    report_exit = cli.main()

            self.assertEqual(0, report_exit)
            markdown = report_stdout.getvalue()
            self.assertIn("# AIT Review Benchmark Report", markdown)
            self.assertIn("Limitations", markdown)

    def test_real_reviewer_benchmark_requires_explicit_dogfood(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires explicit --dogfood"):
            run_review_benchmark_payload(_fixture_path(), reviewer_adapter="claude-code", dogfood=False)

    def test_mock_real_reviewer_dogfood_records_adapter_metadata(self) -> None:
        timeouts = []

        def fake_run_adapter(repo_root, *, review_id, adapter, brief, attempt_head_oid="", baseline_ref_oid="", timeout_seconds=None):
            timeouts.append(timeout_seconds)
            return ReviewAdapterResult(
                command=("mock-reviewer", "--token", "sk-test-secret123456"),
                cwd=str(repo_root),
                returncode=0,
                stdout='{"summary":"auth bypass","findings":[]}',
                stderr="",
                timeout_seconds=timeout_seconds,
                resolved_binary_path="/usr/bin/mock-reviewer",
                blocked_env={"ANTHROPIC_API_KEY": False},
            )

        with patch("ait.review_benchmark.run_review_adapter", side_effect=fake_run_adapter):
            payload = run_review_benchmark_payload(
                _fixture_path(),
                reviewer_adapter="mock-real",
                dogfood=True,
                permission_profile="read-only",
                model="mock-model",
            )

        self.assertTrue(payload["dogfood"])
        self.assertEqual("mock-real", payload["reviewer"])
        self.assertEqual("mock-model", payload["adapter"]["model"])
        self.assertEqual("read-only", payload["adapter"]["permission_profile"])
        self.assertEqual(
            DEFAULT_REAL_REVIEWER_BENCHMARK_TIMEOUT_SECONDS,
            payload["adapter"]["timeout_seconds"],
        )
        self.assertEqual({DEFAULT_REAL_REVIEWER_BENCHMARK_TIMEOUT_SECONDS}, set(timeouts))
        self.assertEqual("completed", payload["run_status"])
        self.assertEqual("sha256:", str(payload["fixture_hash"])[:7])
        self.assertEqual(10, len(payload["case_results"]))
        self.assertEqual('{"summary":"auth bypass","findings":[]}', payload["case_results"][0]["stdout_excerpt"])
        self.assertNotIn("sk-test-secret123456", json.dumps(payload))

    def test_real_reviewer_dogfood_records_unavailable_once_without_repeating_timeout(self) -> None:
        calls = []

        def fake_run_adapter(repo_root, *, review_id, adapter, brief, attempt_head_oid="", baseline_ref_oid="", timeout_seconds=None):
            calls.append(review_id)
            raise ReviewAdapterError("review adapter timed out after 1 seconds")

        with patch("ait.review_benchmark.run_review_adapter", side_effect=fake_run_adapter):
            payload = run_review_benchmark_payload(
                _fixture_path(),
                reviewer_adapter="claude-code",
                dogfood=True,
                permission_profile="read-only",
                model="claude-code-test",
                timeout_seconds=1,
            )

        self.assertEqual(["benchmark:auth-bypass"], calls)
        self.assertEqual("unavailable", payload["run_status"])
        self.assertEqual("claude-code", payload["adapter"]["name"])
        self.assertEqual(1, payload["adapter"]["timeout_seconds"])
        self.assertEqual(10, len(payload["case_results"]))
        self.assertTrue(all(item["status"] == "unavailable" for item in payload["case_results"]))
        self.assertIn("dogfood evidence", " ".join(payload["limitations"]))

    def test_review_benchmark_cli_real_adapter_requires_dogfood(self) -> None:
        stdout = io.StringIO()
        with patch(
            "sys.argv",
            [
                "ait",
                "review",
                "benchmark",
                "run",
                "--fixture",
                str(_fixture_path()),
                "--reviewer-adapter",
                "claude-code",
                "--format",
                "json",
            ],
        ):
            with redirect_stdout(stdout):
                exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(2, exit_code)
        self.assertEqual("error", payload["status"])
        self.assertIn("--dogfood", payload["error"])

    def test_review_benchmark_cli_mock_real_adapter_dogfood_json_smoke(self) -> None:
        def fake_run_adapter(repo_root, *, review_id, adapter, brief, attempt_head_oid="", baseline_ref_oid="", timeout_seconds=None):
            return ReviewAdapterResult(
                command=("mock-reviewer",),
                cwd=str(repo_root),
                returncode=0,
                stdout='{"summary":"ok","findings":[]}',
                stderr="",
                timeout_seconds=None,
                resolved_binary_path="/usr/bin/mock-reviewer",
                blocked_env={},
            )

        stdout = io.StringIO()
        with patch("ait.review_benchmark.run_review_adapter", side_effect=fake_run_adapter):
            with patch(
                "sys.argv",
                [
                    "ait",
                    "review",
                    "benchmark",
                    "run",
                    "--fixture",
                    str(_fixture_path()),
                    "--reviewer-adapter",
                    "mock-real",
                    "--dogfood",
                    "--permission-profile",
                    "read-only",
                    "--format",
                    "json",
                ],
            ):
                with redirect_stdout(stdout):
                    exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["dogfood"])
        self.assertEqual("mock-real", payload["reviewer"])
        self.assertEqual("read-only", payload["adapter"]["permission_profile"])
        self.assertEqual("completed", payload["run_status"])
        self.assertEqual(10, len(payload["case_results"]))


def _fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "review_benchmark" / "cases.json"


if __name__ == "__main__":
    unittest.main()
