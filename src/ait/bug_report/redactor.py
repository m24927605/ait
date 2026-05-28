from __future__ import annotations

import os
import re

_TOKEN_PATTERNS = (
    re.compile(r"gh[ps]_[A-Za-z0-9]{30,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SENSITIVE_FLAGS = frozenset({"--api-key", "--token", "--password"})


def redact(text: str) -> str:
    if not text:
        return text
    home = os.path.expanduser("~")
    if home and home in text:
        text = text.replace(home, "~")
    for pat in _TOKEN_PATTERNS:
        text = pat.sub("[REDACTED_TOKEN]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    return text


def redact_argv(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            out.append("[REDACTED]")
            skip_next = False
            continue
        if "=" in arg:
            flag, _, _ = arg.partition("=")
            if flag in _SENSITIVE_FLAGS:
                out.append(f"{flag}=[REDACTED]")
                continue
        if arg in _SENSITIVE_FLAGS:
            out.append(arg)
            # Only mark next for redaction if there IS a next.
            if i + 1 < len(argv):
                skip_next = True
            continue
        out.append(arg)
    return out
