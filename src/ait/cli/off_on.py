"""Shell-eval'able scripts for `ait off` and `ait on`.

The binary cannot mutate its parent shell's environment, so these
commands print a shell snippet that the `ait()` function intercepts
and eval's. Pattern mirrors `ait continue --shell-hook`.

See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md § P1.1.
"""
from __future__ import annotations

import sys
from pathlib import Path


def build_off_script() -> str:
    return (
        "export AIT_BYPASS=1\n"
        'printf "%s\\n" "AIT auto-wrap disabled for this shell." >&2\n'
        'printf "%s\\n" "Run \\`ait on\\` to re-enable." >&2\n'
    )


def build_on_script() -> str:
    return (
        "unset AIT_BYPASS\n"
        'printf "%s\\n" "AIT auto-wrap re-enabled for this shell." >&2\n'
    )


def handle(args, repo_root: Path, parser=None) -> int:
    del parser, repo_root
    if args.command == "off":
        sys.stdout.write(build_off_script())
        return 0
    if args.command == "on":
        sys.stdout.write(build_on_script())
        return 0
    return 1
