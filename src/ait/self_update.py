"""Self-update implementation for the `ait` standalone binary.

Public entry point: run(args) called by cli/self_update.py.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib as _hashlib
import json as _json
import os as _os
import sys
import tempfile
import urllib.request
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


class ChecksumMismatch(RuntimeError):
    pass


def download_and_verify(url: str, *, expected_sha256: str,
                        timeout: int = 60) -> bytes:
    """Download `url` and verify its sha256. Returns the bytes on match,
    raises ChecksumMismatch otherwise."""
    with urllib.request.urlopen(url, timeout=timeout) as fh:
        content = fh.read()
    actual = _hashlib.sha256(content).hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise ChecksumMismatch(
            f"sha256 mismatch: expected {expected_sha256!r}, got {actual!r}"
        )
    return content


def atomic_replace(target: Path, content: bytes) -> None:
    """Write `content` to a sibling of `target` then atomically rename.

    Atomic on POSIX same-filesystem (os.replace). Tmp is cleaned up
    on any failure.
    """
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(dir=str(target_dir), prefix=".ait.new.")
    tmp = Path(tmp_str)
    try:
        with _os.fdopen(fd, "wb") as fh:
            fh.write(content)
        _os.chmod(tmp_str, 0o755)
        _os.replace(tmp_str, str(target))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


class InstallPathNotWritable(RuntimeError):
    pass


def check_install_path_writable(target: Path) -> None:
    """Raise InstallPathNotWritable if we can't write into target.parent."""
    if not _os.access(str(target.parent), _os.W_OK):
        raise InstallPathNotWritable(
            f"cannot write to {target.parent}\n"
            f"re-run with sudo, or move ait to a user-owned path."
        )


def refuse_with_message(method: str, *, stdout=None) -> int:
    """Print the right refusal message and return exit code 1."""
    out = stdout if stdout is not None else sys.stdout
    if method == "pip":
        print(
            "You installed ait via pip. Run `pip install --upgrade ait-vcs` instead.",
            file=out,
        )
    elif method == "brew":
        print(
            "You installed ait via Homebrew. Run `brew upgrade ait` instead.",
            file=out,
        )
    else:
        print(f"ait self-update is not supported for install method: {method}",
              file=out)
    return 1
