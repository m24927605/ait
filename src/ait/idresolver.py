"""Resolve user-supplied intent / attempt identifiers to full IDs.

V1 object IDs have the form `<repo_id>:<ulid>` where `<repo_id>` is itself
`<root_commit_oid>:<install_nonce>`, so a full ID is ~100 characters — not
realistic to type or paste by hand. To keep the CLI usable this module
accepts either a full ID or a unique suffix (typically the tail of the
ULID) and resolves to the canonical stored ID.

Rules:

- A string that matches a full `id` column exactly is returned unchanged.
- Otherwise the string is treated as a substring and looked up with
  ``id LIKE '%<substring>%'``. Users can paste any recognisable chunk of
  the ULID (prefix, suffix, or middle).
- Zero matches raises ``ValueError``.
- More than one match raises ``ValueError`` and lists the candidates so the
  caller can pick a longer or more specific fragment.

Resolution is always scoped to a single repository (one `.ait/` store) so
collisions across unrelated repositories cannot happen here.
"""

from __future__ import annotations

import sqlite3


class IdResolutionError(ValueError):
    """Raised when a user-supplied identifier cannot be resolved uniquely."""


def resolve_intent_id(conn: sqlite3.Connection, given: str) -> str:
    return _resolve(conn, "intents", "intent", given)


def resolve_attempt_id(conn: sqlite3.Connection, given: str) -> str:
    return _resolve(conn, "attempts", "attempt", given)


def _resolve(
    conn: sqlite3.Connection,
    table: str,
    subject: str,
    given: str,
) -> str:
    if not given or not given.strip():
        raise IdResolutionError(f"{subject} id must not be empty")

    exact = conn.execute(
        f"SELECT id FROM {table} WHERE id = ?",
        (given,),
    ).fetchone()
    if exact is not None:
        return str(exact["id"])

    rows = conn.execute(
        f"SELECT id FROM {table} WHERE id LIKE ?",
        (f"%{given}%",),
    ).fetchall()
    if not rows:
        raise IdResolutionError(f"no {subject} matches: {given}")
    if len(rows) > 1:
        candidates = ", ".join(str(row["id"]) for row in rows)
        raise IdResolutionError(
            f"{subject} id {given!r} is ambiguous; candidates: {candidates}"
        )
    return str(rows[0]["id"])
