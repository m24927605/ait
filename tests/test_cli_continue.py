from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import create_attempt, create_commit_for_attempt, create_intent, init_repo
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

    def test_continue_no_interactive_uses_handle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="claude-code:worker")

            text = _run_cli_text(repo, "continue", "--no-interactive")

        self.assertIn("Target: AIT attempt worktree", text)
        self.assertIn("Attempt: a1", text)
        self.assertIn("Resume command: ait resume a1", text)
        self.assertIn("Finish command: ait resume a1 --finish", text)
        self.assertIn("claude --continue", text)
        self.assertNotIn(attempt.workspace_ref, text)

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
        self.assertEqual("ait resume a1", plan["command"])
        self.assertEqual(attempt.workspace_ref, plan["resume"]["workspace_ref"])
        self.assertEqual("a1", plan["resume"]["attempt_handle"])
        self.assertIn("no indexed changed files yet", plan["resume"]["attempt_description"])

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
        self.assertIn("interrupted attempt a1 is recoverable", stdout.getvalue())
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

    def test_agent_continue_launches_real_agent_in_latest_attempt_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_git_repo(repo)
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test User")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text(
                "#!/bin/sh\n"
                "printf 'continued in %s\\n' \"$PWD\"\n"
                "printf 'continued\\n' > continued.txt\n",
                encoding="utf-8",
            )
            real_codex.chmod(0o755)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="codex:worker")

            with chdir(repo):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "agent-continue",
                        "--adapter",
                        "codex",
                        "--real-binary",
                        str(real_codex),
                    ],
                ):
                    exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertTrue(Path(attempt.workspace_ref, "continued.txt").exists())
            self.assertEqual(
                "codex: continue interrupted work",
                _git(attempt.workspace_ref, "log", "-1", "--format=%s"),
            )

    def test_agent_continue_is_repo_scoped_and_ignores_recent_activity_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            repo_a = root / "repo-a"
            repo_b = root / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            _init_git_repo(repo_a)
            _init_git_repo(repo_b)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            capture = root / "agent-launched.txt"
            real_codex = bin_dir / "codex"
            real_codex.write_text(
                "#!/bin/sh\n"
                "printf 'pwd=%s\\nrepo=%s\\nworkspace=%s\\n' "
                '"$PWD" "${AIT_RESUME_REPO_ROOT:-}" "${AIT_WORKSPACE_REF:-}" '
                '> "$AIT_TEST_CAPTURE"\n'
                "printf 'launched\\n' > launched.txt\n",
                encoding="utf-8",
            )
            real_codex.chmod(0o755)

            with patch.dict(
                os.environ,
                {
                    "AIT_STATE_DIR": str(state_dir),
                    "AIT_TEST_CAPTURE": str(capture),
                    "AIT_RESUME_REPO_ROOT": "",
                },
                clear=False,
            ):
                intent_a = create_intent(
                    repo_a,
                    title="Interrupted elsewhere",
                    description=None,
                    kind="demo",
                )
                attempt_a = create_attempt(
                    repo_a,
                    intent_id=intent_a.intent_id,
                    agent_id="codex:worker",
                )
                init_repo(repo_b)
                with chdir(repo_b):
                    with patch(
                        "sys.argv",
                        [
                            "ait",
                            "agent-continue",
                            "--adapter",
                            "codex",
                            "--real-binary",
                            str(real_codex),
                            "--",
                        ],
                    ):
                        exit_code = cli.main()
                    cwd_after = Path.cwd().resolve()

            self.assertEqual(75, exit_code)
            self.assertEqual(repo_b.resolve(), cwd_after)
            self.assertFalse(capture.exists())
            self.assertFalse(Path(attempt_a.workspace_ref, "launched.txt").exists())

    def test_agent_continue_resumes_current_repo_when_recent_activity_elsewhere_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            repo_a = root / "repo-a"
            repo_b = root / "repo-b"
            repo_a.mkdir()
            repo_b.mkdir()
            _init_git_repo(repo_a)
            _init_git_repo(repo_b)
            _git(repo_b, "config", "user.email", "test@example.com")
            _git(repo_b, "config", "user.name", "Test User")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            capture = root / "agent-launched.txt"
            real_codex = bin_dir / "codex"
            real_codex.write_text(
                "#!/bin/sh\n"
                "printf 'pwd=%s\\nrepo=%s\\nworkspace=%s\\n' "
                '"$PWD" "${AIT_RESUME_REPO_ROOT:-}" "${AIT_WORKSPACE_REF:-}" '
                '> "$AIT_TEST_CAPTURE"\n'
                "printf 'continued\\n' > continued.txt\n",
                encoding="utf-8",
            )
            real_codex.chmod(0o755)

            with patch.dict(
                os.environ,
                {
                    "AIT_STATE_DIR": str(state_dir),
                    "AIT_TEST_CAPTURE": str(capture),
                    "AIT_RESUME_REPO_ROOT": "",
                },
                clear=False,
            ):
                intent_b = create_intent(
                    repo_b,
                    title="Current interrupted",
                    description=None,
                    kind="demo",
                )
                attempt_b = create_attempt(
                    repo_b,
                    intent_id=intent_b.intent_id,
                    agent_id="codex:worker",
                )
                intent_a = create_intent(
                    repo_a,
                    title="Newer elsewhere",
                    description=None,
                    kind="demo",
                )
                attempt_a = create_attempt(
                    repo_a,
                    intent_id=intent_a.intent_id,
                    agent_id="codex:worker",
                )
                with chdir(repo_b):
                    with patch(
                        "sys.argv",
                        [
                            "ait",
                            "agent-continue",
                            "--adapter",
                            "codex",
                            "--real-binary",
                            str(real_codex),
                            "--",
                        ],
                    ):
                        exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertTrue(Path(attempt_b.workspace_ref, "continued.txt").exists())
            self.assertFalse(Path(attempt_a.workspace_ref, "continued.txt").exists())
            capture_text = capture.read_text(encoding="utf-8")
            self.assertIn(f"pwd={attempt_b.workspace_ref}", capture_text)
            self.assertIn(f"repo={repo_b.resolve()}", capture_text)
            self.assertIn(f"workspace={attempt_b.workspace_ref}", capture_text)

    def test_agent_continue_returns_no_target_for_ready_to_apply_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_git_repo(repo)
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test User")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_codex = bin_dir / "codex"
            real_codex.write_text("#!/bin/sh\nprintf 'should not run\\n'\n", encoding="utf-8")
            real_codex.chmod(0o755)
            intent = create_intent(repo, title="Ready", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="codex:worker")
            Path(attempt.workspace_ref, "ready.txt").write_text("ready\n", encoding="utf-8")
            _git(attempt.workspace_ref, "add", "-A")
            create_commit_for_attempt(repo, attempt_id=attempt.attempt_id, message="ready")
            init_result = init_repo(repo)
            conn = connect_db(init_result.db_path)
            try:
                update_attempt(
                    conn,
                    attempt.attempt_id,
                    reported_status="finished",
                    verified_status="succeeded",
                )
            finally:
                conn.close()

            with chdir(repo):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "agent-continue",
                        "--adapter",
                        "codex",
                        "--real-binary",
                        str(real_codex),
                    ],
                ):
                    exit_code = cli.main()

        self.assertEqual(75, exit_code)

    def test_agent_continue_does_not_use_native_resume_for_cross_agent_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_git_repo(repo)
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test User")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" > claude-args.txt\n",
                encoding="utf-8",
            )
            real_claude.chmod(0o755)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="codex:worker")

            with chdir(repo):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "agent-continue",
                        "--adapter",
                        "claude-code",
                        "--real-binary",
                        str(real_claude),
                    ],
                ):
                    exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertEqual(
                "\n",
                Path(attempt.workspace_ref, "claude-args.txt").read_text(encoding="utf-8"),
            )

    def test_agent_continue_uses_native_claude_resume_for_claude_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _init_git_repo(repo)
            _git(repo, "config", "user.email", "test@example.com")
            _git(repo, "config", "user.name", "Test User")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            real_claude = bin_dir / "claude"
            real_claude.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" > claude-args.txt\n",
                encoding="utf-8",
            )
            real_claude.chmod(0o755)
            intent = create_intent(repo, title="Interrupted", description=None, kind="demo")
            attempt = create_attempt(repo, intent_id=intent.intent_id, agent_id="claude-code:worker")

            with chdir(repo):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "agent-continue",
                        "--adapter",
                        "claude-code",
                        "--real-binary",
                        str(real_claude),
                    ],
                ):
                    exit_code = cli.main()

            self.assertEqual(0, exit_code)
            self.assertEqual(
                "--continue\n",
                Path(attempt.workspace_ref, "claude-args.txt").read_text(encoding="utf-8"),
            )


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
