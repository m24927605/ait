from __future__ import annotations

import shutil
import subprocess
import sys

from ait.cli_installation import (
    _classify_ait_source,
    _format_installation_alert_lines,
    _format_installation_lines,
    _installation_next_steps,
    _installation_payload,
    package_version,
)
from ait.cli.status_helpers import _format_status

from .main import main
from .upgrade import _format_upgrade, _upgrade_command, _upgrade_payload

__all__ = [
    "main",
    "package_version",
    "build_parser",
    "_classify_ait_source",
    "_format_status",
    "_installation_payload",
    "_upgrade_payload",
    "_upgrade_command",
    "subprocess",
    "shutil",
    "sys",
]


def build_parser():
    from ait.cli_parser import build_parser as _build_parser

    return _build_parser()
