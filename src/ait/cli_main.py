from __future__ import annotations

from ait.cli import main
from ait.cli.upgrade import _upgrade_command, _upgrade_payload

__all__ = ["main", "_upgrade_command", "_upgrade_payload"]


if __name__ == "__main__":
    raise SystemExit(main())
