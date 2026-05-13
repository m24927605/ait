from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import init_repo
from ait.db import connect_db, insert_attempt, insert_evidence_file, insert_intent
from ait.db.records import NewAttempt, NewIntent


class CliAttemptListTests(unittest.TestCase):
    def test_attempt_list_table_uses_compact_human_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = _seed_repo_with_attempt(repo_root)
            stdout = io.StringIO()

            with (
                chdir(repo_root),
                patch("sys.argv", ["ait", "attempt", "list"]),
                redirect_stdout(stdout),
            ):
                exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("attempt", text)
        self.assertIn("status", text)
        self.assertIn("agent", text)
        self.assertIn("intent", text)
        self.assertIn("S2WM575M", text)
        self.assertIn("succeeded", text)
        self.assertIn("claude-code", text)
        self.assertIn("Add divide support", text)
        self.assertNotIn(attempt_id, text)
        self.assertNotIn("workspace_ref", text)
        self.assertNotIn("ownership_token", text)

    def test_attempt_list_jsonl_keeps_full_machine_readable_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            attempt_id = _seed_repo_with_attempt(repo_root)
            stdout = io.StringIO()

            with (
                chdir(repo_root),
                patch("sys.argv", ["ait", "attempt", "list", "--format", "jsonl"]),
                redirect_stdout(stdout),
            ):
                exit_code = cli.main()

        rows = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(0, exit_code)
        self.assertEqual([attempt_id], [row["id"] for row in rows])
        self.assertIn("workspace_ref", rows[0])


def _seed_repo_with_attempt(repo_root: Path) -> str:
    _init_git_repo(repo_root)
    init_repo(repo_root)
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    attempt_id = "repo:nonce:01KRG5GCXHKKMV4NTFS2WM575M"
    intent_id = "repo:nonce:01KRG5GCR4FGXJ4PA74M9FGJXB"
    try:
        insert_intent(
            conn,
            NewIntent(
                id=intent_id,
                repo_id="repo:nonce",
                title="Add divide support with zero-division handling and tests",
                kind="feature",
                created_at="2026-05-13T07:57:00Z",
                created_by_actor_type="human",
                created_by_actor_id="demo",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id=attempt_id,
                intent_id=intent_id,
                agent_id="claude-code:manual",
                agent_harness="claude-code",
                workspace_ref=str(repo_root / ".ait" / "workspaces" / "attempt-0001"),
                base_ref_oid="21257c5",
                base_ref_name="main",
                started_at="2026-05-13T07:58:31Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        conn.execute(
            "UPDATE attempts SET result_exit_code = ? WHERE id = ?",
            (0, attempt_id),
        )
        insert_evidence_file(
            conn,
            attempt_id=attempt_id,
            file_path="src/calculator.js",
            kind="changed",
        )
        insert_evidence_file(
            conn,
            attempt_id=attempt_id,
            file_path="test/calculator.test.js",
            kind="changed",
        )
    finally:
        conn.close()
    return attempt_id


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
