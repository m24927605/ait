from __future__ import annotations

from ._shared import *

from ait.dev_server import DEFAULT_DEV_PORTS, DevServerError, start_dev_server
from ait.cleanup import CleanupPolicy, cleanup_repo
from ait.landing import ApplyError, apply_attempt, apply_result_payload
from ait.policy import run_apply_policy, run_auto_prune


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "run":
        if run_auto_prune(repo_root):
            _safe_startup_prune(repo_root)
        command = args.run_command
        if command and command[0] == "--":
            command = command[1:]
        if not args.intent:
            try:
                records = start_dev_server(
                    repo_root,
                    tuple(command),
                    ports=tuple(args.dev_ports or args.dev_check_ports or DEFAULT_DEV_PORTS),
                )
            except DevServerError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if args.format == "json":
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
        try:
            result = run_agent_command(
                repo_root,
                intent_title=args.intent,
                agent_id=args.agent,
                command=command,
                adapter_name=args.adapter,
                kind=args.kind,
                description=args.description,
                commit_message=args.commit_message,
                auto_commit=not args.no_auto_commit,
                with_context=args.with_context,
                capture_command_output=args.format == "json",
            )
        except (AdapterError, WorkspaceError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        run_apply = run_apply_policy(repo_root, args.apply)
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
                )
            except (ApplyError, ValueError, WorkspaceError) as exc:
                print(
                    "ait warning: apply was held; run `ait recover latest --debug` "
                    f"for details ({exc})",
                    file=sys.stderr,
                )
        if args.format == "json":
            payload = asdict(result)
            payload["run_apply_policy"] = run_apply
            payload["apply"] = None if applied is None else apply_result_payload(applied, debug=True)
            print(json.dumps(payload, indent=2))
        else:
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


def _apply_mode_for_policy(policy: str) -> str:
    if policy in {"current", "branch"}:
        return policy
    return "auto"


def _safe_startup_prune(repo_root: Path) -> None:
    try:
        cleanup_repo(repo_root, CleanupPolicy(apply=True))
    except Exception:
        return
