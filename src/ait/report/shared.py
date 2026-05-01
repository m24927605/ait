from __future__ import annotations



import json

import re

def _json_list(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)

def _search_blob(*parts: str) -> str:
    return " ".join(part for part in parts if part).lower()

def _css_token(value: str) -> str:
    token = "".join(char if char.isalnum() else "_" for char in value.lower()).strip("_")
    return token or "unknown"

def _short_id(value: str) -> str:
    return value.rsplit(":", 1)[-1][:8]



__all__ = [

    "_css_token",

    "_json_list",

    "_search_blob",

    "_short_id",

]
