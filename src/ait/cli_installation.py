from __future__ import annotations

from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib


def package_version() -> str:
    try:
        return metadata.version("ait-vcs")
    except metadata.PackageNotFoundError:
        pyproject = next(
            (
                parent / "pyproject.toml"
                for parent in Path(__file__).resolve().parents
                if (parent / "pyproject.toml").is_file()
            ),
            None,
        )
        if pyproject is None:
            return "0+unknown"
        data = tomllib.loads(pyproject.read_text())
        return str(data.get("project", {}).get("version", "0+unknown"))

def _installation_payload() -> dict[str, object]:
    current_version = package_version()
    active_path = shutil.which("ait") or ""
    executable_path = _resolve_existing_path(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    candidates = _ait_path_candidates(os.environ.get("PATH", ""))
    candidate_payloads = [
        _ait_binary_payload(path, active_path=active_path, executable_path=executable_path)
        for path in candidates
    ]
    versions = {
        str(item.get("version"))
        for item in candidate_payloads
        if item.get("version") and item.get("version") != "unknown"
    }
    active = next((item for item in candidate_payloads if item.get("active")), None)
    conflicts = len(versions) > 1
    if active and active.get("version") not in ("", "unknown", current_version):
        conflicts = True
    payload = {
        "current_version": current_version,
        "active_path": active_path,
        "executable_path": executable_path,
        "python_executable": sys.executable,
        "source": _classify_ait_source(executable_path or active_path),
        "path_entries": candidate_payloads,
        "conflict": conflicts,
    }
    payload["next_steps"] = _installation_next_steps(payload)
    return payload

def _ait_path_candidates(path_value: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    executable = "ait.exe" if os.name == "nt" else "ait"
    for entry in path_value.split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / executable
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = _resolve_existing_path(str(candidate))
        key = resolved or str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(str(candidate))
    return candidates

def _ait_binary_payload(path: str, *, active_path: str, executable_path: str) -> dict[str, object]:
    resolved = _resolve_existing_path(path)
    return {
        "path": path,
        "resolved_path": resolved,
        "source": _classify_ait_source(resolved or path),
        "version": _ait_binary_version(path),
        "active": _same_path(path, active_path),
        "current_executable": _same_path(path, executable_path),
    }

def _ait_binary_version(path: str) -> str:
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (completed.stdout or completed.stderr).strip()
    match = re.search(r"\bait\s+([^\s]+)", text)
    return match.group(1) if match else "unknown"

def _classify_ait_source(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/node_modules/ait-vcs/" in normalized or normalized.endswith("/node_modules/ait-vcs/bin/ait.js"):
        return "npm"
    if _inside_npm_package(path):
        return "npm"
    if "/pipx/venvs/ait-vcs/" in normalized:
        return "pipx"
    if "/.venv/" in normalized or normalized.endswith("/venv/bin/ait"):
        return "venv"
    if "/site-packages/" in normalized or "/dist-packages/" in normalized:
        return "python"
    if normalized:
        return "path"
    return "unknown"

def _inside_npm_package(path: str) -> bool:
    try:
        current = Path(path).expanduser().resolve()
    except OSError:
        return False
    for parent in current.parents:
        package_json = parent / "package.json"
        if not package_json.is_file():
            continue
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") == "ait-vcs" and (parent / "bin" / "ait.js").is_file():
            return True
    return False

def _installation_next_steps(payload: dict[str, object]) -> list[str]:
    if not payload.get("conflict"):
        return []
    entries = [item for item in payload.get("path_entries", []) if isinstance(item, dict)]
    active_path = str(payload.get("active_path") or "")
    active = next((item for item in entries if item.get("active")), None)
    npm_entries = [item for item in entries if item.get("source") == "npm"]
    pipx_entries = [item for item in entries if item.get("source") == "pipx"]
    if pipx_entries and npm_entries:
        return [
            "pipx uninstall ait-vcs",
            "rehash",
            "ait --version",
        ]
    if active and active.get("source") != "npm" and npm_entries:
        npm_path = str(npm_entries[0].get("path"))
        return [
            f"put {str(Path(npm_path).parent)} before {str(Path(active_path).parent)} in PATH",
            "rehash",
            "ait --version",
        ]
    if pipx_entries:
        return [
            "remove older ait executables from PATH or uninstall the older package",
            "rehash",
            "ait --version",
        ]
    return [
        "keep only one ait executable on PATH, or put the preferred one first",
        "rehash",
        "ait --version",
    ]

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

def _format_upgrade(payload: dict[str, object]) -> str:
    lines = [
        "AIT upgrade",
        f"Source: {payload.get('source', 'unknown')}",
        f"Current version: {payload.get('current_version', 'unknown')}",
        "Command: " + " ".join(str(part) for part in payload.get("command", [])),
    ]
    if payload.get("dry_run"):
        lines.append("State: dry run")
    else:
        lines.append(f"Exit code: {payload.get('exit_code')}")
        lines.append("Next:")
        lines.append("- ait --version")
    return "\n".join(lines)

def _format_installation_alert_lines(installation: dict[str, object]) -> list[str]:
    if not installation.get("conflict"):
        return []
    lines = ["AIT install conflict: your shell has multiple ait commands or versions"]
    next_steps = installation.get("next_steps", [])
    if next_steps:
        lines.append("Next:")
        lines.extend(f"- {step}" for step in next_steps)
    return lines

def _format_installation_lines(
    installation: dict[str, object],
    *,
    include_next_steps: bool = True,
) -> list[str]:
    lines = [
        "AIT install:",
        f"- version: {installation.get('current_version', 'unknown')}",
        f"- source: {installation.get('source', 'unknown')}",
        f"- active path: {installation.get('active_path') or 'not found on PATH'}",
        f"- executable: {installation.get('executable_path') or 'unknown'}",
    ]
    entries = [item for item in installation.get("path_entries", []) if isinstance(item, dict)]
    if entries:
        lines.append("AIT commands on PATH:")
        for item in entries:
            marker = " active" if item.get("active") else ""
            lines.append(
                "- "
                f"{item.get('path')} "
                f"version={item.get('version', 'unknown')} "
                f"source={item.get('source', 'unknown')}"
                f"{marker}"
            )
    if installation.get("conflict"):
        lines.append("AIT install conflict: True")
    next_steps = installation.get("next_steps", []) if include_next_steps else []
    if next_steps:
        lines.append("AIT install next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return lines

def _resolve_existing_path(path: str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except OSError:
        return path

def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _resolve_existing_path(left) == _resolve_existing_path(right)
