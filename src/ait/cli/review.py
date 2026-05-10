from __future__ import annotations

from ._shared import *

from ait.app import init_repo
from ait.db import (
    NewAttemptReviewOverride,
    connect_db,
    get_attempt_review_finding,
    insert_attempt_review_override,
    list_review_findings,
    update_attempt_review_finding_status,
    utc_now,
)
from ait.ids import new_ulid
from ait.review import (
    NoReviewableAttemptError,
    ReviewTargetError,
    create_command_reviewer_review,
    create_deterministic_review,
    create_fake_reviewer_review,
)
from ait.review_policy import risk_reason_payload
from ait.review_benchmark import run_review_benchmark
from ait.review_queue import list_review_jobs, process_review_queue


def handle(args, repo_root: Path, parser=None) -> int:
    if args.review_command is None:
        jobs = list_review_jobs(repo_root)
        if args.format == "json":
            print(json.dumps(_review_status_payload(jobs), indent=2))
        else:
            print(_format_review_status_text(jobs))
        return 0
    if args.review_command == "report":
        from ait.review_report import build_review_report, render_review_report_markdown

        try:
            report = build_review_report(repo_root, attempt_selector=args.attempt)
        except ValueError as exc:
            return _review_error(args.format, str(exc), exit_code=2, next_step="ait status --json")
        rendered = (
            json.dumps(report, indent=2)
            if args.format == "json"
            else render_review_report_markdown(report)
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered if rendered.endswith("\n") else rendered + "\n", encoding="utf-8")
            if args.format == "json":
                print(json.dumps({"schema_version": 1, "status": "written", "output": str(output), "report": report}, indent=2))
            else:
                print(f"Wrote {output}")
        else:
            print(rendered)
        return 0
    if args.review_command == "status":
        jobs = list_review_jobs(repo_root)
        if getattr(args, "status", None):
            jobs = [job for job in jobs if job.status == args.status]
        if args.format == "json":
            print(json.dumps(_review_status_payload(jobs), indent=2))
        else:
            print(_format_review_status_text(jobs))
        return 0
    if args.review_command == "worker":
        result = process_review_queue(repo_root, max_jobs=args.max_jobs)
        if args.format == "json":
            print(json.dumps(_worker_payload(result), indent=2))
        else:
            print(_format_worker_text(result))
        return 0 if result.failed == 0 else 1
    if args.review_command == "benchmark":
        result = run_review_benchmark(args.fixture, fake_reviewer=args.fake_reviewer)
        payload = result.to_dict()
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_benchmark_text(payload))
        return 0
    if args.review_command == "finding":
        return _handle_review_finding(args, repo_root)
    if args.review_command == "attempt":
        try:
            if getattr(args, "mode", "light") == "adversarial":
                adapter = getattr(args, "review_adapter", None)
                if not adapter:
                    return _review_error(
                        args.format,
                        "review adapter is required for adversarial mode",
                        exit_code=2,
                        next_step="ait review attempt latest-reviewable --mode adversarial --review-adapter fake:pass",
                    )
                if str(adapter).startswith("fake"):
                    result = create_fake_reviewer_review(
                        repo_root,
                        args.selector,
                        fake_adapter=str(adapter),
                        budget=getattr(args, "review_budget", "standard"),
                    )
                else:
                    result = create_command_reviewer_review(
                        repo_root,
                        args.selector,
                        reviewer_adapter=str(adapter),
                        budget=getattr(args, "review_budget", "standard"),
                    )
                if args.format == "json":
                    print(json.dumps(_adversarial_review_payload(result), indent=2))
                else:
                    print(_format_adversarial_review_text(result))
                return 0 if result.review.status != "failed" else 1
            result = create_deterministic_review(repo_root, args.selector)
        except NoReviewableAttemptError as exc:
            return _review_error(
                args.format,
                str(exc),
                exit_code=1,
                next_step="ait attempt list --verified-status succeeded",
            )
        except ReviewTargetError as exc:
            return _review_error(args.format, str(exc), exit_code=2)
        if args.format == "json":
            print(json.dumps(_phase1_review_payload(result), indent=2))
        else:
            print(_format_phase1_review_text(result))
        return 0
    if parser is not None:
        parser.print_help()
    return 1


def _review_error(
    output_format: str,
    message: str,
    *,
    exit_code: int,
    next_step: str | None = None,
) -> int:
    if output_format == "json":
        payload = {
            "schema_version": 1,
            "status": "error",
            "error": message,
        }
        if next_step is not None:
            payload["next_step"] = next_step
        print(json.dumps(payload, indent=2))
    else:
        print(message, file=sys.stderr)
        if next_step is not None:
            print(f"Try: {next_step}", file=sys.stderr)
    return exit_code


def _phase1_review_payload(result) -> dict[str, object]:
    target = result.target
    assessment = result.assessment
    return {
        "schema_version": 1,
        "review_id": result.review.id,
        "target_attempt_id": target.attempt_id,
        "selector": target.selector,
        "verified_status": target.verified_status,
        "reported_status": target.reported_status,
        "workspace_ref": target.workspace_ref,
        "base_ref_oid": target.base_ref_oid,
        "base_ref_name": target.base_ref_name,
        "changed_files": list(target.changed_files),
        "risk_level": assessment.risk_level,
        "risk_score": assessment.risk_score,
        "risk_reasons": [
            risk_reason_payload(reason) for reason in assessment.risk_reasons
        ],
        "review_required": assessment.review_required,
        "suggested_mode": assessment.suggested_mode,
        "artifact_ref": result.review.artifact_ref,
    }


