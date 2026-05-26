from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import init_repo
from ait.db import connect_db, insert_attempt, insert_intent
from ait.db.records import NewAttempt, NewIntent


class CliAttemptAliasTests(unittest.TestCase):
    def test_alias_list_shows_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _seed_repo_with_attempts(repo_root)

            set_out = _run_cli(repo_root, "ait", "attempt", "alias", "set", "a1", "fix-ci")
            list_out = _run_cli(repo_root, "ait", "attempt", "alias", "list")

        self.assertEqual(0, set_out[0], set_out[2])
        self.assertIn("Alias fix-ci -> a1", set_out[1])
        self.assertEqual(0, list_out[0], list_out[2])
        self.assertIn("alias", list_out[1])
        self.assertIn("handle", list_out[1])
        self.assertIn("attempt", list_out[1])
        self.assertIn("fix-ci", list_out[1])
        self.assertIn("a1", list_out[1])

    def test_alias_commands_accept_handle_or_full_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            first_id, second_id = _seed_repo_with_attempts(repo_root)

            by_handle = _run_cli(repo_root, "ait", "attempt", "alias", "set", "a1", "fix-ci")
            by_full_id = _run_cli(
                repo_root,
                "ait",
                "attempt",
                "alias",
                "set",
                second_id,
                "full-id",
            )
            list_out = _run_cli(repo_root, "ait", "attempt", "alias", "list")

        self.assertEqual(0, by_handle[0], by_handle[2])
        self.assertEqual(0, by_full_id[0], by_full_id[2])
        self.assertIn("Alias fix-ci -> a1", by_handle[1])
        self.assertIn("Alias full-id -> a2", by_full_id[1])
        self.assertIn("fix-ci", list_out[1])
        self.assertIn(first_id.rsplit(":", 1)[-1], list_out[1])
        self.assertIn("full-id", list_out[1])
        self.assertIn(second_id.rsplit(":", 1)[-1], list_out[1])


def _run_cli(repo_root: Path, *argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with chdir(repo_root), patch("sys.argv", list(argv)), redirect_stdout(stdout):
        with patch("sys.stderr", stderr):
            exit_code = cli.main()
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _seed_repo_with_attempts(repo_root: Path) -> tuple[str, str]:
    _init_git_repo(repo_root)
    init_repo(repo_root)
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    first_attempt_id = "repo:nonce:01KRG5GCXHKKMV4NTFS2WM575M"
    second_attempt_id = "repo:nonce:01KRG5GD8F9VVR7YYB2S4E5T8Q"
    intent_id = "repo:nonce:01KRG5GCR4FGXJ4PA74M9FGJXB"
    try:
        insert_intent(
            conn,
            NewIntent(
                id=intent_id,
                repo_id="repo:nonce",
                title="Alias attempts",
                kind="feature",
                created_at="2026-05-13T07:57:00Z",
                created_by_actor_type="human",
                created_by_actor_id="demo",
                trigger_source="cli",
            ),
        )
        for attempt_id, ordinal in (
            (first_attempt_id, "0001"),
            (second_attempt_id, "0002"),
        ):
            insert_attempt(
                conn,
                NewAttempt(
                    id=attempt_id,
                    intent_id=intent_id,
                    agent_id="codex:manual",
                    agent_harness="codex",
                    workspace_ref=str(repo_root / ".ait" / "workspaces" / f"attempt-{ordinal}"),
                    base_ref_oid="21257c5",
                    base_ref_name="main",
                    started_at=f"2026-05-13T07:58:{ordinal[-2:]}Z",
                    ownership_token=f"token-{ordinal}",
                    reported_status="finished",
                    verified_status="succeeded",
                ),
            )
    finally:
        conn.close()
    return first_attempt_id, second_attempt_id


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("demo\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    unittest.main()
