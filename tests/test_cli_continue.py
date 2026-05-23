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
from ait.app import create_attempt, create_intent, init_repo
from ait.db import connect_db, update_attempt


class CliContinueTests(unittest.TestCase):
    def test_continue_json_prefers_attachable_latest_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Terminal", "--agents", "fake:one,fake:two", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Attach safely", "--format", "json")

            plan = _run_cli_json(repo, "continue", "--format", "json")

        self.assertEqual("continue_plan", plan["kind"])
        self.assertEqual("session_attach", plan["target_type"])
        self.assertIn("ait session attach", plan["command"])
        self.assertEqual(2, len(plan["session"]["participants"]))

    def test_continue_no_interactive_falls_back_to_resume_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="claude-code:worker")

            text = _run_cli_text(repo, "continue", "--no-interactive")

        self.assertIn("Target: AIT attempt worktree", text)
        self.assertIn(f"Workspace: {attempt.workspace_ref}", text)
        self.assertIn("ait resume", text)
        self.assertIn("claude --continue", text)

    def test_continue_latest_uses_newer_attempt_over_older_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            session = _run_cli_json(repo, "session", "start", "Terminal", "--agents", "fake:one", "--format", "json")
            session_id = str(session["session_id"])
            session_path = repo / ".ait" / "sessions" / session_id / "session.json"
            session_payload = json.loads(session_path.read_text(encoding="utf-8"))
            session_payload["created_at"] = "2020-01-01T00:00:00Z"
            session_payload["updated_at"] = "2020-01-01T00:00:00Z"
            session_path.write_text(json.dumps(session_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id)

            plan = _run_cli_json(repo, "continue", "--format", "json")

        self.assertEqual("attempt_resume", plan["target_type"])
        self.assertEqual(attempt.workspace_ref, plan["resume"]["workspace_ref"])

    def test_continue_json_reports_codex_native_resume_from_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="codex:worker")
            trace_ref = ".ait/transcripts/codex.raw.txt"
            trace_path = repo / trace_ref
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                "To continue this session, run codex resume 019dd9ba-fc1a\n",
                encoding="utf-8",
            )
            init_result = init_repo(repo)
            conn = connect_db(init_result.db_path)
            try:
                update_attempt(conn, attempt.attempt_id, raw_trace_ref=trace_ref)
            finally:
                conn.close()

            plan = _run_cli_json(repo, "continue", "--format", "json")

        self.assertEqual("attempt_resume", plan["target_type"])
        commands = [item["command"] for item in plan["agent_hints"]]
        self.assertIn(f"cd {attempt.workspace_ref} && codex resume 019dd9ba-fc1a", commands)

    def test_continue_interactive_launches_resume_shell_for_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            create_attempt(repo, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo):
                with (
                    patch("sys.argv", ["ait", "continue"]),
                    redirect_stdout(stdout),
                    patch.object(stdout, "isatty", return_value=True),
                    patch("sys.stdin.isatty", return_value=True),
                    patch("ait.cli.continue_cmd.launch_resume_shell", return_value=7) as launch,
                ):
                    exit_code = cli.main()

        self.assertEqual(7, exit_code)
        self.assertTrue(launch.called)

    def test_continue_shell_hook_emits_current_shell_cd_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id)

            text = _run_cli_text(repo, "continue", "--shell-hook")

        self.assertIn(f"cd {attempt.workspace_ref}", text)
        self.assertIn("AIT_RESUME_ATTEMPT_ID", text)
        self.assertIn("AIT_RESUME_REPO_ROOT", text)

    def test_continue_shell_reminder_prints_actionable_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id)
            stdout = io.StringIO()

            with chdir(repo):
                with patch("sys.argv", ["ait", "continue", "--shell-reminder"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertIn(attempt.attempt_id.rsplit(":", 1)[-1], stdout.getvalue())
        self.assertIn("Run: ait continue", stdout.getvalue())

    def test_continue_latest_uses_recent_activity_when_not_in_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            repo = Path(tmp) / "repo"
            outside = Path(tmp) / "outside"
            home.mkdir()
            repo.mkdir()
            outside.mkdir()
            _init_git_repo(repo)
            with patch.dict("os.environ", {"HOME": str(home)}):
                intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
                attempt = create_attempt(repo, intent_id=intent.intent_id)
                plan = _run_cli_json(outside, "continue", "--format", "json")

        self.assertEqual("attempt_resume", plan["target_type"])
        self.assertEqual(str(repo.resolve()), plan["repo_root"])
        self.assertEqual(attempt.workspace_ref, plan["resume"]["workspace_ref"])

    def test_continue_prefers_current_repo_before_recent_activity_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_a = Path(tmp) / "repo-a"
            repo_b = Path(tmp) / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            _init_git_repo(repo_a)
            _init_git_repo(repo_b)
            intent_a = create_intent(repo_a, title="Current", description=None, kind="demo")
            attempt_a = create_attempt(repo_a, intent_id=intent_a.intent_id)
            intent_b = create_intent(repo_b, title="Newer elsewhere", description=None, kind="demo")
            create_attempt(repo_b, intent_id=intent_b.intent_id)

            plan = _run_cli_json(repo_a, "continue", "--format", "json")

        self.assertEqual("attempt_resume", plan["target_type"])
        self.assertEqual(str(repo_a.resolve()), plan["repo_root"])
        self.assertEqual(attempt_a.workspace_ref, plan["resume"]["workspace_ref"])

    def test_continue_latest_attempt_uses_heartbeat_over_start_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            older = create_attempt(repo, intent_id=intent.intent_id)
            newer = create_attempt(repo, intent_id=intent.intent_id)
            init_result = init_repo(repo)
            conn = connect_db(init_result.db_path)
            try:
                update_attempt(
                    conn,
                    older.attempt_id,
                    heartbeat_at="2099-01-01T00:00:00Z",
                )
            finally:
                conn.close()

            plan = _run_cli_json(repo, "continue", "--format", "json")

        self.assertEqual("attempt_resume", plan["target_type"])
        self.assertEqual(older.workspace_ref, plan["resume"]["workspace_ref"])
        self.assertNotEqual(newer.workspace_ref, plan["resume"]["workspace_ref"])


def _run_cli_json(repo: Path, *argv: str) -> dict[str, object]:
    text = _run_cli_text(repo, *argv)
    return json.loads(text)


def _run_cli_text(repo: Path, *argv: str) -> str:
    stdout = io.StringIO()
    with chdir(repo):
        with patch("sys.argv", ["ait", *argv]):
            with redirect_stdout(stdout):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(f"CLI exited with {exit_code}: {stdout.getvalue()}")
    return stdout.getvalue()


def _init_git_repo(path: Path) -> None:
    _git(path, "init", "-b", "main")


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
