from __future__ import annotations

import re


REDACTION_MARKER = "[REDACTED]"

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"\b(TOKEN|SECRET|PASSWORD|KEY)=([^\s'\"]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|KEY))=([^\s'\"]+)",
        re.IGNORECASE,
    ),
)


def redact_text(text: str) -> tuple[str, bool]:
    redacted = text
    changed = False
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted, count = pattern.subn(lambda match: f"{match.group(1)}={REDACTION_MARKER}", redacted)
        else:
            redacted, count = pattern.subn(REDACTION_MARKER, redacted)
        changed = changed or count > 0
    return redacted, changed


def has_redactions(text: str) -> bool:
    return REDACTION_MARKER in text
