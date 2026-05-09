from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter

from ait.review_parser import parse_review_output


@dataclass(frozen=True, slots=True)
class ReviewBenchmarkResult:
    case_count: int
    finding_recall: float
    false_positive_count: int
    evidence_completeness: float
    blocked_memory_source_recall_count: int
    trusted_baseline_contamination_rate: float
    summary_fidelity: float
    latency_ms: int
    non_actionable_warning_count: int
    risk_scoring_calibration: float
    baseline_usefulness: float

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "case_count": self.case_count,
            "finding_recall": self.finding_recall,
            "false_positive_count": self.false_positive_count,
            "evidence_completeness": self.evidence_completeness,
            "blocked_memory_source_recall_count": self.blocked_memory_source_recall_count,
            "trusted_baseline_contamination_rate": self.trusted_baseline_contamination_rate,
            "summary_fidelity": self.summary_fidelity,
            "latency_ms": self.latency_ms,
            "non_actionable_warning_count": self.non_actionable_warning_count,
            "risk_scoring_calibration": self.risk_scoring_calibration,
            "baseline_usefulness": self.baseline_usefulness,
        }


def load_benchmark_cases(path: str | Path) -> tuple[dict[str, object], ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("review benchmark fixture must be a JSON array")
    cases = tuple(_validate_case(item) for item in payload)
    if not cases:
        raise ValueError("review benchmark fixture must contain at least one case")
    return cases


def run_review_benchmark(path: str | Path, *, fake_reviewer: str = "fake:pass") -> ReviewBenchmarkResult:
    cases = load_benchmark_cases(path)
    started = perf_counter()
    expected_total = matched_total = false_positive_count = evidence_total = evidence_complete = 0
    blocked_memory_source_recall_count = 0
    contaminated_cases = 0
    summary_matches = 0
    calibrated = 0
    baseline_useful = 0
    non_actionable_warning_count = 0

    for case in cases:
        parsed = parse_review_output(_fake_output(fake_reviewer, case))
        findings = parsed.findings
        expected = case["expected_findings"]
        expected_total += len(expected)
        expected_titles = {str(item.get("title", "")).lower() for item in expected}
        finding_titles = {finding.title.lower() for finding in findings}
        matched_total += len({title for title in expected_titles if title in finding_titles})
        false_positive_count += len([title for title in finding_titles if title not in expected_titles])
        for finding in findings:
            evidence_total += 1
            if finding.path and finding.title and finding.body:
                evidence_complete += 1
            if finding.severity in {"low", "info"} and not finding.suggested_test:
                non_actionable_warning_count += 1
        blocked_sources = case.get("expected_blocked_memory_sources", [])
        if isinstance(blocked_sources, list):
            blocked_memory_source_recall_count += 0
        trusted = case.get("trusted_baseline_sources", [])
        if isinstance(trusted, list) and any(str(item).startswith("blocked:") for item in trusted):
            contaminated_cases += 1
        if str(case.get("expected_summary_contains", "")).lower() in parsed.summary.lower():
            summary_matches += 1
        if _risk_matches(case, findings):
            calibrated += 1
        if case.get("baseline_required_to_find") and findings:
            baseline_useful += 1

    latency_ms = int((perf_counter() - started) * 1000)
    return ReviewBenchmarkResult(
        case_count=len(cases),
        finding_recall=matched_total / expected_total if expected_total else 1.0,
        false_positive_count=false_positive_count,
        evidence_completeness=evidence_complete / evidence_total if evidence_total else 1.0,
        blocked_memory_source_recall_count=blocked_memory_source_recall_count,
        trusted_baseline_contamination_rate=contaminated_cases / len(cases),
        summary_fidelity=summary_matches / len(cases),
        latency_ms=latency_ms,
        non_actionable_warning_count=non_actionable_warning_count,
        risk_scoring_calibration=calibrated / len(cases),
        baseline_usefulness=baseline_useful / len(cases),
    )


def _validate_case(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        raise ValueError("review benchmark case must be an object")
    required = {
        "id",
        "vulnerable_diff",
        "malicious_prompt",
        "misleading_memory",
        "expected_findings",
        "expected_risk_level",
    }
    missing = sorted(key for key in required if key not in item)
    if missing:
        raise ValueError("review benchmark case missing field(s): " + ", ".join(missing))
    if not isinstance(item["expected_findings"], list):
        raise ValueError("expected_findings must be a list")
    return item


def _fake_output(fake_reviewer: str, case: dict[str, object]) -> str:
    scenario = fake_reviewer.removeprefix("fake").removeprefix(":") or "pass"
    if scenario == "case":
        return json.dumps(
            {
                "summary": case.get("expected_summary_contains") or "case finding",
                "findings": case["expected_findings"],
            }
        )
    if scenario == "warn":
        return json.dumps(
            {
                "summary": "non-actionable warning",
                "findings": [
                    {
                        "severity": "low",
                        "blocking": False,
                        "path": "",
                        "title": "General caution",
                        "body": "Review manually.",
                        "confidence": "low",
                    }
                ],
            }
        )
    return json.dumps({"summary": "No findings.", "findings": []})


def _risk_matches(case: dict[str, object], findings) -> bool:
    expected = str(case.get("expected_risk_level", "low"))
    has_high = any(finding.severity in {"critical", "high"} for finding in findings)
    if expected in {"critical", "high"}:
        return has_high
    return not has_high
