from __future__ import annotations

from pathlib import Path
import subprocess

from ait.db import (
    connect_db,
    get_attempt,
    get_evidence_summary,
    list_attempt_commits,
    list_attempt_review_findings,
    list_attempt_review_overrides,
    list_attempt_reviews,
    list_attempts,
    list_evidence_files,
    run_migrations,
)
from ait.idresolver import resolve_attempt_id
from ait.repo import resolve_repo_root


REVIEW_REPORT_SCHEMA_VERSION = 1


def build_review_report(repo_root: str | Path, *, attempt_selector: str = "latest") -> dict[str, object]:
    root = resolve_repo_root(repo_root)
    conn = connect_db(root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        attempt_id = _resolve_attempt(conn, attempt_selector)
        attempt = get_attempt(conn, attempt_id)
        if attempt is None:
            raise ValueError(f"Unknown attempt: {attempt_id}")
        commits = list_attempt_commits(conn, attempt_id)
        evidence = get_evidence_summary(conn, attempt_id)
        evidence_files = list_evidence_files(conn, attempt_id)
        reviews = list_attempt_reviews(conn, target_attempt_id=attempt_id)
        review_payloads = []
        all_findings = []
        overrides = []
        for review in reviews:
            findings = list_attempt_review_findings(conn, review.id)
            review_overrides = list_attempt_review_overrides(conn, review.id)
            all_findings.extend(findings)
            overrides.extend(review_overrides)
            review_payloads.append(
                {
                    "review_id": review.id,
                    "mode": review.mode,
                    "budget": review.budget,
                    "status": review.status,
                    "blocking": review.blocking,
                    "reviewer_adapter": review.reviewer_adapter,
                    "reviewer_agent_id": review.reviewer_agent_id,
                    "reviewer_model": review.reviewer_model,
                    "risk_level": review.risk_level,
                    "risk_score": review.risk_score,
                    "profiles": list(review.profiles),
                    "artifact_ref": review.artifact_ref,
                    "baseline_ref": review.baseline_ref,
                    "created_at": review.created_at,
                    "completed_at": review.completed_at,
                    "summary": review.summary,
                    "finding_count": len(findings),
                }
            )
    finally:
        conn.close()

    changed_files = tuple(sorted({path for commit in commits for path in commit.touched_files}))
    head_commit = commits[-1].commit_oid if commits else _git_stdout(Path(attempt.workspace_ref), "rev-parse", "--verify", "HEAD", allow_failure=True) or None
    findings_payload = [_finding_payload(finding) for finding in all_findings]
    fixes_applied = [item for item in findings_payload if item["lifecycle_status"] == "fixed"]
    residual = [
        item
        for item in findings_payload
        if item["lifecycle_status"] in {"open", "acknowledged", "accepted_risk"}
    ]
    return {
        "schema_version": REVIEW_REPORT_SCHEMA_VERSION,
        "attempt_id": attempt.id,
        "base_commit": attempt.base_ref_oid,
        "head_commit": head_commit,
        "base_branch": attempt.base_ref_name,
        "workspace_ref": attempt.workspace_ref,
        "reported_status": attempt.reported_status,
        "verified_status": attempt.verified_status,
        "changed_files": list(changed_files),
        "commands_executed": {
            "observed_commands_run": 0 if evidence is None else evidence.observed_commands_run,
            "raw_trace_ref": None if evidence is None else evidence.raw_trace_ref,
            "logs_ref": None if evidence is None else evidence.logs_ref,
        },
        "tests_run": {
            "observed_tests_run": 0 if evidence is None else evidence.observed_tests_run,
            "observed_tests_passed": 0 if evidence is None else evidence.observed_tests_passed,
            "observed_tests_failed": 0 if evidence is None else evidence.observed_tests_failed,
            "observed_lint_passed": None if evidence is None else evidence.observed_lint_passed,
            "observed_build_passed": None if evidence is None else evidence.observed_build_passed,
        },
        "evidence_files": {kind: list(paths) for kind, paths in evidence_files.items()},
        "review_agents": [
            {
                "review_id": review["review_id"],
                "adapter": review["reviewer_adapter"],
                "agent_id": review["reviewer_agent_id"],
                "model": review["reviewer_model"],
                "mode": review["mode"],
                "status": review["status"],
            }
            for review in review_payloads
        ],
        "reviews": review_payloads,
        "findings_by_severity": _findings_by_severity(findings_payload),
        "findings": findings_payload,
        "fixes_applied": fixes_applied,
        "overrides": [
            {
                "id": override.id,
                "review_id": override.review_id,
                "reason": override.reason,
                "actor": override.actor,
                "audit_ref": override.audit_ref,
                "created_at": override.created_at,
            }
            for override in overrides
        ],
        "final_approval_status": _approval_status(review_payloads, findings_payload),
        "residual_risks": residual,
    }


def render_review_report_markdown(report: dict[str, object]) -> str:
    lines = [
        f"# AIT Review Report: {report.get('attempt_id')}",
        "",
        f"- Base: `{report.get('base_commit')}`",
        f"- Head: `{report.get('head_commit')}`",
        f"- Status: `{report.get('final_approval_status')}`",
        f"- Changed files: {len(report.get('changed_files', []))}",
        "",
        "## Tests",
    ]
    tests = report.get("tests_run", {})
    if isinstance(tests, dict):
        lines.extend(
            [
                f"- Run: {tests.get('observed_tests_run', 0)}",
                f"- Passed: {tests.get('observed_tests_passed', 0)}",
                f"- Failed: {tests.get('observed_tests_failed', 0)}",
            ]
        )
    lines.extend(["", "## Review Agents"])
    agents = report.get("review_agents", [])
    if agents:
        for agent in agents:
            if isinstance(agent, dict):
                lines.append(
                    f"- `{agent.get('review_id')}` {agent.get('adapter') or 'deterministic'} "
                    f"mode={agent.get('mode')} status={agent.get('status')}"
                )
    else:
        lines.append("- none")
    lines.extend(["", "## Findings"])
    findings = report.get("findings", [])
    if findings:
        for finding in findings:
            if isinstance(finding, dict):
                location = finding.get("path") or ""
                if finding.get("line") is not None:
                    location = f"{location}:{finding.get('line')}"
                lines.append(
                    f"- `{finding.get('severity')}` `{finding.get('lifecycle_status')}` "
                    f"{location} - {finding.get('title')}"
                )
    else:
        lines.append("- none")
    lines.extend(["", "## Residual Risks"])
    residual = report.get("residual_risks", [])
    if residual:
        for risk in residual:
            if isinstance(risk, dict):
                lines.append(f"- `{risk.get('severity')}` {risk.get('title')}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _resolve_attempt(conn, selector: str) -> str:
    if selector == "latest":
        attempts = list_attempts(conn)
        if not attempts:
            raise ValueError("no attempts found")
        return attempts[-1].id
    return resolve_attempt_id(conn, selector)


def _finding_payload(finding) -> dict[str, object]:
    return {
        "id": finding.id,
        "review_id": finding.review_id,
        "severity": finding.severity,
        "blocking": finding.blocking,
        "lifecycle_status": finding.lifecycle_status,
        "path": finding.path,
        "line": finding.line,
        "hunk_ref": finding.hunk_ref,
        "title": finding.title,
        "body": finding.body,
        "evidence_ref": finding.evidence_ref,
        "suggested_test": finding.suggested_test,
        "confidence": finding.confidence,
    }


def _findings_by_severity(findings: list[dict[str, object]]) -> dict[str, int]:
    counts = {severity: 0 for severity in ("critical", "high", "medium", "low", "info")}
    for finding in findings:
        severity = str(finding.get("severity") or "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _approval_status(reviews: list[dict[str, object]], findings: list[dict[str, object]]) -> str:
    blocking_open = [
        finding
        for finding in findings
        if finding.get("blocking")
        and finding.get("lifecycle_status") in {"open", "acknowledged"}
    ]
    if blocking_open:
        return "blocked"
    if any(review.get("status") == "failed" for review in reviews):
        return "review_failed"
    if any(review.get("status") == "blocked" for review in reviews):
        return "blocked"
    if not reviews:
        return "no_review"
    if any(review.get("status") in {"passed", "warning", "overridden"} for review in reviews):
        return "approved"
    return "pending"


def _git_stdout(cwd: Path, *args: str, allow_failure: bool = False) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if allow_failure:
            return ""
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()
