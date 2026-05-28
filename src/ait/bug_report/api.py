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
    from ait.bug_report.flush import decide_prompt
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if env_disabled() or load_prefs().mode == "never":
        return
    decision = decide_prompt(now=now)
    if decision.action != "prompt":
        return
    # Delegate prompting + submission to CLI layer (Task 17 wires this).
    # For now, defer interactive flows: write to pending queue so
    # `ait bug-report --replay` can ship them.
    from ait.bug_report.pending_queue import PendingReport, enqueue
    from ait.bug_report.builder import build_issue, BuildInput
    inp = _build_default_input(decision.to_prompt)
    issue = build_issue(inp)
    enqueue(PendingReport(
        fingerprint=issue.primary_fingerprint,
        title=issue.title,
        body=issue.body,
        category=decision.to_prompt[0].category,
        created_at=now,
    ))


def _build_default_input(entries):
    import platform, sys
    from ait.bug_report.builder import BuildInput
    try:
        from ait import __version__ as ait_version
    except Exception:
        ait_version = "unknown"
    prefs = load_prefs()
    return BuildInput(
        entries=entries,
        ait_version=ait_version,
        python_version=platform.python_version(),
        os_arch=f"{platform.system().lower()}/{platform.machine()}",
        argv=list(sys.argv),
        include_tier2=prefs.include_tier2,
        include_tier3=prefs.include_tier3,
        install_nonce="",
        daemon_log_tail="",
        daemon_state="",
        phase="",
        env_vars={},
        extra_transcript=None,
        repo_id=None,
    )
