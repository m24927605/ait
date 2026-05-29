"""Self-update implementation for the `ait` standalone binary.

Public entry point: run(args) called by cli/self_update.py.
"""
from __future__ import annotations

import sys
from pathlib import Path


def install_method() -> str:
    """Detect how this ait was installed.

    Returns 'pip' | 'brew' | 'binary' | 'unknown'.
    """
    if not getattr(sys, "frozen", False):
        return "pip"
    exe = str(Path(sys.executable).resolve()) if sys.executable else ""
    # Homebrew Cellar layout: .../Cellar/ait/<version>/bin/ait
    if "/Cellar/" in exe and "/ait/" in exe:
        return "brew"
    return "binary"


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if equal, 1 if a > b.

    Accepts either `1.5.0` or `v1.5.0` forms. Raises ValueError on malformed
    input. AIT versions are always MAJOR.MINOR.PATCH.
    """
    def _parse(s: str) -> tuple[int, int, int]:
        s = s.lstrip("v")
        parts = s.split(".")
        if len(parts) != 3:
            raise ValueError(f"not a 3-part semver: {s!r}")
        try:
            return tuple(int(p) for p in parts)  # type: ignore[return-value]
        except ValueError:
            raise ValueError(f"non-integer component in {s!r}")

    pa = _parse(a)
    pb = _parse(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0
