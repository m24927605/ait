from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "adapter":
        if args.adapter_command == "list":
            adapters = [asdict(adapter) for adapter in list_adapters()]
            if args.format == "json":
                print(json.dumps(adapters, indent=2))
            else:
                print(_format_rows(adapters, "table"))
            return 0
        if args.adapter_command == "show":
            adapter = get_adapter(args.name)
            if args.format == "json":
                print(json.dumps(asdict(adapter), indent=2))
            else:
                print(_format_adapter(adapter))
            return 0
        if args.adapter_command == "doctor":
            result = doctor_adapter(args.name, repo_root)
            from ait.adapter_doctor import agent_auth_diagnostics

            auth = agent_auth_diagnostics(args.name, repo_root)
            if args.format == "json":
                payload = asdict(result)
                payload["agent_auth"] = auth
                print(json.dumps(payload, indent=2))
            else:
                print(_format_adapter_doctor(result))
                print(_format_agent_auth(auth))
            return 0 if result.ok else 2
        if args.adapter_command == "setup":
            try:
                result = setup_adapter(
                    args.name,
                    repo_root,
                    target=args.target,
                    print_only=args.print_only,
                    install_wrapper=args.install_wrapper,
                    install_direnv=args.install_direnv,
                )
            except AdapterError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if args.print_only:
                print(json.dumps(result.settings, indent=2, sort_keys=True))
            else:
                print(json.dumps(asdict(result), indent=2))
            return 0
    if parser is not None:
        parser.print_help()
    return 1


def _format_agent_auth(auth: dict[str, object]) -> str:
    lines = [
        "Agent auth:",
        f"- mode: {auth.get('auth_mode')}",
        f"- command: {' '.join(str(item) for item in auth.get('actual_command', []) if str(item)) or 'none'}",
        f"- will use API key: {auth.get('will_use_api_key')}",
        f"- API key mode allowed: {auth.get('api_key_mode_allowed')}",
        f"- fallback to credits: {auth.get('will_fallback_to_credits')}",
    ]
    if auth.get("failure_reason"):
        lines.append(f"- failure: {auth.get('failure_reason')}")
    if auth.get("recommended_fix"):
        lines.append(f"- fix: {auth.get('recommended_fix')}")
    return "\n".join(lines)