def _format_phase1_review_text(result) -> str:
    target = result.target
    assessment = result.assessment
    lines = [
        f"Review target: {target.attempt_id}",
        f"Review: {result.review.id}",
        f"Risk: {assessment.risk_level} ({assessment.risk_score})",
        f"Suggested mode: {assessment.suggested_mode}",
    ]
    if target.changed_files:
        lines.append(f"Changed: {len(target.changed_files)} files")
    return "\n".join(lines)


def _handle_review_finding(args, repo_root: Path) -> int:
    init_result = init_repo(repo_root)
    conn = connect_db(init_result.db_path)
    try:
        if args.review_finding_command == "list":
            findings = list_review_findings(
                conn,
                lifecycle_status=args.status,
                severity=args.severity,
            )
            if args.format == "json":
                print(json.dumps(_findings_payload(findings), indent=2))
            else:
                print(_format_findings_text(findings))
            return 0
        if args.review_finding_command == "update":
            if args.status in {"false_positive", "accepted_risk"} and not args.reason:
                return _review_error(
                    args.format,
                    f"{args.status} requires --reason",
                    exit_code=2,
                )
            before = get_attempt_review_finding(conn, args.finding_id)
            if before is None:
                return _review_error(args.format, f"finding not found: {args.finding_id}", exit_code=2)
            updated = update_attempt_review_finding_status(
                conn,
                args.finding_id,
                lifecycle_status=args.status,
            )
            override = None
            if args.status == "accepted_risk":
                override = insert_attempt_review_override(
                    conn,
                    NewAttemptReviewOverride(
                        id=f"override:{new_ulid()}",
                        review_id=updated.review_id,
                        reason=args.reason,
                        created_at=utc_now(),
                        actor="cli",
                        audit_ref=f".ait/reviews/finding-{updated.id.replace(':', '_')}-accepted-risk.json",
                    ),
                )
            payload = {
                "schema_version": 1,
                "finding": _finding_payload(updated),
                "override": None if override is None else {
                    "id": override.id,
                    "review_id": override.review_id,
                    "reason": override.reason,
                    "audit_ref": override.audit_ref,
                },
            }
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(f"Finding {updated.id} -> {updated.lifecycle_status}")
            return 0
    finally:
        conn.close()
    return 1


def _adversarial_review_payload(result) -> dict[str, object]:
    payload = _phase1_review_payload(result)
    payload.update(
        {
            "mode": result.review.mode,
            "budget": result.review.budget,
            "status": result.review.status,
            "blocking": result.review.blocking,
            "reviewer_adapter": result.review.reviewer_adapter,
            "baseline_ref": result.review.baseline_ref,
            "finding_count": len(result.findings),
            "error": result.error,
        }
    )
    return payload


def _format_adversarial_review_text(result) -> str:
    lines = [
        f"Review target: {result.target.attempt_id}",
        f"Review: {result.review.id}",
        f"Mode: {result.review.mode}",
        f"Status: {result.review.status}",
        f"Risk: {result.assessment.risk_level} ({result.assessment.risk_score})",
        f"Findings: {len(result.findings)}",
    ]
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)


def _review_status_payload(jobs) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reviews": [
            {
                "review_id": job.id,
                "target_attempt_id": job.target_attempt_id,
                "status": job.status,
                "mode": job.mode,
                "risk_level": job.risk_level,
                "blocking": job.blocking,
                "baseline_ref": job.baseline_ref,
            }
            for job in jobs
        ],
    }


def _format_review_status_text(jobs) -> str:
    if not jobs:
        return "No reviews recorded."
    lines = ["AIT Reviews"]
    for job in jobs:
        lines.append(
            f"- {job.id}: target={job.target_attempt_id} "
            f"status={job.status} risk={job.risk_level} blocking={job.blocking}"
        )
        if job.status in {"queued", "running"}:
            lines.append(f"  Next: ait review status --format json")
    return "\n".join(lines)


def _worker_payload(result) -> dict[str, object]:
    return {
        "schema_version": 1,
        "processed": result.processed,
        "passed": result.passed,
        "blocked": result.blocked,
        "failed": result.failed,
        "skipped": result.skipped,
    }


def _format_worker_text(result) -> str:
    return (
        "Review worker: "
        f"processed={result.processed} "
        f"passed={result.passed} "
        f"blocked={result.blocked} "
        f"failed={result.failed} "
        f"skipped={result.skipped}"
    )


def _format_benchmark_text(payload: dict[str, object]) -> str:
    return (
        "Review benchmark: "
        f"cases={payload['case_count']} "
        f"recall={payload['finding_recall']} "
        f"false_positives={payload['false_positive_count']} "
        f"latency_ms={payload['latency_ms']}"
    )


def _findings_payload(findings) -> dict[str, object]:
    return {
        "schema_version": 1,
        "findings": [_finding_payload(finding) for finding in findings],
    }


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


def _format_findings_text(findings) -> str:
    if not findings:
        return "No review findings found."
    lines = ["AIT Review Findings"]
    for finding in findings:
        lines.append(
            f"- {finding.id}: severity={finding.severity} "
            f"status={finding.lifecycle_status} path={finding.path} title={finding.title}"
        )
    return "\n".join(lines)
