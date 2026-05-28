from __future__ import annotations

import datetime as dt
import functools
import traceback
from typing import Any, Callable, TypeVar

from ait.bug_report.config import state_dir

T = TypeVar("T")


def _log_path():
    return state_dir() / "internal_errors.log"


def _log_internal_error(exc: BaseException) -> None:
    """Append a traceback to internal_errors.log. Never raises."""
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"--- {ts} ---\n{tb}\n")
    except Exception:
        # Truly cannot do anything if even the log fails.
        pass


def _safe(fn: Callable[..., T]) -> Callable[..., T | None]:
    """Wrap fn so any exception is logged and converted to None.

    Never re-enters the bug_report collector to avoid infinite recursion.
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T | None:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            _log_internal_error(exc)
            return None
    return wrapper
