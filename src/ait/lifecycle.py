"""Single source of truth for intent status transitions.

V1 spec (ai-vcs-mvp-spec.md, Intent Transition Rules) defines only forward
transitions:

- `open -> running`: any attempt reaches `reported_status = running`
- `running -> finished`: any attempt reaches `verified_status = promoted`
- `* -> abandoned` / `* -> superseded`: explicit user command (not handled here)

Terminal states (`finished`, `abandoned`, `superseded`) must never be mutated
by automatic refresh. Non-terminal states must never regress (e.g., a
`running` intent must not fall back to `open` just because its attempts
finished without being promoted).

This module centralizes that rule so verifier, event handlers, and CLI flows
cannot drift.
"""

from __future__ import annotations

import sqlite3

from ait.db import update_intent_status

_TERMINAL_STATUSES: frozenset[str] = frozenset({"finished", "abandoned", "superseded"})


def refresh_intent_status(conn: sqlite3.Connection, intent_id: str) -> None:
    """Apply forward-only intent status transitions based on child attempts."""
    row = conn.execute(
        "SELECT status FROM intents WHERE id = ?",
        (intent_id,),
    ).fetchone()
    if row is None:
        return

    current = str(row["status"])
    if current in _TERMINAL_STATUSES:
        return

    attempts = conn.execute(
        """
        SELECT reported_status, verified_status
        FROM attempts
        WHERE intent_id = ?
        """,
        (intent_id,),
    ).fetchall()

    if any(str(item["verified_status"]) == "promoted" for item in attempts):
        update_intent_status(conn, intent_id, "finished")
        return

    if current == "open" and any(
        str(item["reported_status"]) == "running" for item in attempts
    ):
        update_intent_status(conn, intent_id, "running")
        return
