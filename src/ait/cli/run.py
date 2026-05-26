from __future__ import annotations

from ._shared import *

from ait.dev_server import DEFAULT_DEV_PORTS, DevServerError, start_dev_server
from ait.cleanup import CleanupPolicy, cleanup_repo
from ait.landing import ApplyError, apply_attempt, apply_result_payload
from ait.policy import run_apply_policy, run_auto_prune
from ait.review import create_command_reviewer_review, create_deterministic_review, create_fake_reviewer_review
from ait.review_policy import review_policy_requires_escalation, run_review_policy
from ait.review_queue import enqueue_review
from ait.run_report import refresh_run_reports


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "run":
        output_format = _resolve_cli_output_format(getattr(args, "format", None))
        args.format = output_format
        if run_auto_prune(repo_root):
            _safe_startup_prune(repo_root)
        command = args.run_command
        if command and command[0] == "--":
            command = command[1:]
        intent_title = args.intent
        intent_inferred = False
        if not intent_title and not _has_agent_run_hint(args):
            try:
                records = start_dev_server(
                    repo_root,
                    tuple(command),
                    ports=tuple(args.dev_ports or args.dev_check_ports or DEFAULT_DEV_PORTS),
                )
            except DevServerError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if output_format == "json":
                print(json.dumps([asdict(item) for item in records], indent=2))
            else:
                for item in records:
                    print(
                        "\n".join(
                            [
                                "Started AIT dev server",
                                f"  pid: {item.pid}",
                                f"  port: {item.port or 'unknown'}",
                                f"  cwd: {item.cwd}",
                                f"  command: {' '.join(item.command)}",
                            ]
                        )
                    )
            return 0
        if not intent_title:
            intent_title = _inferred_run_intent_title(args)
            intent_inferred = True
        try:
            result = run_agent_command(
                repo_root,
                intent_title=intent_title,
                agent_id=args.agent,
                command=command,
                adapter_name=args.adapter,
                kind=args.kind,
                description=args.description,
                commit_message=args.commit_message,
                auto_commit=not args.no_auto_commit,
                with_context=args.with_context,
                capture_command_output=output_format == "json",
                stdin_mode=getattr(args, "stdin", "inherit"),
            )
        except (AdapterError, WorkspaceError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        run_apply = run_apply_policy(repo_root, args.apply)
        run_review = run_review_policy(repo_root, args.review)
        review_result = None
        review_error = None
        require_review_gate = False
        if (
            run_review != "never"
            and result.exit_code == 0
            and result.attempt.attempt.get("verified_status") == "succeeded"
        ):
            try:
                review_result, require_review_gate = _run_review_for_attempt(
                    repo_root,
                    attempt_id=result.attempt_id,
                    mode=run_review,
                    adapter=getattr(args, "review_adapter", None),
                    budget=getattr(args, "review_budget", "standard"),
                    apply_policy=run_apply,
                )
            except Exception as exc:
                review_error = str(exc)
                if run_apply != "never" and run_review in {"adversarial", "risk-based"}:
                    require_review_gate = True
                print(f"ait warning: review was not completed ({exc})", file=sys.stderr)
            if review_result is not None:
                try:
                    refresh_run_reports(repo_root, latest_attempt_id=result.attempt_id)
                except Exception:
                    pass
        applied = None
        if (
            run_apply != "never"
            and result.exit_code == 0
            and result.attempt.attempt.get("verified_status") == "succeeded"
        ):
            try:
                applied = apply_attempt(
                    repo_root,
                    attempt_selector=result.attempt_id,
                    mode=_apply_mode_for_policy(run_apply),
                    require_review_gate=require_review_gate,
                )
            except (ApplyError, ValueError, WorkspaceError) as exc:
                handle = result.attempt.attempt.get("attempt_handle") or result.attempt_id.rsplit(":", 1)[-1]
                print(
                    f"ait warning: apply was held; run `ait recover {handle} --debug` "
                    f"for details ({exc})",
                    file=sys.stderr,
                )
        if output_format == "json":
            payload = asdict(result)
            attempt_handle = result.attempt.attempt.get("attempt_handle") or result.attempt_id.rsplit(":", 1)[-1]
            payload["run_apply_policy"] = run_apply
            payload["run_review_policy"] = run_review
            payload["review"] = None if review_result is None else _review_result_payload(review_result)
            payload["review_error"] = review_error
            payload["apply"] = None if applied is None else apply_result_payload(applied, debug=True)
            payload["intent_inferred"] = intent_inferred
            payload["attempt_handle"] = attempt_handle
            payload["next_steps"] = _run_next_steps(result, apply_result=applied, attempt_handle=attempt_handle)
            if intent_inferred:
                payload["inferred_intent_title"] = intent_title
            print(json.dumps(payload, indent=2))
        else:
            if intent_inferred:
                print(f"AIT inferred intent: {intent_title}", file=sys.stderr)
            print(_format_run_result(result, apply_result=applied), file=sys.stderr)
        return result.exit_code
    if args.command == "context":
        context = build_agent_context(repo_root, intent_id=args.intent_id)
        if args.format == "json":
            print(json.dumps(asdict(context), indent=2))
        else:
            print(render_agent_context_text(context), end="")
        return 0
    if parser is not None:
        parser.print_help()
    return 1


def _run_next_steps(result, *, apply_result=None, attempt_handle: str) -> list[str]:
    status = result.attempt.attempt.get("verified_status")
    if apply_result is not None and apply_result.status == "applied":
        return []
    if apply_result is not None:
        return [f"ait recover {attempt_handle}"]
    if result.exit_code == 0 and status == "succeeded":
        return [f"ait apply {attempt_handle}"]
    if status in {"failed", "pending"}:
        return [f"ait recover {attempt_handle}"]
    return []


def _apply_mode_for_policy(policy: str) -> str:
    if policy in {"current", "branch"}:
        return policy
    return "auto"


def _run_review_for_attempt(
    repo_root: Path,
    *,
    attempt_id: str,
    mode: str,
    adapter: str | None,
    budget: str,
    apply_policy: str,
):
    if mode == "light":
        return create_deterministic_review(repo_root, attempt_id), False
    if mode == "adversarial":
        return _run_adversarial_review(
            repo_root,
            attempt_id=attempt_id,
            adapter=adapter,
            budget=budget,
        ), apply_policy != "never"
    deterministic = create_deterministic_review(repo_root, attempt_id)
    escalation_required = review_policy_requires_escalation(
        repo_root,
        changed_files=deterministic.target.changed_files,
        risk_level=deterministic.assessment.risk_level,
    )
    if not escalation_required:
        return deterministic, False
    queued = enqueue_review(
        repo_root,
        attempt_id,
        mode="adversarial",
        budget=budget,
        adapter=adapter,
    )
    return queued, apply_policy != "never"


def _run_adversarial_review(
    repo_root: Path,
    *,
    attempt_id: str,
    adapter: str | None,
    budget: str,
):
    if not adapter:
        raise ValueError("review adapter is required for adversarial review")
    if str(adapter).startswith("fake"):
        return create_fake_reviewer_review(
            repo_root,
            attempt_id,
            fake_adapter=str(adapter),
            budget=budget,
        )
    return create_command_reviewer_review(
        repo_root,
        attempt_id,
        reviewer_adapter=str(adapter),
        budget=budget,
    )


def _has_agent_run_hint(args) -> bool:
    return bool(getattr(args, "agent", None)) or getattr(args, "adapter", "shell") != "shell"


def _inferred_run_intent_title(args) -> str:
    label = getattr(args, "agent", None) or getattr(args, "adapter", None) or "agent"
    return f"manual {label} run"


def _review_result_payload(review_result) -> dict[str, object]:
    if hasattr(review_result, "review"):
        return {
            "review_id": review_result.review.id,
            "target_attempt_id": review_result.target.attempt_id,
            "mode": review_result.review.mode,
            "status": review_result.review.status,
            "risk_level": review_result.review.risk_level,
            "risk_score": review_result.review.risk_score,
            "blocking": review_result.review.blocking,
            "finding_count": len(review_result.findings),
            "artifact_ref": review_result.review.artifact_ref,
            "baseline_ref": review_result.review.baseline_ref,
            "error": review_result.error,
        }
    return {
        "review_id": review_result.id,
        "target_attempt_id": review_result.target_attempt_id,
        "mode": review_result.mode,
        "status": review_result.status,
        "risk_level": review_result.risk_level,
        "risk_score": review_result.risk_score,
        "blocking": review_result.blocking,
        "finding_count": 0,
        "artifact_ref": review_result.artifact_ref,
        "baseline_ref": review_result.baseline_ref,
        "error": None,
    }


def _safe_startup_prune(repo_root: Path) -> None:
    try:
        cleanup_repo(repo_root, CleanupPolicy(apply=True))
    except Exception:
        return
