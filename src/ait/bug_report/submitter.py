from __future__ import annotations

import subprocess
import urllib.parse
import webbrowser
from dataclasses import dataclass
from shutil import which
from typing import Callable

REPO = "m24927605/ait"
URL_MAX = 7000


@dataclass
class SubmitResult:
    status: str          # "ok" | "deferred"
    method: str | None   # "gh" | "url" | None
    issue_url: str | None
    reason: str | None = None


def _gh_auth_ok() -> bool:
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    return "not logged in" not in (r.stderr or "").lower()


def _try_gh(title: str, body: str) -> SubmitResult | None:
    if not which("gh"):
        return None
    if not _gh_auth_ok():
        return None
    try:
        r = subprocess.run(
            ["gh", "issue", "create",
             "--repo", REPO,
             "--title", title,
             "--body-file", "-"],
            input=body, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return SubmitResult(status="ok", method="gh",
                        issue_url=(r.stdout or "").strip())


def build_prefill_url(title: str, body: str) -> str:
    q = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{REPO}/issues/new?{q}"


def _try_url(title: str, body: str,
             opener: Callable[[str], bool]) -> SubmitResult | None:
    url = build_prefill_url(title, body)
    if len(url) > URL_MAX:
        return None
    ok = bool(opener(url))
    if not ok:
        return None
    return SubmitResult(status="ok", method="url", issue_url=None)


def submit(
    *,
    title: str,
    body: str,
    browser_opener: Callable[[str], bool] = webbrowser.open,
) -> SubmitResult:
    gh = _try_gh(title, body)
    if gh is not None:
        return gh
    url = _try_url(title, body, browser_opener)
    if url is not None:
        return url
    reason = "body_too_long_or_no_browser"
    return SubmitResult(status="deferred", method=None,
                        issue_url=None, reason=reason)
