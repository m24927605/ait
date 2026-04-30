"""Single source of truth for intent status transitions.

V1 spec (ai-vcs-mvp-spec.md, Intent Transition Rules) defines only forward
transitions:

- `open -> running`: any attempt reaches `reported_status = running`
- `open|running -> finished`: any attempt reaches `verified_status =
  succeeded` or `promoted`
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

_TERMINAL_STATUSES: frozenset[str] = frozenset({"finished", "abandoned", "superseded"})


def refresh_intent_status(conn: sqlite3.Connection, intent_id: str) -> None:
    """Apply forward-only intent status transitions based on child attempts."""
    with conn:
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

        next_status: str | None = None
        if any(str(item["verified_status"]) in {"succeeded", "promoted"} for item in attempts):
            next_status = "finished"
        elif current == "open" and any(
            str(item["reported_status"]) == "running" for item in attempts
        ):
            next_status = "running"

        if next_status is None:
            return
        conn.execute(
            """
            UPDATE intents
            SET status = ?
            WHERE id = ?
              AND status NOT IN ('finished', 'abandoned', 'superseded')
            """,
            (next_status, intent_id),
        )
