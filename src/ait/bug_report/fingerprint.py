from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    filename: str
    function: str


def fingerprint(exc_type: str, frames: list[Frame]) -> str:
    """Return 'fp:' + 8-hex SHA256 over (exc_type, top-3 (basename, fn))."""
    parts = [exc_type]
    for frame in frames[:3]:
        parts.append(f"{os.path.basename(frame.filename)}:{frame.function}")
    blob = "\n".join(parts).encode("utf-8")
    return "fp:" + hashlib.sha256(blob).hexdigest()[:8]
