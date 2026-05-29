from __future__ import annotations

from ._shared import *
from ait.cli.status_helpers import _format_status_condensed, _status_payload_with_recovery


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "init":
        result = init_repo(repo_root, auto_git_init=True)
        try:
            automation = enable_available_adapters(
                result.repo_root,
                names=tuple(args.init_adapters) if args.init_adapters else None,
            )
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.shell:
            if automation.shell_snippet:
                print(automation.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        memory_policy = init_memory_policy(result.repo_root)
        statuses = tuple(
            doctor_automation(item.adapter.name, result.repo_root)
            for item in automation.installed
        )
        shell_install_result = _maybe_auto_install_shell_hook(
            skip=getattr(args, "no_shell_install", False),
            installed_adapters=automation.installed,
        )
        payload = _init_payload(
            result,
            automation,
            statuses,
            None,
            memory_policy,
            shell_install=shell_install_result,
        )
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_init(payload))
        return 0
    if args.command == "bootstrap":
        try:
            if args.shell:
                print(bootstrap_shell_snippet(args.name, repo_root))
                return 0
            if args.check:
                result = doctor_automation(args.name, repo_root)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_adapter_doctor(result))
                return 0 if result.ok else 2
            result = bootstrap_adapter(args.name, repo_root)
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_bootstrap(result))
        return 0 if result.ok else 2
    if args.command == "doctor":
        if args.fix:
            try:
                init_result = init_repo(repo_root, auto_git_init=True)
                result = enable_available_adapters(
                    init_result.repo_root,
                    names=(args.name,) if args.name else None,
                )
                memory_policy = init_memory_policy(init_result.repo_root)
            except ValueError as exc:
                if args.format == "json":
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                try:
                    result = enable_available_adapters(
                        repo_root,
                        names=(args.name,) if args.name else None,
                    )
                    init_memory_policy(repo_root)
                except AdapterError as adapter_exc:
                    print(f"error: {adapter_exc}", file=sys.stderr)
                    return 2
                if result.shell_snippet:
                    print(result.shell_snippet)
                    return 0
                print("error: no supported agent binaries found on PATH", file=sys.stderr)
                return 2
            except AdapterError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            statuses = tuple(
                doctor_automation(item.adapter.name, init_result.repo_root)
                for item in result.installed
            )
            if args.format == "json":
                payload = _init_payload(init_result, result, statuses, None, memory_policy)
                print(json.dumps(payload, indent=2))
                return 0 if result.installed else 2
            if result.shell_snippet:
                print(result.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        result = doctor_automation(args.name or "claude-code", repo_root)
        payload = asdict(result)
        payload["installation"] = _installation_payload()
        payload["daemon"] = _daemon_status_payload(repo_root)
        from ait.adapter_doctor import agent_auth_diagnostics

        payload["agent_auth"] = agent_auth_diagnostics(args.name or "claude-code", repo_root)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_adapter_doctor(result, installation=payload["installation"], daemon=payload["daemon"]))
        return 0 if result.ok else 2
    if args.command == "status":
        from ait.agent_state import inspect_agent_state
        from ait.next_action import next_action_for_state

        if args.all_adapters:
            results = tuple(
                doctor_automation(name, repo_root)
                for name in sorted(ADAPTERS)
                if name != "shell"
            )
            memory_status = _memory_status_payload(repo_root)
            installation = _installation_payload()
            daemon = _daemon_status_payload(repo_root)
            payload = [
                _status_payload_with_recovery(
                    _status_payload(
                        result,
                        memory_status=memory_status,
                        installation=installation,
                        daemon=daemon,
                    ),
                    repo_root,
                )
                for result in results
            ]
            state = inspect_agent_state(repo_root)
            agent_state = state.to_dict()
            next_action = next_action_for_state(state).to_dict()
            for item in payload:
                item["agent_state"] = agent_state
                item["next_action"] = next_action
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(_format_status_all(payload, debug=args.debug))
                _maybe_emit_status_all_hint(args, repo_root, results)
            return 0
        result = doctor_automation(args.name, repo_root)
        payload = _status_payload(
            result,
            memory_status=_memory_status_payload(repo_root),
            installation=_installation_payload(),
            daemon=_daemon_status_payload(repo_root),
        )
        payload = _status_payload_with_recovery(payload, repo_root)
        state = inspect_agent_state(repo_root)
        payload["agent_state"] = state.to_dict()
        payload["next_action"] = next_action_for_state(state).to_dict()
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            if getattr(args, "verbose", False) or args.command == "doctor":
                print(_format_status(payload, debug=args.debug))
            else:
                print(_format_status_condensed(payload))
            _maybe_emit_automation_hint(args, repo_root, result)
        return 0
    if args.command == "repair":
        names = (args.name,) if args.name else tuple(name for name in sorted(ADAPTERS) if name != "shell")
        before = tuple(doctor_automation(name, repo_root) for name in names)
        try:
            init_result = init_repo(repo_root, auto_git_init=True)
            result = enable_available_adapters(init_result.repo_root, names=names)
            memory_lint = lint_memory_notes(init_result.repo_root, fix=True)
            memory_health_lint = lint_memory_notes(init_result.repo_root)
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        after = tuple(doctor_automation(name, init_result.repo_root) for name in names)
        payload = _repair_payload(before, result, after, None, memory_lint, memory_health_lint)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_repair(payload))
        return 0 if result.installed or memory_lint.fixes else 2
    if args.command == "enable":
        try:
            result = enable_available_adapters(
                repo_root,
                names=tuple(args.enable_adapters) if args.enable_adapters else None,
            )
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.shell:
            if result.shell_snippet:
                print(result.shell_snippet)
                return 0
            print("error: no supported agent binaries found on PATH", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(asdict(result), indent=2))
        else:
            print(_format_auto_enable(result))
        return 0 if result.ok else 2
    if parser is not None:
        parser.print_help()
    return 1
