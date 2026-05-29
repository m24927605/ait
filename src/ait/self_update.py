"""Self-update implementation for the `ait` standalone binary.

Public entry point: run(args) called by cli/self_update.py.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
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


_CACHE_TTL_SECONDS = 3600


def _xdg_state_dir() -> Path:
    val = _os.environ.get("XDG_STATE_HOME")
    if val:
        return Path(val)
    return Path.home() / ".local" / "state"


def cache_path() -> Path:
    return _xdg_state_dir() / "ait" / "self_update_cache.json"


def save_cache(latest: dict, *, now: _dt.datetime) -> None:
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "fetched_at": now.isoformat().replace("+00:00", "Z"),
        "ttl_seconds": _CACHE_TTL_SECONDS,
        "latest": latest,
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(_json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def load_cache() -> dict | None:
    p = cache_path()
    if not p.exists():
        return None
    try:
        return _json.loads(p.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return None


def is_cache_fresh(*, now: _dt.datetime) -> bool:
    cached = load_cache()
    if cached is None:
        return False
    fetched_at_str = cached.get("fetched_at", "")
    try:
        fetched_at = _dt.datetime.fromisoformat(
            fetched_at_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    ttl = int(cached.get("ttl_seconds", _CACHE_TTL_SECONDS))
    return (now - fetched_at).total_seconds() < ttl
