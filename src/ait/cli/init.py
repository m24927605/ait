from __future__ import annotations

from ._shared import *


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
        memory_import = ensure_agent_memory_imported(result.repo_root)
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
            memory_import,
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
                memory_import = ensure_agent_memory_imported(init_result.repo_root)
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
                payload = _init_payload(init_result, result, statuses, memory_import, memory_policy)
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
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_adapter_doctor(result, installation=payload["installation"], daemon=payload["daemon"]))
        return 0 if result.ok else 2
    if args.command == "status":
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
                _status_payload(
                    result,
                    memory_status=memory_status,
                    installation=installation,
                    daemon=daemon,
                )
                for result in results
            ]
            if args.format == "json":
                print(json.dumps(payload, indent=2))
            else:
                print(_format_status_all(payload))
                _maybe_emit_status_all_hint(args, repo_root, results)
            return 0
        result = doctor_automation(args.name, repo_root)
        payload = _status_payload(
            result,
            memory_status=_memory_status_payload(repo_root),
            installation=_installation_payload(),
            daemon=_daemon_status_payload(repo_root),
        )
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(_format_status(payload))
            _maybe_emit_automation_hint(args, repo_root, result)
        return 0
    if args.command == "repair":
        names = (args.name,) if args.name else tuple(name for name in sorted(ADAPTERS) if name != "shell")
        before = tuple(doctor_automation(name, repo_root) for name in names)
        try:
            init_result = init_repo(repo_root, auto_git_init=True)
            result = enable_available_adapters(init_result.repo_root, names=names)
            memory_import = ensure_agent_memory_imported(init_result.repo_root)
            memory_lint = lint_memory_notes(init_result.repo_root, fix=True)
            memory_health_lint = lint_memory_notes(init_result.repo_root)
        except AdapterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        after = tuple(doctor_automation(name, init_result.repo_root) for name in names)
        payload = _repair_payload(before, result, after, memory_import, memory_lint, memory_health_lint)
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
