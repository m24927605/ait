"""Attempt-entry banner printed to stderr at session start.

See docs/superpowers/specs/2026-05-30-ux-friction-fix-design.md § P0.3.
Width fixed at 60 chars. Skip when stderr is not a TTY OR
AIT_NO_BANNER=1.
"""
from __future__ import annotations

import os
import re
import sys
from typing import TextIO

_BOX_WIDTH = 60
_INNER = _BOX_WIDTH - 2  # account for │ … │ frame
_HORIZ = "─"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _ansi(code: str, text: str, *, enable: bool) -> str:
    if not enable:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _truncate_visible(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def render_attempt_banner(
    *,
    attempt_id: str,
    workspace_rel: str,
    head: str,
    target: str,
    use_color: bool = False,
) -> str:
    """Return the 4-line banner (with framing) as a single string.

    `attempt_id` may be a full ULID or shorter; the renderer truncates
    a long id to its first 9 visible characters.
    """
    short_id = attempt_id.split(":")[-1][:9]
    header_text = f" AIT attempt {short_id} "
    header_fill = max(0, _BOX_WIDTH - 3 - len(header_text))
    top = "┌─" + header_text + _HORIZ * header_fill + "┐"
    bottom = "└" + _HORIZ * (_BOX_WIDTH - 2) + "┘"

    body_lines = [
        f"workspace: {workspace_rel}",
        f"HEAD: {head} · target: {target}",
        f"Commits land on `{target}` only after `ait apply`.",
        "Bypass once: AIT_BYPASS=1 <agent> …",
        "Bypass shell: `ait off`  ·  re-enable: `ait on`",
    ]

    rendered_body = []
    for line in body_lines:
        line = _truncate_visible(line, _INNER - 1)
        if use_color:
            line = line.replace(
                "detached", _ansi("33", "detached", enable=True)
            )
            if "`" in line:
                pre, _, rest = line.partition("`")
                code, _, post = rest.partition("`")
                line = pre + _ansi("1", code, enable=True) + post
        visible = _visible_len(line)
        pad = max(0, _INNER - 1 - visible)
        rendered_body.append(f"│ {line}{' ' * pad}│")

    return "\n".join([top, *rendered_body, bottom]) + "\n"


def print_attempt_banner(
    *,
    stream: TextIO | None = None,
    attempt_id: str,
    workspace_rel: str,
    head: str,
    target: str,
) -> None:
    """Print the banner to `stream` (default stderr) if conditions allow.

    Skip when the stream is not a TTY or when AIT_NO_BANNER is set.
    """
    out = stream if stream is not None else sys.stderr
    try:
        is_tty = out.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    if not is_tty:
        return
    if os.environ.get("AIT_NO_BANNER", "") not in ("", "0"):
        return
    text = render_attempt_banner(
        attempt_id=attempt_id,
        workspace_rel=workspace_rel,
        head=head,
        target=target,
        use_color=True,
    )
    out.write(text)
    out.flush()
