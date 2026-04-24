from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.db import (
    NewAttempt,
    NewIntent,
    connect_db,
    insert_attempt,
    insert_intent,
    run_migrations,
)
from ait.idresolver import (
    IdResolutionError,
    resolve_attempt_id,
    resolve_intent_id,
)


class IdResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:long-nonce:01ABCDEFGHJK",
                repo_id="repo:long-nonce",
                title="First",
                created_at="2026-04-24T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_intent(
            self.conn,
            NewIntent(
                id="repo:long-nonce:01ABCDEFGHJM",
                repo_id="repo:long-nonce",
                title="Second",
                created_at="2026-04-24T00:01:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            self.conn,
            NewAttempt(
                id="repo:long-nonce:01ZZZZZZZZZZ",
                intent_id="repo:long-nonce:01ABCDEFGHJK",
                agent_id="codex:main",
                workspace_ref="/tmp/a",
                base_ref_oid="0" * 40,
                started_at="2026-04-24T00:02:00Z",
                ownership_token="t",
            ),
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_full_id_resolves_to_itself(self) -> None:
        self.assertEqual(
            "repo:long-nonce:01ABCDEFGHJK",
            resolve_intent_id(self.conn, "repo:long-nonce:01ABCDEFGHJK"),
        )

    def test_unique_suffix_resolves_to_full_id(self) -> None:
        self.assertEqual(
            "repo:long-nonce:01ABCDEFGHJK",
            resolve_intent_id(self.conn, "01ABCDEFGHJK"),
        )

    def test_ambiguous_prefix_surface_candidates(self) -> None:
        # "01ABCDEFGHJ" matches both seeded intents (K and M suffix).
        with self.assertRaises(IdResolutionError) as raised:
            resolve_intent_id(self.conn, "01ABCDEFGHJ")

        message = str(raised.exception)
        self.assertIn("ambiguous", message.lower())
        self.assertIn("01ABCDEFGHJK", message)
        self.assertIn("01ABCDEFGHJM", message)

    def test_no_match_raises(self) -> None:
        with self.assertRaises(IdResolutionError):
            resolve_intent_id(self.conn, "01NOPE")

    def test_empty_input_raises(self) -> None:
        with self.assertRaises(IdResolutionError):
            resolve_intent_id(self.conn, "")
        with self.assertRaises(IdResolutionError):
            resolve_intent_id(self.conn, "   ")

    def test_resolves_attempt_by_suffix(self) -> None:
        self.assertEqual(
            "repo:long-nonce:01ZZZZZZZZZZ",
            resolve_attempt_id(self.conn, "01ZZZZZZZZZZ"),
        )

    def test_attempt_resolver_does_not_cross_tables(self) -> None:
        # The intent ULID suffix exists in intents but not in attempts.
        with self.assertRaises(IdResolutionError):
            resolve_attempt_id(self.conn, "01ABCDEFGHJK")


if __name__ == "__main__":
    unittest.main()
