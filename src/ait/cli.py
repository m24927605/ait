from __future__ import annotations

import shutil
import subprocess
import sys

from ait import cli_main as _cli_main
from ait.cli_helpers import _format_status
from ait.cli_installation import _classify_ait_source, _installation_payload, package_version
from ait.cli_parser import build_parser


def main() -> int:
    _cli_main._installation_payload = _installation_payload
    _cli_main._upgrade_payload = _upgrade_payload
    _cli_main._upgrade_command = _upgrade_command
    _cli_main.shutil = shutil
    _cli_main.subprocess = subprocess
    return _cli_main.main()


def _upgrade_payload(*, dry_run: bool, output_format: str) -> dict[str, object]:
    installation = _installation_payload()
    command = _upgrade_command(installation)
    payload: dict[str, object] = {
        "dry_run": dry_run,
        "source": installation.get("source", "unknown"),
        "current_version": installation.get("current_version", "unknown"),
        "command": command,
        "installation": installation,
    }
    if dry_run:
        payload.update({"exit_code": 0, "ran": False})
        return payload
    if output_format == "json":
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        payload.update(
            {
                "ran": True,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        return payload
    completed = subprocess.run(command, check=False)
    payload.update({"ran": True, "exit_code": completed.returncode})
    return payload


def _upgrade_command(installation: dict[str, object]) -> list[str]:
    source = str(installation.get("source") or "unknown")
    if source == "pipx":
        if shutil.which("pipx") is None:
            raise ValueError("pipx install detected, but pipx is not on PATH")
        return ["pipx", "upgrade", "ait-vcs"]
    if source == "npm":
        if shutil.which("npm") is None:
            raise ValueError("npm install detected, but npm is not on PATH")
        return ["npm", "install", "-g", "ait-vcs"]
    if source in {"venv", "python", "path"}:
        return [sys.executable, "-m", "pip", "install", "-U", "ait-vcs"]
    raise ValueError(
        f"unsupported ait install source for automatic upgrade: {source}; "
        "use pipx upgrade ait-vcs or python -m pip install -U ait-vcs"
    )


if __name__ == "__main__":
    raise SystemExit(main())
