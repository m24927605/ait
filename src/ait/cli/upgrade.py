from __future__ import annotations

import ait.cli as _compat
from ait.cli_installation import _format_upgrade


def _installation_payload() -> dict[str, object]:
    return _compat._installation_payload()


def _subprocess():
    return _compat.subprocess


def _shutil():
    return _compat.shutil


def _sys():
    return _compat.sys


def handle(args, repo_root, parser=None) -> int:
    del repo_root, parser
    try:
        payload = _upgrade_payload(dry_run=args.dry_run, output_format=args.format)
    except ValueError as exc:
        print(f"error: {exc}", file=_sys().stderr)
        return 2
    if args.format == "json":
        import json

        print(json.dumps(payload, indent=2))
    else:
        print(_format_upgrade(payload))
    return int(payload.get("exit_code", 1))


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
        completed = _subprocess().run(command, capture_output=True, text=True, check=False)
        payload.update(
            {
                "ran": True,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        return payload
    completed = _subprocess().run(command, check=False)
    payload.update({"ran": True, "exit_code": completed.returncode})
    return payload


def _upgrade_command(installation: dict[str, object]) -> list[str]:
    source = str(installation.get("source") or "unknown")
    if source == "pipx":
        if _shutil().which("pipx") is None:
            raise ValueError("pipx install detected, but pipx is not on PATH")
        return ["pipx", "upgrade", "ait-vcs"]
    if source == "npm":
        if _shutil().which("npm") is None:
            raise ValueError("npm install detected, but npm is not on PATH")
        return ["npm", "install", "-g", "ait-vcs"]
    if source in {"venv", "python", "path"}:
        return [_sys().executable, "-m", "pip", "install", "-U", "ait-vcs"]
    raise ValueError(
        f"unsupported ait install source for automatic upgrade: {source}; "
        "use pipx upgrade ait-vcs or python -m pip install -U ait-vcs"
    )
