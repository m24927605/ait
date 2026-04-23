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
    update_attempt,
    update_intent_status,
)
from ait.lifecycle import refresh_intent_status


class IntentLifecycleForwardOnlyTests(unittest.TestCase):
    """Regression coverage for the forward-only intent status rule.

    Spec: docs/ai-vcs-mvp-spec.md, Intent Transition Rules.
    """

    def setUp(self) -> None:
        self.conn = connect_db(":memory:")
        run_migrations(self.conn)
        self._seed_intent("repo:01INTENT", status="open")

    def tearDown(self) -> None:
        self.conn.close()

    def test_running_intent_does_not_regress_when_all_attempts_failed(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "running")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="crashed",
            verified_status="failed",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("running", self._intent_status("repo:01INTENT"))

    def test_running_intent_does_not_regress_when_all_attempts_discarded(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "running")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="finished",
            verified_status="discarded",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("running", self._intent_status("repo:01INTENT"))

    def test_promoted_attempt_moves_intent_to_finished(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "running")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="finished",
            verified_status="promoted",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("finished", self._intent_status("repo:01INTENT"))

    def test_terminal_finished_intent_is_not_mutated(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "finished")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="running",
            verified_status="pending",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("finished", self._intent_status("repo:01INTENT"))

    def test_terminal_abandoned_intent_is_not_mutated(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "abandoned")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="running",
            verified_status="pending",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("abandoned", self._intent_status("repo:01INTENT"))

    def test_terminal_superseded_intent_is_not_mutated(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "superseded")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="running",
            verified_status="pending",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("superseded", self._intent_status("repo:01INTENT"))

    def test_open_intent_with_no_attempts_stays_open(self) -> None:
        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("open", self._intent_status("repo:01INTENT"))

    def test_open_intent_moves_to_running_when_any_attempt_running(self) -> None:
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="running",
            verified_status="pending",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("running", self._intent_status("repo:01INTENT"))

    def test_mixed_outcomes_finished_wins_even_with_failed_sibling(self) -> None:
        update_intent_status(self.conn, "repo:01INTENT", "running")
        self._seed_attempt(
            "repo:01ATT1",
            reported_status="crashed",
            verified_status="failed",
        )
        self._seed_attempt(
            "repo:01ATT2",
            reported_status="finished",
            verified_status="promoted",
        )

        refresh_intent_status(self.conn, "repo:01INTENT")

        self.assertEqual("finished", self._intent_status("repo:01INTENT"))

    def test_unknown_intent_id_is_noop(self) -> None:
        refresh_intent_status(self.conn, "repo:does-not-exist")

        self.assertEqual("open", self._intent_status("repo:01INTENT"))

    def _seed_intent(self, intent_id: str, *, status: str) -> None:
        insert_intent(
            self.conn,
            NewIntent(
                id=intent_id,
                repo_id="repo",
                title="Lifecycle",
                created_at="2026-04-23T00:00:00Z",
                created_by_actor_type="user",
                created_by_actor_id="cli",
                trigger_source="cli",
                status=status,
            ),
        )

    def _seed_attempt(
        self,
        attempt_id: str,
        *,
        reported_status: str,
        verified_status: str,
    ) -> None:
        insert_attempt(
            self.conn,
            NewAttempt(
                id=attempt_id,
                intent_id="repo:01INTENT",
                agent_id="codex:main",
                workspace_ref=f"/tmp/{attempt_id}",
                base_ref_oid="0" * 40,
                started_at="2026-04-23T00:01:00Z",
                ownership_token=f"token-{attempt_id}",
            ),
        )
        update_attempt(
            self.conn,
            attempt_id,
            reported_status=reported_status,
            verified_status=verified_status,
        )

    def _intent_status(self, intent_id: str) -> str:
        row = self.conn.execute(
            "SELECT status FROM intents WHERE id = ?",
            (intent_id,),
        ).fetchone()
        return str(row["status"]) if row else ""


if __name__ == "__main__":
    unittest.main()
