from __future__ import annotations

from ._shared import *


def handle(args, repo_root: Path, parser=None) -> int:
    if args.command == "shell":
        try:
            if args.shell_command == "show":
                print(shell_snippet(args.shell), end="")
                return 0
            if args.shell_command == "install":
                result = install_shell_integration(shell=args.shell, rc_path=args.rc_path)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_shell_integration("installed", result))
                return 0
            if args.shell_command == "uninstall":
                result = uninstall_shell_integration(shell=args.shell, rc_path=args.rc_path)
                if args.format == "json":
                    print(json.dumps(asdict(result), indent=2))
                else:
                    print(_format_shell_integration("removed", result))
                return 0
        except ShellIntegrationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if parser is not None:
        parser.print_help()
    return 1
