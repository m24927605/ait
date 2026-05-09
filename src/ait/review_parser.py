from __future__ import annotations

from dataclasses import dataclass
import json
import re


SEVERITY_VALUES = {"critical", "high", "medium", "low", "info"}
SEVERITY_ALIASES = {
    "informational": "info",
    "warning": "medium",
    "warn": "medium",
}
CONFIDENCE_VALUES = {"low", "medium", "high"}


class ReviewOutputParseError(ValueError):
    """Raised when reviewer output cannot be trusted as structured findings."""


@dataclass(frozen=True, slots=True)
class ParsedReviewFinding:
    severity: str
    blocking: bool
    path: str
    line: int | None
    hunk_ref: str | None
    title: str
    body: str
    evidence_ref: str | None
    suggested_test: str | None
    confidence: str


@dataclass(frozen=True, slots=True)
class ParsedReviewOutput:
    summary: str
    findings: tuple[ParsedReviewFinding, ...]


def parse_review_output(raw: str) -> ParsedReviewOutput:
    payload = _load_payload(raw)
    summary = _optional_text(payload.get("summary")) or ""
    findings_raw = payload.get("findings")
    if not isinstance(findings_raw, list):
        raise ReviewOutputParseError("review output must contain findings list")
    findings = tuple(_parse_finding(item, index=index) for index, item in enumerate(findings_raw))
    return ParsedReviewOutput(summary=summary, findings=findings)


def _load_payload(raw: str) -> dict[str, object]:
    text = raw.strip()
    if not text:
        raise ReviewOutputParseError("review output is empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _load_fenced_payload(text)
    if not isinstance(payload, dict):
        raise ReviewOutputParseError("review output must be a JSON object")
    return payload


def _load_fenced_payload(text: str) -> object:
    blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        raise ReviewOutputParseError("review output is not valid JSON")
    last_error: Exception | None = None
    for block in blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError as exc:
            last_error = exc
    raise ReviewOutputParseError("fenced review output is not valid JSON") from last_error


def _parse_finding(item: object, *, index: int) -> ParsedReviewFinding:
    if not isinstance(item, dict):
        raise ReviewOutputParseError(f"finding {index} must be an object")
    severity = _normalize_severity(item.get("severity"), index=index)
    path = _optional_text(item.get("path")) or ""
    title = _optional_text(item.get("title")) or ""
    body = _optional_text(item.get("body")) or ""
    if severity in {"critical", "high"}:
        missing = [
            name
            for name, value in (("path", path), ("title", title), ("body", body))
            if not value
        ]
        if missing:
            raise ReviewOutputParseError(
                f"{severity} finding {index} missing required fields: {', '.join(missing)}"
            )
    if not title:
        raise ReviewOutputParseError(f"finding {index} missing title")
    if not body:
        raise ReviewOutputParseError(f"finding {index} missing body")
    return ParsedReviewFinding(
        severity=severity,
        blocking=_bool_value(item.get("blocking"), default=severity in {"critical", "high"}),
        path=path,
        line=_optional_int(item.get("line"), field_name="line", index=index),
        hunk_ref=_optional_text(item.get("hunk_ref")),
        title=title,
        body=body,
        evidence_ref=_optional_text(item.get("evidence_ref")),
        suggested_test=_optional_text(item.get("suggested_test")),
        confidence=_normalize_confidence(item.get("confidence")),
    )


def _normalize_severity(value: object, *, index: int) -> str:
    text = _optional_text(value)
    if not text:
        raise ReviewOutputParseError(f"finding {index} missing severity")
    normalized = SEVERITY_ALIASES.get(text.lower(), text.lower())
    if normalized not in SEVERITY_VALUES:
        raise ReviewOutputParseError(f"finding {index} has unknown severity: {text}")
    return normalized


def _normalize_confidence(value: object) -> str:
    text = _optional_text(value)
    if not text:
        return "medium"
    lowered = text.lower()
    return lowered if lowered in CONFIDENCE_VALUES else "medium"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object, *, field_name: str, index: int) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ReviewOutputParseError(f"finding {index} {field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReviewOutputParseError(f"finding {index} {field_name} must be an integer") from exc


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ReviewOutputParseError("finding blocking must be a boolean")
