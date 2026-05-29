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
