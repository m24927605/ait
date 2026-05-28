from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1
VALID_MODES = ("unset", "ask", "always", "never")


@dataclass
class BugReportPrefs:
    mode: str = "unset"
    first_setup_at: str | None = None
    last_prompted_at: str | None = None
    include_tier2: bool = True
    include_tier3: bool = False


def _xdg_config_home() -> Path:
    val = os.environ.get("XDG_CONFIG_HOME")
    if val:
        return Path(val)
    return Path.home() / ".config"


def _xdg_state_home() -> Path:
    val = os.environ.get("XDG_STATE_HOME")
    if val:
        return Path(val)
    return Path.home() / ".local" / "state"


def config_path() -> Path:
    return _xdg_config_home() / "ait" / "config.json"


def state_dir() -> Path:
    return _xdg_state_home() / "ait" / "bug_reports"


def env_disabled() -> bool:
    return os.environ.get("AIT_BUG_REPORT", "").strip().lower() == "never"


def load_prefs() -> BugReportPrefs:
    p = config_path()
    if not p.exists():
        return BugReportPrefs()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return BugReportPrefs()
    block = data.get("bug_report") or {}
    mode = block.get("mode", "unset")
    if mode not in VALID_MODES:
        mode = "unset"
    return BugReportPrefs(
        mode=mode,
        first_setup_at=block.get("first_setup_at"),
        last_prompted_at=block.get("last_prompted_at"),
        include_tier2=bool(block.get("include_tier2", True)),
        include_tier3=bool(block.get("include_tier3", False)),
    )


def save_prefs(prefs: BugReportPrefs) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.setdefault("schema_version", SCHEMA_VERSION)
    existing["bug_report"] = asdict(prefs)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
