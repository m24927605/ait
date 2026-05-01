from __future__ import annotations

import re


ANSI_CONTROL_RE = re.compile(
    r"""
    \x1b\][^\x07\x1b]*(?:\x07|\x1b\\)  # OSC
    |
    \x1b[@-Z\\-_]                       # 7-bit C1
    |
    \x1b\[[0-?]*[ -/]*[@-~]             # CSI
    """,
    re.VERBOSE,
)


def normalize_transcript(text: str, *, adapter: str | None = None) -> str:
    cleaned = strip_terminal_control(text)
    lines = cleaned.splitlines()
    if adapter == "codex":
        lines = _normalize_codex_lines(lines)
    else:
        lines = _normalize_common_lines(lines)
    return "\n".join(lines).strip() + ("\n" if lines else "")


def strip_terminal_control(text: str) -> str:
    return ANSI_CONTROL_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def _normalize_common_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    previous = ""
    for raw_line in lines:
        line = _clean_line(raw_line)
        if not line:
            if normalized and normalized[-1]:
                normalized.append("")
            continue
        if _is_progress_noise(line):
            continue
        if line == previous:
            continue
        normalized.append(line)
        previous = line
    while normalized and not normalized[-1]:
        normalized.pop()
    return normalized


def _normalize_codex_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    previous = ""
    for raw_line in lines:
        line = _clean_line(raw_line)
        if not line:
            if normalized and normalized[-1]:
                normalized.append("")
            continue
        if _is_codex_noise(line):
            continue
        line = _dedupe_repeated_words(line)
        if not line or line == previous:
            continue
        normalized.append(line)
        previous = line
    while normalized and not normalized[-1]:
        normalized.pop()
    return normalized


def _clean_line(line: str) -> str:
    return re.sub(r"[ \t]+", " ", line).strip()


def _is_progress_noise(line: str) -> bool:
    compact = line.replace(" ", "")
    if compact in {"Working", "Thinking", "Starting", "StartingMCPservers"}:
        return True
    if re.fullmatch(r"(Working|Thinking|Starting|Start|Sta|St|S|W|Wo|Wor|Work|Worki|Workin)+", compact):
        return True
    return False


def _is_codex_noise(line: str) -> bool:
    if _is_progress_noise(line):
        return True
    if "esc to interrupt" in line and "Working" in line:
        return True
    if line.startswith("•Working") or line.startswith("• Working"):
        return True
    if line.startswith("› Summarize recent commits"):
        return True
    if "Starting MCP servers" in line:
        return True
    if re.fullmatch(r"[SStaStartingWorkinrg•\d ]{3,}", line):
        return True
    return False


def _dedupe_repeated_words(line: str) -> str:
    for word in ("Working", "Starting", "Generating", "Loading", "Thinking"):
        line = re.sub(rf"\b({word})(?:\1)+\b", r"\1", line)
    return line
