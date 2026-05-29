from __future__ import annotations

from ._shared import *


def _emit_probe_env() -> str:
    """Shell snippet that exports AIT_SHELL_PROBE_* for each helper currently defined.

    The eval'ing shell side sets `AIT_SHELL_PROBE_<HELPER>=1` only
    when `command -v <helper>` returns success. The Python process
    can then read those env vars to report which helpers exist —
    impossible to determine from inside Python alone since the
    helpers live in the parent shell.
    """
    return (
        'command -v ait >/dev/null 2>&1 '
        '&& AIT_SHELL_PROBE_AIT=1 && export AIT_SHELL_PROBE_AIT\n'
        'command -v _ait_continue_should_cd >/dev/null 2>&1 '
        '&& AIT_SHELL_PROBE_CONTINUE_SHOULD_CD=1 '
        '&& export AIT_SHELL_PROBE_CONTINUE_SHOULD_CD\n'
        'command -v _ait_continue_reminder >/dev/null 2>&1 '
        '&& AIT_SHELL_PROBE_CONTINUE_REMINDER=1 '
        '&& export AIT_SHELL_PROBE_CONTINUE_REMINDER\n'
        ':\n'  # ensure eval exits 0 even if the last helper is absent
    )


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
            if args.shell_command == "probe-env":
                print(_emit_probe_env(), end="")
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
