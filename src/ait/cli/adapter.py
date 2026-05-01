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
            if args.format == "json":
                print(json.dumps(asdict(result), indent=2))
            else:
                print(_format_adapter_doctor(result))
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
