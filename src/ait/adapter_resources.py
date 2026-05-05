from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
import shlex
import sys

from ait.adapter_models import AdapterError


def _resource_exists(adapter_dir: str, name: str) -> bool:
    try:
        return resources.files("ait").joinpath("resources", adapter_dir, name).is_file()
    except Exception:
        return False


def _read_adapter_resource(adapter_dir: str, name: str) -> str:
    return (
        resources.files("ait")
        .joinpath("resources", adapter_dir, name)
        .read_text(encoding="utf-8")
    )


def _read_claude_resource(name: str) -> str:
    return _read_adapter_resource("claude-code", name)


def _resolve_target(repo_root: Path, target: str | Path) -> Path:
    path = Path(target)
    if path.is_absolute():
        return path
    return repo_root / path


def _claude_code_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"$CLAUDE_PROJECT_DIR/.ait/adapters/claude-code/claude_code_hook.py"'
    )
    tool_events = {
        "matcher": "Read|Grep|Glob|LS|Write|Edit|MultiEdit|NotebookEdit|Bash",
        "hooks": [{"type": "command", "command": command}],
    }
    session_events = {"hooks": [{"type": "command", "command": command}]}
    return {
        "hooks": {
            "SessionStart": [session_events],
            "PostToolUse": [tool_events],
            "PostToolUseFailure": [tool_events],
            "Stop": [session_events],
            "SessionEnd": [session_events],
        }
    }


def _codex_hooks_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"$CODEX_PROJECT_DIR/.ait/adapters/codex/codex_hook.py"'
    )
    tool_events = {
        "matcher": "Read|Grep|Glob|LS|Write|Edit|MultiEdit|NotebookEdit|Bash|shell|apply_patch",
        "hooks": [{"type": "command", "command": command}],
    }
    session_events = {"hooks": [{"type": "command", "command": command}]}
    return {
        "hooks": {
            "SessionStart": [session_events],
            "PostToolUse": [tool_events],
            "PostToolUseFailure": [tool_events],
            "Stop": [session_events],
            "SessionEnd": [session_events],
        }
    }


def _gemini_settings() -> dict[str, object]:
    command = (
        f"{shlex.quote(sys.executable)} "
        '"$GEMINI_PROJECT_DIR/.ait/adapters/gemini/gemini_hook.py"'
    )
    session_events = {"hooks": [{"type": "command", "command": command}]}
    return {
        "hooks": {
            "SessionStart": [session_events],
            "AfterTool": [session_events],
            "AfterToolFailure": [session_events],
            "Stop": [session_events],
        }
    }


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AdapterError(f"settings file must contain a JSON object: {path}")
    return data


def _merge_settings(existing: dict[str, object], generated: dict[str, object]) -> dict[str, object]:
    merged = dict(existing)
    existing_hooks = merged.setdefault("hooks", {})
    if not isinstance(existing_hooks, dict):
        raise AdapterError("settings hooks must be a JSON object")

    generated_hooks = generated.get("hooks", {})
    if not isinstance(generated_hooks, dict):
        raise AdapterError("generated hooks must be a JSON object")

    for event_name, generated_entries in generated_hooks.items():
        if not isinstance(generated_entries, list):
            raise AdapterError(f"generated hook entries must be a list: {event_name}")
        existing_entries = existing_hooks.setdefault(event_name, [])
        if not isinstance(existing_entries, list):
            raise AdapterError(f"settings hook entries must be a list: {event_name}")
        for entry in generated_entries:
            if entry not in existing_entries:
                existing_entries.append(entry)
    return merged
