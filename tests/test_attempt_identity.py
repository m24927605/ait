from __future__ import annotations

import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import create_intent
from ait.db import (
    NewAttempt,
    NewIntent,
    SCHEMA_VERSION,
    backfill_attempt_identities,
    connect_db,
    get_attempt_identity,
    get_attempt_identity_by_handle,
    insert_attempt,
    insert_intent,
    list_attempt_identities,
    list_intent_attempts,
    run_migrations,
)
from support import init_git_repo


def _create_attempt_worker(
    repo_root: str, intent_id: str, queue: multiprocessing.Queue
) -> None:
    try:
        from ait.app import create_attempt

        attempt = create_attempt(
            Path(repo_root),
            intent_id=intent_id,
            agent_id="codex:worker",
        )
        queue.put(("ok", attempt.attempt_id, attempt.workspace_ref))
    except BaseException as exc:
        queue.put(("error", type(exc).__name__, str(exc)))


class AttemptIdentityTests(unittest.TestCase):
    def test_create_attempt_assigns_handle(self) -> None:
        conn = _memory_db()
        self.addCleanup(conn.close)
        _insert_intent(conn, intent_id="repo:intent-1", title="Fix identity")

        attempt = insert_attempt(
            conn,
            _new_attempt(
                attempt_id="repo:attempt-1",
                intent_id="repo:intent-1",
                started_at="2026-05-26T00:00:00Z",
            ),
        )

        identity = get_attempt_identity(conn, attempt.id)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual("a1", identity.handle)
        self.assertEqual(1, identity.handle_index)
        self.assertEqual("Fix identity", identity.display_title)
        self.assertEqual(identity.display_title, identity.deterministic_description)
        self.assertEqual("identity-bootstrap:v1", identity.description_source)
        self.assertTrue(identity.description_fingerprint.startswith("sha256:"))
        self.assertEqual(identity, get_attempt_identity_by_handle(conn, "a1"))

    def test_multiple_attempts_get_monotonic_handles(self) -> None:
        conn = _memory_db()
        self.addCleanup(conn.close)
        _insert_intent(conn, intent_id="repo:intent-1", title="Many attempts")

        attempts = [
            insert_attempt(
                conn,
                _new_attempt(
                    attempt_id=f"repo:attempt-{index}",
                    intent_id="repo:intent-1",
                    started_at=f"2026-05-26T00:00:0{index}Z",
                ),
            )
            for index in range(1, 4)
        ]

        identities = list_attempt_identities(conn, tuple(attempt.id for attempt in attempts))
        self.assertEqual(
            ["a1", "a2", "a3"],
            [identities[attempt.id].handle for attempt in attempts],
        )
        self.assertEqual(
            [1, 2, 3],
            [identities[attempt.id].handle_index for attempt in attempts],
        )

    def test_backfill_existing_attempts_is_stable(self) -> None:
        conn = _memory_db()
        self.addCleanup(conn.close)
        _insert_intent(conn, intent_id="repo:intent-1", title="Backfill identity")
        _insert_raw_attempt(
            conn,
            attempt_id="repo:attempt-b",
            intent_id="repo:intent-1",
            ordinal=2,
            started_at="2026-05-26T00:00:00Z",
        )
        _insert_raw_attempt(
            conn,
            attempt_id="repo:attempt-a",
            intent_id="repo:intent-1",
            ordinal=1,
            started_at="2026-05-26T00:00:00Z",
        )
        _insert_raw_attempt(
            conn,
            attempt_id="repo:attempt-c",
            intent_id="repo:intent-1",
            ordinal=3,
            started_at="2026-05-26T00:00:01Z",
        )

        first_count = backfill_attempt_identities(conn)
        first = _identity_rows(conn)
        second_count = backfill_attempt_identities(conn)
        second = _identity_rows(conn)

        self.assertEqual(3, first_count)
        self.assertEqual(0, second_count)
        self.assertEqual(first, second)
        self.assertEqual(
            [
                ("repo:attempt-a", 1, "a1"),
                ("repo:attempt-b", 2, "a2"),
                ("repo:attempt-c", 3, "a3"),
            ],
            first,
        )

    def test_concurrent_identity_assignment_has_no_duplicate_handles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            init_git_repo(repo_root)
            intent = create_intent(
                repo_root,
                title="Concurrent identity",
                description=None,
                kind="task",
            )

            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            processes = [
                ctx.Process(
                    target=_create_attempt_worker,
                    args=(str(repo_root), intent.intent_id, queue),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()

            results = [queue.get(timeout=20.0) for _ in processes]
            for process in processes:
                process.join(timeout=10.0)
                self.assertEqual(0, process.exitcode)

            errors = [result for result in results if result[0] != "ok"]
            self.assertEqual([], errors)
            attempt_ids = tuple(str(result[1]) for result in results)

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                attempts = list_intent_attempts(conn, intent.intent_id)
                identities = list_attempt_identities(conn, attempt_ids)
            finally:
                conn.close()

            self.assertEqual(2, len(identities))
            self.assertEqual({"a1", "a2"}, {identity.handle for identity in identities.values()})
            self.assertEqual(2, len({identity.handle_index for identity in identities.values()}))

            workspace_refs = [Path(attempt.workspace_ref) for attempt in attempts]
            self.assertEqual(len(workspace_refs), len(set(workspace_refs)))
            for workspace_ref in workspace_refs:
                self.assertTrue(workspace_ref.exists(), workspace_ref)
            worktree_dirs = sorted(
                path.resolve()
                for path in (repo_root / ".ait" / "workspaces").glob("attempt-*")
            )
            self.assertEqual(
                sorted(path.resolve() for path in workspace_refs),
                worktree_dirs,
            )

    def test_identity_deletes_with_attempt(self) -> None:
        conn = _memory_db()
        self.addCleanup(conn.close)
        _insert_intent(conn, intent_id="repo:intent-1", title="Cascade")
        attempt = insert_attempt(
            conn,
            _new_attempt(
                attempt_id="repo:attempt-1",
                intent_id="repo:intent-1",
                started_at="2026-05-26T00:00:00Z",
            ),
        )
        self.assertIsNotNone(get_attempt_identity(conn, attempt.id))

        with conn:
            conn.execute("DELETE FROM attempts WHERE id = ?", (attempt.id,))

        self.assertIsNone(get_attempt_identity(conn, attempt.id))


def _memory_db():
    conn = connect_db(":memory:")
    run_migrations(conn)
    return conn


def _insert_intent(conn, *, intent_id: str, title: str) -> None:
    insert_intent(
        conn,
        NewIntent(
            id=intent_id,
            repo_id="repo",
            title=title,
            created_at="2026-05-26T00:00:00Z",
            created_by_actor_type="user",
            created_by_actor_id="test",
            trigger_source="test",
        ),
    )


def _new_attempt(*, attempt_id: str, intent_id: str, started_at: str) -> NewAttempt:
    return NewAttempt(
        id=attempt_id,
        intent_id=intent_id,
        agent_id="codex:test",
        workspace_ref=f"workspace-{attempt_id.rsplit(':', 1)[-1]}",
        base_ref_oid="0" * 40,
        started_at=started_at,
        ownership_token=f"token-{attempt_id.rsplit(':', 1)[-1]}",
    )


def _insert_raw_attempt(
    conn,
    *,
    attempt_id: str,
    intent_id: str,
    ordinal: int,
    started_at: str,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO attempts(
                id, schema_version, intent_id, ordinal, agent_id, agent_model,
                agent_harness, agent_harness_version, workspace_kind, workspace_ref,
                base_ref_oid, base_ref_name, started_at, ended_at, heartbeat_at,
                reported_status, verified_status, ownership_token, raw_trace_ref,
                logs_ref, result_promotion_ref, result_exit_code
            )
            VALUES (?, ?, ?, ?, 'codex:test', NULL, NULL, NULL, 'worktree', ?, ?, NULL, ?, NULL, NULL,
                    'created', 'pending', ?, NULL, NULL, NULL, NULL)
            """,
            (
                attempt_id,
                SCHEMA_VERSION,
                intent_id,
                ordinal,
                f"workspace-{ordinal}",
                "0" * 40,
                started_at,
                f"token-{ordinal}",
            ),
        )


def _identity_rows(conn) -> list[tuple[str, int, str]]:
    rows = conn.execute(
        """
        SELECT attempt_id, handle_index, handle
        FROM attempt_identities
        ORDER BY handle_index ASC
        """
    ).fetchall()
    return [
        (str(row["attempt_id"]), int(row["handle_index"]), str(row["handle"]))
        for row in rows
    ]


if __name__ == "__main__":
    unittest.main()
