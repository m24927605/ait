from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutcomeClassification:
    outcome_class: str
    confidence: str
    reasons: tuple[str, ...]


def classify_attempt_outcome(
    *,
    reported_status: str,
    verified_status: str,
    result_exit_code: int | None,
    changed_files: tuple[str, ...],
    commit_oids: tuple[str, ...],
    observed_tool_calls: int,
    observed_file_writes: int,
    observed_tests_run: int,
    observed_tests_failed: int,
    raw_trace_text: str,
    has_memory_candidates: bool,
) -> OutcomeClassification:
    reasons: list[str] = []
    normalized_trace = raw_trace_text.lower()
    has_changes = bool(changed_files or commit_oids or observed_file_writes > 0)
    has_evidence = has_changes or observed_tool_calls > 0 or observed_tests_run > 0 or has_memory_candidates

    if verified_status == "discarded":
        return OutcomeClassification("discarded", "high", ("attempt was discarded",))
    if verified_status == "promoted":
        return OutcomeClassification("promoted", "high", ("attempt commits were promoted",))
    if reported_status != "finished":
        if reported_status == "crashed":
            return OutcomeClassification("failed_infra", "high", ("attempt crashed before finishing",))
        return OutcomeClassification("pending", "low", (f"reported_status={reported_status}",))

    if result_exit_code not in (None, 0):
        if result_exit_code == 130 or "keyboardinterrupt" in normalized_trace or "^c" in normalized_trace:
            return OutcomeClassification("failed_interrupted", "high", ("attempt was interrupted",))
        if _looks_like_infra_failure(normalized_trace):
            return OutcomeClassification("failed_infra", "high", ("trace indicates harness or environment failure",))
        if has_evidence:
            reasons.append("failed attempt still produced reusable evidence")
            if has_changes:
                reasons.append("workspace changed")
            if observed_tests_run > 0:
                reasons.append("tests ran")
            if has_memory_candidates:
                reasons.append("memory candidates extracted")
            return OutcomeClassification("failed_with_evidence", "medium", tuple(reasons))
        return OutcomeClassification("failed", "high", (f"exit_code={result_exit_code}",))

    if verified_status == "failed":
        if _looks_like_infra_failure(normalized_trace):
            return OutcomeClassification("failed_infra", "high", ("verified failure looks infrastructural",))
        if has_evidence:
            return OutcomeClassification("failed_with_evidence", "medium", ("verified failed but evidence exists",))
        return OutcomeClassification("failed", "high", ("verified_status=failed",))

    if observed_tests_failed > 0:
        return OutcomeClassification("needs_review", "medium", ("tests failed despite zero exit code",))
    if has_changes:
        reasons.append("workspace changed")
        if commit_oids:
            reasons.append("attempt has commits")
        return OutcomeClassification("succeeded", "high", tuple(reasons))
    if has_memory_candidates:
        return OutcomeClassification("succeeded", "medium", ("no file changes but durable memory candidates exist",))
    return OutcomeClassification("succeeded_noop", "high", ("zero exit with no changes and no durable evidence",))


def _looks_like_infra_failure(trace_text: str) -> bool:
    markers = (
        "stdout is not a terminal",
        "command not executable",
        "real agent binary",
        "binary not found",
        "wrapper recursion",
        "broken pipe",
        "connection refused",
        "ait daemon did not start",
        "harness",
        "traceback",
    )
    return any(marker in trace_text for marker in markers)
