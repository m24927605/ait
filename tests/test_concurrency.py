from __future__ import annotations

import multiprocessing
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.app import create_intent
from ait.db import connect_db, list_intent_attempts


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _create_attempt_worker(repo_root: str, intent_id: str, queue: multiprocessing.Queue) -> None:
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


class CreateAttemptConcurrencyTests(unittest.TestCase):
    def test_two_process_create_attempt_no_unique_violation_no_orphan_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")
            _git(repo_root, "config", "user.email", "test@example.com")
            _git(repo_root, "config", "user.name", "Test User")
            (repo_root / "README.md").write_text("test\n", encoding="utf-8")
            _git(repo_root, "add", "README.md")
            _git(repo_root, "commit", "-m", "initial")

            intent = create_intent(
                repo_root,
                title="Concurrent attempt creation",
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

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            try:
                attempts = list_intent_attempts(conn, intent.intent_id)
            finally:
                conn.close()

            self.assertEqual(2, len(attempts))
            self.assertEqual([1, 2], [attempt.ordinal for attempt in attempts])
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


if __name__ == "__main__":
    unittest.main()
