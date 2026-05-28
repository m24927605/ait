from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Callable

from ait.bug_report import collector as collector_mod
from ait.bug_report.config import env_disabled, load_prefs
from ait.bug_report.safety import _safe

_SKIP = (KeyboardInterrupt, SystemExit, BrokenPipeError)

_PREV_HOOK: Callable[..., Any] | None = None


@_safe
def install() -> None:
    """Chain a new excepthook that records to the collector then delegates."""
    if env_disabled():
        return
    if load_prefs().mode == "never":
        return

    global _PREV_HOOK
    if _PREV_HOOK is not None:
        return  # already installed
    _PREV_HOOK = sys.excepthook
    sys.excepthook = _hook


@_safe
def uninstall() -> None:
    global _PREV_HOOK
    if _PREV_HOOK is None:
        return
    sys.excepthook = _PREV_HOOK
    _PREV_HOOK = None


def reset_for_tests() -> None:
    """Test-only helper to clear the installed hook state between cases."""
    global _PREV_HOOK
    _PREV_HOOK = None


def _hook(exc_type, exc_value, tb) -> None:
    try:
        if not isinstance(exc_value, _SKIP):
            now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            collector_mod.collector().record(
                category="excepthook",
                exc=exc_value,
                context=None,
                now=now,
            )
    except Exception:
        # Never let our hook break the previous hook.
        pass
    finally:
        if _PREV_HOOK is not None:
            _PREV_HOOK(exc_type, exc_value, tb)
