from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ait.bug_report.fingerprint import Frame, fingerprint


@dataclass
class CollectedEntry:
    category: str
    exc_type: str
    exc_message: str
    frames: list[Frame]
    fingerprint: str
    count: int
    context: dict[str, Any] | None
    first_recorded_at: str
    last_recorded_at: str


def _extract_frames(exc: BaseException) -> list[Frame]:
    tb = exc.__traceback__
    frames: list[Frame] = []
    while tb is not None:
        frames.append(Frame(
            filename=tb.tb_frame.f_code.co_filename,
            function=tb.tb_frame.f_code.co_name,
        ))
        tb = tb.tb_next
    # Deepest frame first.
    frames.reverse()
    return frames


class Collector:
    def __init__(self, max_entries: int = 20) -> None:
        self._max = max_entries
        self._entries: dict[tuple[str, str], CollectedEntry] = {}
        self._order: list[tuple[str, str]] = []
        self.truncated = False

    def record(
        self,
        *,
        category: str,
        exc: BaseException,
        context: dict[str, Any] | None,
        now: str,
    ) -> None:
        frames = _extract_frames(exc)
        exc_type = type(exc).__name__
        fp = fingerprint(exc_type, frames)
        key = (category, fp)
        existing = self._entries.get(key)
        if existing is not None:
            existing.count += 1
            existing.last_recorded_at = now
            return
        entry = CollectedEntry(
            category=category,
            exc_type=exc_type,
            exc_message=str(exc),
            frames=frames,
            fingerprint=fp,
            count=1,
            context=context,
            first_recorded_at=now,
            last_recorded_at=now,
        )
        if len(self._entries) >= self._max:
            # Drop oldest by insertion order.
            oldest = self._order.pop(0)
            self._entries.pop(oldest, None)
            self.truncated = True
        self._entries[key] = entry
        self._order.append(key)

    def entries(self) -> list[CollectedEntry]:
        return [self._entries[key] for key in self._order]


_GLOBAL: Collector | None = None


def collector() -> Collector:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Collector()
    return _GLOBAL


def reset_for_tests() -> None:
    """Test-only helper to clear the singleton between cases."""
    global _GLOBAL
    _GLOBAL = None
