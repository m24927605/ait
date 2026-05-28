from __future__ import annotations

import datetime as dt
from typing import Any

from ait.bug_report import collector as collector_mod
from ait.bug_report import excepthook as excepthook_mod
from ait.bug_report.config import env_disabled, load_prefs
from ait.bug_report.safety import _safe


@_safe
def install_excepthook() -> None:
    excepthook_mod.install()


@_safe
def report_internal_error(
    *,
    category: str,
    exc: BaseException,
    context: dict[str, Any] | None = None,
    user_facing: str | None = None,
) -> None:
    if env_disabled():
        return
    if load_prefs().mode == "never":
        return
    if exc is None:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    collector_mod.collector().record(
        category=category, exc=exc, context=context, now=now,
    )


@_safe
def flush_at_exit() -> None:
    # Filled in next task (Task 14). For now, no-op stub.
    return
