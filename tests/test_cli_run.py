from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli
from ait.app import init_repo
from ait.db import (
    connect_db,
    insert_attempt,
    insert_intent,
    insert_memory_retrieval_event,
    replace_memory_fact_entities,
    run_migrations,
    upsert_memory_fact,
)
from ait.db.repositories import (
    MemoryFactEntityRecord,
    NewAttempt,
    NewIntent,
    NewMemoryFact,
    NewMemoryRetrievalEvent,
)


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class CliRunTests(unittest.TestCase):
    def test_cli_main_returns_130_on_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            with chdir(repo_root):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--intent",
                            "Interrupted run",
                            "--",
                            sys.executable,
                            "-c",
                            "print('ok')",
                        ],
                    ),
                    patch("ait.cli.run.run_agent_command", side_effect=KeyboardInterrupt),
                ):
                    exit_code = cli.main()

        self.assertEqual(130, exit_code)

    def test_run_json_remains_machine_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--json",
                        "--intent",
                        "Capture output",
                        "--",
                        sys.executable,
                        "-c",
                        (
                            "import sys; "
                            "from pathlib import Path; "
                            "Path('agent.txt').write_text('ok\\n'); "
                            "print('agent out'); "
                            "print('agent err', file=sys.stderr)"
                        ),
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(0, payload["exit_code"])
        self.assertIn("workspace_ref", payload)
        self.assertIn(".ait/workspaces", payload["workspace_ref"])
        self.assertEqual("agent out\n", payload["command_stdout"])
        self.assertEqual("agent err\n", payload["command_stderr"])
        self.assertEqual("a1", payload["attempt_handle"])
        self.assertEqual(["ait apply a1"], payload["next_steps"])

    def test_run_default_tty_outputs_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = TtyStringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--intent",
                        "Default TTY text",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

        text = stderr.getvalue()
        self.assertEqual(0, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("AIT recorded the run", text)
        self.assertIn("Attempt: a1", text)
        self.assertIn("Next: ait apply a1", text)
        self.assertNotIn("{", text)
        self.assertNotIn(".ait/workspaces", text)

    def test_run_adapter_without_intent_uses_agent_attempt_not_dev_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--format",
                            "json",
                            "--adapter",
                            "codex",
                            "--",
                            sys.executable,
                            "-c",
                            "print('agent run')",
                        ],
                    ),
                    patch("ait.cli.run.start_dev_server", side_effect=AssertionError("dev server path should not run")),
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["intent_inferred"])
        self.assertEqual("manual codex run", payload["inferred_intent_title"])
        self.assertEqual("agent run\n", payload["command_stdout"])
        self.assertIn(".ait/workspaces", payload["workspace_ref"])

    def test_run_agent_without_intent_uses_agent_attempt_not_dev_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--format",
                            "json",
                            "--agent",
                            "claude-code:manual",
                            "--",
                            sys.executable,
                            "-c",
                            "print('agent run')",
                        ],
                    ),
                    patch("ait.cli.run.start_dev_server", side_effect=AssertionError("dev server path should not run")),
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["intent_inferred"])
        self.assertEqual("manual claude-code:manual run", payload["inferred_intent_title"])
        self.assertEqual("agent run\n", payload["command_stdout"])
        self.assertIn(".ait/workspaces", payload["workspace_ref"])

    def test_run_json_in_unborn_git_repo_creates_baseline_before_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _git(repo_root, "init")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Unborn repo smoke",
                        "--",
                        sys.executable,
                        "-c",
                        "print('ok')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual(0, payload["exit_code"])
            self.assertEqual("ok\n", payload["command_stdout"])
            self.assertEqual(
                "chore: initialize repository for AIT",
                _git_stdout(repo_root, "log", "-1", "--format=%s"),
            )

    def test_run_json_auto_commits_changes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Auto commit generated change",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload["attempt"]["commits"]))
        self.assertEqual(["agent.txt"], payload["attempt"]["files"]["changed"])

    def test_run_json_no_auto_commit_leaves_changes_uncommitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Inspect generated change",
                        "--no-auto-commit",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()
            payload = json.loads(stdout.getvalue())
            status = _git_stdout(Path(payload["workspace_ref"]), "status", "--short")

        self.assertEqual(0, exit_code)
        self.assertEqual([], payload["attempt"]["commits"])
        self.assertEqual("?? agent.txt", status)

    def test_run_text_format_prints_summary_to_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "text",
                        "--intent",
                        "Text run",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("AIT recorded the run", stderr.getvalue())
        self.assertIn("Exit code: 0", stderr.getvalue())
        self.assertIn("Next: ait apply a1", stderr.getvalue())
        self.assertNotIn(".ait/workspaces", stderr.getvalue())

    def test_run_apply_auto_text_applies_result_without_workspace_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _init_ait_and_commit_gitignore(repo_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "text",
                        "--apply",
                        "auto",
                        "--intent",
                        "Apply generated change",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

            text = stderr.getvalue()
            self.assertEqual(0, exit_code)
            self.assertEqual("", stdout.getvalue())
            self.assertTrue((repo_root / "agent.txt").exists())
            self.assertIn("Status: applied", text)
            self.assertIn("Cleanup: internal workspace removed", text)
            self.assertNotIn(".ait/workspaces", text)

    def test_run_apply_auto_json_keeps_run_and_apply_workspace_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _init_ait_and_commit_gitignore(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--apply",
                        "auto",
                        "--intent",
                        "Apply JSON change",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('json-agent.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("auto", payload["run_apply_policy"])
            self.assertIn(".ait/workspaces", payload["workspace_ref"])
            self.assertEqual("applied", payload["apply"]["status"])
            self.assertIn(".ait/workspaces", payload["apply"]["workspace_ref"])

    def test_run_uses_repo_config_apply_policy_when_cli_omits_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _init_ait_and_commit_gitignore(repo_root)
            config_path = repo_root / ".ait" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["run"] = {"apply": "auto"}
            config_path.write_text(json.dumps(config), encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Configured apply",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('configured.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("auto", payload["run_apply_policy"])
            self.assertEqual("applied", payload["apply"]["status"])
            self.assertTrue((repo_root / "configured.txt").exists())

    def test_config_show_reports_effective_policy_and_invalid_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _init_ait_and_commit_gitignore(repo_root)
            config_path = repo_root / ".ait" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["run"] = {"apply": "ask", "auto_prune": False}
            config["apply"] = {
                "dirty_strategy": "bad",
                "integration_attempt": "auto",
                "cleanup_after_apply": False,
                "semantic_integration": "auto",
            }
            config["integration"] = {
                "allow_untracked_replay": True,
                "allow_binary_merge": True,
                "allow_delete_merge": True,
                "auto_test_command": "pytest -q",
                "semantic_adapter": "codex",
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "config", "show", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            policy = payload["policy"]
            self.assertEqual(0, exit_code)
            self.assertEqual("never", policy["run"]["apply"])
            self.assertFalse(policy["run"]["auto_prune"])
            self.assertEqual("safe-patch", policy["apply"]["dirty_strategy"])
            self.assertEqual("auto", policy["apply"]["integration_attempt"])
            self.assertFalse(policy["apply"]["cleanup_after_apply"])
            self.assertEqual("codex", policy["integration"]["semantic_adapter"])
            self.assertIn("run.apply ask is non-interactive; using never", payload["warnings"])
            self.assertIn("apply.dirty_strategy invalid; using safe-patch", payload["warnings"])

    def test_query_parse_error_returns_cli_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "query", "agent.id = 'codex:main'"]):
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        exit_code = cli.main()

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("error: unexpected character", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_memory_text_outputs_repo_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertIn("AIT Long-Term Repo Memory", stdout.getvalue())
        self.assertIn("Recent Attempts:", stdout.getvalue())

    def test_memory_note_cli_adds_lists_and_removes_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_stdout = io.StringIO()
            list_stdout = io.StringIO()
            remove_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "architecture",
                        "Use repo-local state only.",
                    ],
                ):
                    with redirect_stdout(add_stdout):
                        add_exit = cli.main()
                note_id = json.loads(add_stdout.getvalue())["id"]
                with patch("sys.argv", ["ait", "memory", "note", "list", "--topic", "architecture"]):
                    with redirect_stdout(list_stdout):
                        list_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "note", "remove", note_id]):
                    with redirect_stdout(remove_stdout):
                        remove_exit = cli.main()

        self.assertEqual(0, add_exit)
        self.assertEqual(0, list_exit)
        self.assertEqual(0, remove_exit)
        self.assertIn("Use repo-local state only.", list_stdout.getvalue())
        self.assertTrue(json.loads(remove_stdout.getvalue())["removed"])

    def test_memory_search_cli_outputs_parseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_stdout = io.StringIO()
            search_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    ["ait", "memory", "note", "add", "--topic", "workflow", "Run tests before release."],
                ):
                    with redirect_stdout(add_stdout):
                        add_exit = cli.main()
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "search",
                        "tests release",
                        "--ranker",
                        "vector",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(search_stdout):
                        search_exit = cli.main()

        payload = json.loads(search_stdout.getvalue())
        self.assertEqual(0, add_exit)
        self.assertEqual(0, search_exit)
        self.assertEqual("note", payload[0]["kind"])
        self.assertIn("Run tests before release.", payload[0]["text"])
        self.assertEqual("vector", payload[0]["metadata"]["ranker"])

    def test_memory_facts_cli_lists_structured_memory_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            run_stdout = io.StringIO()
            facts_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Capture durable memory fact",
                        "--commit-message",
                        "Rule: 以後所有 release 必須先跑 pytest。",
                        "--",
                        sys.executable,
                        "-c",
                        "print('Rule: 以後所有 release 必須先跑 pytest。')",
                    ],
                ):
                    with redirect_stdout(run_stdout):
                        run_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "facts", "--format", "json"]):
                    with redirect_stdout(facts_stdout):
                        facts_exit = cli.main()

        payload = json.loads(facts_stdout.getvalue())
        self.assertEqual(0, run_exit)
        self.assertEqual(0, facts_exit)
        self.assertEqual(1, len(payload))
        self.assertEqual("rule", payload[0]["kind"])
        self.assertIn(payload[0]["status"], {"accepted", "candidate"})
        self.assertIn("release", payload[0]["body"])

    def test_memory_recall_cli_outputs_selected_memory_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            add_stdout = io.StringIO()
            recall_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "attempt-memory",
                        "--source",
                        "attempt-memory:test",
                        "Billing retry path changed_files=billing_retry.py confidence=high",
                    ],
                ):
                    with redirect_stdout(add_stdout):
                        add_exit = cli.main()
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "recall",
                        "billing retry",
                        "--budget-chars",
                        "180",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(recall_stdout):
                        recall_exit = cli.main()

        payload = json.loads(recall_stdout.getvalue())
        self.assertEqual(0, add_exit)
        self.assertEqual(0, recall_exit)
        self.assertEqual("billing retry", payload["query"])
        self.assertEqual(180, payload["budget_chars"])
        self.assertTrue(payload["selected"])
        self.assertEqual("attempt-memory:test", payload["selected"][0]["source"])
        self.assertEqual("temporal-v1", payload["selected"][0]["metadata"]["temporal_ranker"])
        self.assertIn("temporal_score", payload["selected"][0]["metadata"])
        self.assertLessEqual(payload["rendered_chars"], 180)

    def test_memory_recall_cli_skips_unhealthy_memory_unless_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            recall_stdout = io.StringIO()
            include_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "attempt-memory",
                        "--source",
                        "attempt-memory:healthy",
                        "Billing retry path changed_files=billing_retry.py confidence=high",
                    ],
                ):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(0, cli.main())
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "attempt-memory",
                        "--source",
                        "attempt-memory:secret",
                        "Billing retry path stores GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 confidence=high",
                    ],
                ):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(0, cli.main())
                with patch(
                    "sys.argv",
                    ["ait", "memory", "recall", "billing retry", "--format", "json"],
                ):
                    with redirect_stdout(recall_stdout):
                        recall_exit = cli.main()
                with patch(
                    "sys.argv",
                    ["ait", "memory", "recall", "billing retry", "--include-unhealthy", "--format", "json"],
                ):
                    with redirect_stdout(include_stdout):
                        include_exit = cli.main()

        payload = json.loads(recall_stdout.getvalue())
        include_payload = json.loads(include_stdout.getvalue())
        selected_sources = {item["source"] for item in payload["selected"]}
        skipped_secret = [item for item in payload["skipped"] if item.get("source") == "attempt-memory:secret"]

        self.assertEqual(0, recall_exit)
        self.assertEqual(0, include_exit)
        self.assertIn("attempt-memory:healthy", selected_sources)
        self.assertNotIn("attempt-memory:secret", selected_sources)
        self.assertEqual("lint issue", skipped_secret[0]["reason"])
        self.assertIn("possible_secret", skipped_secret[0]["lint_codes"])
        self.assertIn("attempt-memory:secret", {item["source"] for item in include_payload["selected"]})

    def test_memory_recall_auto_outputs_query_sources_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "recall",
                        "Billing retry",
                        "--auto",
                        "--agent",
                        "claude-code:manual",
                        "--command-text",
                        "python billing_retry.py",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertIn("Billing retry", payload["query"])
        self.assertIn("python billing_retry.py", payload["query"])
        self.assertTrue(any(item["source"] == "intent_title" for item in payload["query_sources"]))
        self.assertTrue(any(item["source"] == "command_args" for item in payload["query_sources"]))

    def test_memory_lint_cli_reports_and_fixes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            lint_stdout = io.StringIO()
            fix_stdout = io.StringIO()
            after_stdout = io.StringIO()

            with chdir(repo_root):
                for _ in range(2):
                    with patch(
                        "sys.argv",
                        ["ait", "memory", "note", "add", "--topic", "release", "Run tests before release."],
                    ):
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(0, cli.main())
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "note",
                        "add",
                        "--topic",
                        "security",
                        "Do not keep GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456 in memory.",
                    ],
                ):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(0, cli.main())
                with patch("sys.argv", ["ait", "memory", "lint", "--format", "json"]):
                    with redirect_stdout(lint_stdout):
                        lint_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "lint", "--fix", "--format", "json"]):
                    with redirect_stdout(fix_stdout):
                        fix_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "lint", "--format", "json"]):
                    with redirect_stdout(after_stdout):
                        after_exit = cli.main()

        lint_payload = json.loads(lint_stdout.getvalue())
        fix_payload = json.loads(fix_stdout.getvalue())
        after_payload = json.loads(after_stdout.getvalue())
        self.assertEqual(2, lint_exit)
        self.assertEqual(2, fix_exit)
        self.assertEqual(0, after_exit)
        self.assertGreater(lint_payload["issue_count"], 0)
        self.assertGreaterEqual(fix_payload["fix_count"], 2)
        self.assertEqual(0, after_payload["issue_count"])

    def test_memory_import_cli_imports_agent_memory_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Use ait repair if wrappers drift.\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "import", "--source", "claude", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload["imported"]))
        self.assertEqual("agent-memory:claude:CLAUDE.md", payload["imported"][0]["source"])
        self.assertIn("Use ait repair", payload["imported"][0]["body"])

    def test_memory_import_cli_custom_path_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / ".cursorrules").write_text("Prefer small scoped patches.\n", encoding="utf-8")
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "import", "--path", ".cursorrules"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        self.assertEqual(0, exit_code)
        self.assertIn("AIT memory import", stdout.getvalue())
        self.assertIn("Imported:", stdout.getvalue())
        self.assertIn("agent-memory:custom:.cursorrules", stdout.getvalue())

    def test_memory_backfill_dry_run_is_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Use ait repair if wrappers drift.\n", encoding="utf-8")
            before = _snapshot_non_internal_files(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "backfill", "--dry-run", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("dry-run", payload["mode"])
            self.assertEqual("repo", payload["scope"])
            self.assertEqual([], payload["imported"])
            self.assertEqual([], payload["writes"])
            self.assertFalse((repo_root / ".ait").exists())
            self.assertEqual(before, _snapshot_non_internal_files(repo_root))
            self.assertEqual(
                [("CLAUDE.md", "would_import")],
                [(item["path"], item["action"]) for item in payload["candidates"]],
            )

    def test_memory_backfill_import_writes_only_ait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Use ait repair if wrappers drift.\n", encoding="utf-8")
            before = _snapshot_non_internal_files(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "backfill", "--import", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("import", payload["mode"])
            self.assertEqual([".ait/"], payload["writes"])
            self.assertIn("not zero-touch", payload["mutation_warning"])
            self.assertEqual(1, len(payload["imported"]))
            self.assertEqual("agent-memory:claude:CLAUDE.md", payload["imported"][0]["source"])
            self.assertTrue((repo_root / ".ait").exists())
            self.assertEqual(before, _snapshot_non_internal_files(repo_root))

    def test_memory_backfill_does_not_scan_global_memory_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            repo_root.mkdir()
            (home / ".claude").mkdir(parents=True)
            _init_git_repo(repo_root)
            (home / ".claude" / "memory.md").write_text("GLOBAL_ONLY_MEMORY\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch.dict(os.environ, {"HOME": str(home)}):
                with chdir(repo_root):
                    with patch("sys.argv", ["ait", "memory", "backfill", "--dry-run", "--format", "json"]):
                        with redirect_stdout(stdout):
                            exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual([], payload["candidates"])
            self.assertEqual([], payload["writes"])
            self.assertFalse((repo_root / ".ait").exists())
            self.assertNotIn("GLOBAL_ONLY_MEMORY", stdout.getvalue())

    def test_memory_backfill_global_requires_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "backfill", "--global", "--dry-run"]):
                    with redirect_stderr(stderr):
                        exit_code = cli.main()

            self.assertEqual(2, exit_code)
            self.assertIn("requires an explicit --path", stderr.getvalue())
            self.assertFalse((repo_root / ".ait").exists())

    def test_memory_backfill_import_refuses_outside_repo_path_without_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            outside = Path(tmp) / "outside" / "memory.md"
            repo_root.mkdir()
            outside.parent.mkdir()
            _init_git_repo(repo_root)
            outside.write_text("External agent memory.\n", encoding="utf-8")
            before_repo = _snapshot_non_internal_files(repo_root)
            before_outside = (outside.read_bytes(), outside.stat().st_mtime_ns)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    ["ait", "memory", "backfill", "--import", "--path", str(outside), "--format", "json"],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual([], payload["imported"])
            self.assertEqual([], payload["writes"])
            self.assertEqual("skip", payload["candidates"][0]["action"])
            self.assertIn("outside repo", payload["candidates"][0]["reason"])
            self.assertFalse((repo_root / ".ait").exists())
            self.assertEqual(before_repo, _snapshot_non_internal_files(repo_root))
            self.assertEqual(before_outside, (outside.read_bytes(), outside.stat().st_mtime_ns))

    def test_memory_graph_cli_builds_shows_and_queries_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            build_stdout = io.StringIO()
            show_stdout = io.StringIO()
            query_stdout = io.StringIO()
            brief_stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "graph", "build", "--format", "json"]):
                    with redirect_stdout(build_stdout):
                        build_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "graph", "show", "--format", "json"]):
                    with redirect_stdout(show_stdout):
                        show_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "graph", "query", "hello", "--format", "json"]):
                    with redirect_stdout(query_stdout):
                        query_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "graph", "brief", "hello", "--format", "json"]):
                    with redirect_stdout(brief_stdout):
                        brief_exit = cli.main()

            graph_exists = (repo_root / ".ait" / "brain" / "graph.json").exists()

        build_payload = json.loads(build_stdout.getvalue())
        show_payload = json.loads(show_stdout.getvalue())
        query_payload = json.loads(query_stdout.getvalue())
        brief_payload = json.loads(brief_stdout.getvalue())
        self.assertEqual(0, build_exit)
        self.assertEqual(0, show_exit)
        self.assertEqual(0, query_exit)
        self.assertEqual(0, brief_exit)
        self.assertTrue(graph_exists)
        self.assertTrue(any(node["id"] == "repo:root" for node in build_payload["nodes"]))
        self.assertTrue(any(node["id"] == "doc:README.md" for node in show_payload["nodes"]))
        self.assertTrue(query_payload)
        self.assertEqual("hello", brief_payload["query"])
        self.assertTrue(brief_payload["results"])

    def test_memory_graph_brief_auto_outputs_sources_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "memory",
                        "graph",
                        "brief",
                        "Release package",
                        "--auto",
                        "--agent",
                        "codex:main",
                        "--command-text",
                        "twine upload dist/*",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        source_names = {source["source"] for source in payload["sources"]}
        self.assertEqual(0, exit_code)
        self.assertIn("intent_title", source_names)
        self.assertIn("agent", source_names)
        self.assertIn("command_args", source_names)

    def test_memory_graph_query_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "graph", "query", "hello", "--limit", "-1"]):
                    with redirect_stderr(stderr):
                        exit_code = cli.main()

        self.assertEqual(2, exit_code)
        self.assertIn("limit must be non-negative", stderr.getvalue())

    def test_work_graph_outputs_text_and_static_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            run_stdout = io.StringIO()
            text_stdout = io.StringIO()
            html_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Build graph report",
                        "--commit-message",
                        "Rule: 以後所有 graph report 必須顯示 outcome badge。",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('graph.txt').write_text('ok\\n'); print('AIT_GRAPH_TRANSCRIPT_TOKEN'); print('Rule: 以後所有 graph report 必須顯示 outcome badge。')",
                    ],
                ):
                    with redirect_stdout(run_stdout):
                        run_exit = cli.main()
                with patch("sys.argv", ["ait", "graph"]):
                    with redirect_stdout(text_stdout):
                        text_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--html"]):
                    with redirect_stdout(html_stdout):
                        html_exit = cli.main()

            run_payload = json.loads(run_stdout.getvalue())
            graph_text = text_stdout.getvalue()
            html_path = repo_root / ".ait" / "report" / "graph.html"
            html = html_path.read_text(encoding="utf-8")

            self.assertEqual(0, run_exit)
            self.assertEqual(0, text_exit)
            self.assertEqual(0, html_exit)
            self.assertIn("AIT Work Graph", graph_text)
            self.assertIn("Intent", graph_text)
            self.assertIn("[status=finished]", graph_text)
            self.assertIn("Build graph report", graph_text)
            self.assertIn("Attempt 1", graph_text)
            self.assertIn("graph.txt", graph_text)
            self.assertIn(run_payload["attempt_id"].rsplit(":", 1)[-1][:8], graph_text)
            self.assertIn("wrote", html_stdout.getvalue())
            self.assertIn("AIT Work Graph", html)
            self.assertIn("AIT Health", html)
            self.assertIn("Status <span class=\"badge badge-ok\">pass</span>", html)
            self.assertIn("Attempt Status", html)
            self.assertIn("Outcomes", html)
            self.assertIn("Hot Files", html)
            self.assertIn("Visual Tree Graph", html)
            self.assertIn("data-visual-intent", html)
            self.assertIn("data-visual-attempt", html)
            self.assertIn("<strong>Files</strong>", html)
            self.assertIn("<strong>Commits</strong>", html)
            self.assertIn("<strong>Memory</strong>", html)
            self.assertIn("<strong>Transcript</strong>", html)
            self.assertIn('id="filterText"', html)
            self.assertIn('data-attempt-node', html)
            self.assertIn("<details", html)
            self.assertIn("Build graph report", html)
            self.assertIn("graph.txt", html)
            self.assertIn("Outcome Reasons", html)
            self.assertIn("Memory Facts", html)
            self.assertIn("Memory Candidates", html)
            self.assertIn("outcome badge", html)
            self.assertIn("Transcript", html)
            self.assertIn("mode=<code>normalized</code>", html)
            self.assertIn("AIT_GRAPH_TRANSCRIPT_TOKEN", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("http://", html)

    def test_work_graph_json_matches_schema_v1_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            run_stdout = io.StringIO()
            graph_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Build graph JSON contract",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('contract.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(run_stdout):
                        run_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--format", "json"]):
                    with redirect_stdout(graph_stdout):
                        graph_exit = cli.main()

            payload = json.loads(graph_stdout.getvalue())
            contract = json.loads(
                (Path(__file__).parent / "fixtures" / "work_graph" / "schema_v1_contract.json").read_text(
                    encoding="utf-8"
                )
            )
            intents = [item for item in payload["intents"] if isinstance(item, dict)]
            attempts = [item for item in intents[0]["attempts"] if isinstance(item, dict)]

            self.assertEqual(0, run_exit)
            self.assertEqual(0, graph_exit)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertEqual(contract["summary_keys"], sorted(payload["summary"].keys()))
            self.assertEqual(contract["intent_keys"], sorted(intents[0].keys()))
            self.assertEqual(contract["attempt_keys"], sorted(attempts[0].keys()))
            self.assertEqual("Build graph JSON contract", intents[0]["title"])
            self.assertIn("contract.txt", attempts[0]["files"].get("changed", []))

    def test_console_read_only_writes_temp_html_without_repo_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "console", "--read-only", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            contract_path = Path(__file__).parent / "fixtures" / "daily_console" / "schema_v1_contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            output = Path(payload["output"])
            html = output.read_text(encoding="utf-8")

            self.assertEqual(0, exit_code)
            self.assertEqual(contract["schema"], payload["schema"])
            self.assertEqual(contract["schema_version"], payload["schema_version"])
            self.assertEqual(contract["top_level_keys"], sorted(payload.keys()))
            self.assertTrue(payload["read_only"])
            self.assertTrue(output.exists())
            self.assertIn("AIT Daily Console", html)
            self.assertIn("Read-only", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("data-action", html)
            self.assertFalse((repo_root / ".ait").exists())

    def test_console_serve_local_rejects_non_loopback_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "console",
                        "--read-only",
                        "--serve-local",
                        "--host",
                        "0.0.0.0",
                        "--format",
                        "json",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(2, exit_code)
            self.assertEqual("error", payload["status"])
            self.assertIn("loopback-only", payload["error"])

    def test_work_graph_html_shows_background_health_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            run_stdout = io.StringIO()
            graph_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Fail graph health",
                        "--",
                        sys.executable,
                        "-c",
                        "raise SystemExit(7)",
                    ],
                ):
                    with redirect_stdout(run_stdout):
                        run_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--html"]):
                    with redirect_stdout(graph_stdout):
                        graph_exit = cli.main()

            html = (repo_root / ".ait" / "report" / "graph.html").read_text(encoding="utf-8")

            self.assertEqual(7, run_exit)
            self.assertEqual(0, graph_exit)
            self.assertIn("AIT Health", html)
            self.assertIn("Status <span class=\"badge badge-warn\">warn</span>", html)
            self.assertIn("latest attempt failed", html)
            self.assertIn("<code>ait graph --html</code>", html)

    def test_memory_retrievals_cli_and_graph_show_context_memory_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            seed_stdout = io.StringIO()
            run_stdout = io.StringIO()
            retrieval_stdout = io.StringIO()
            graph_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--intent",
                        "Seed release memory",
                        "--commit-message",
                        "Rule: 以後所有 release 必須先跑 pytest。",
                        "--",
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path;"
                            "Path('docs').mkdir(exist_ok=True);"
                            "Path('docs/release.md').write_text('Rule: 以後所有 release 必須先跑 pytest。\\n');"
                            "print('Rule: 以後所有 release 必須先跑 pytest。')"
                        ),
                    ],
                ):
                    with redirect_stdout(seed_stdout):
                        seed_exit = cli.main()
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--with-context",
                        "--intent",
                        "Use release memory",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('context-copy.txt').write_text(Path('.ait-context.md').read_text())",
                    ],
                ):
                    with redirect_stdout(run_stdout):
                        run_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "retrievals"]):
                    with redirect_stdout(retrieval_stdout):
                        retrieval_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--html"]):
                    with redirect_stdout(graph_stdout):
                        graph_exit = cli.main()

            seed_payload = json.loads(seed_stdout.getvalue())
            run_payload = json.loads(run_stdout.getvalue())
            retrieval_text = retrieval_stdout.getvalue()
            html = (repo_root / ".ait" / "report" / "graph.html").read_text(encoding="utf-8")

            self.assertEqual(0, seed_exit)
            self.assertEqual(0, run_exit)
            self.assertEqual(0, retrieval_exit)
            self.assertEqual(0, graph_exit)
            self.assertEqual(0, seed_payload["exit_code"])
            self.assertEqual(0, run_payload["exit_code"])
            self.assertIn("AIT Memory Retrievals", retrieval_text)
            self.assertIn("release 必須先跑 pytest", retrieval_text)
            self.assertIn("hybrid-v1", retrieval_text)
            self.assertIn("Memory Used", html)
            self.assertIn("Memory Eval", html)
            self.assertIn("score=", html)
            self.assertIn("pass", html)
            self.assertIn("release 必須先跑 pytest", html)
            self.assertIn("Use release memory", html)

    def test_memory_eval_empty_repo_outputs_passing_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(0, payload["event_count"])
        self.assertEqual(100, payload["average_score"])
        self.assertEqual([], payload["events"])

    def test_work_graph_html_shows_memory_eval_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stdout = io.StringIO()
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:rejected",
                fact_status="rejected",
                confidence="high",
                selected_fact_ids=("fact:rejected",),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
            )

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "graph", "--html"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

            html = (repo_root / ".ait" / "report" / "graph.html").read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("Memory Eval", html)
        self.assertIn("score=", html)
        self.assertIn("Issues", html)
        self.assertIn("selected fact is not accepted", html)
        self.assertIn("fact:rejected", html)

    def test_memory_eval_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--limit", "-1"]):
                    with redirect_stderr(stderr):
                        exit_code = cli.main()

        self.assertEqual(2, exit_code)
        self.assertIn("limit must be non-negative", stderr.getvalue())

    def test_memory_eval_passes_healthy_selected_fact_and_filters_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            attempt_id = _seed_memory_eval_state(
                repo_root,
                fact_id="fact:release:pytest",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:release:pytest",),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
            )
            other_attempt_id = _seed_memory_eval_state(
                repo_root,
                intent_id="intent:other",
                attempt_id="attempt:other",
                event_id="retrieval:other",
                fact_id="fact:other",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:other",),
                query="other memory",
                source_trace_ref=".ait/traces/other.txt",
                summary="Use other memory",
                body="Other workflow memory is unrelated.",
                entities=("other",),
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    ["ait", "memory", "eval", "--attempt", attempt_id, "--format", "json"],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(1, payload["event_count"])
        event = payload["events"][0]
        self.assertEqual(attempt_id, event["attempt_id"])
        self.assertNotEqual(other_attempt_id, event["attempt_id"])
        self.assertEqual("pass", event["status"])
        self.assertEqual(100, event["score"])
        self.assertEqual(["fact:release:pytest"], event["selected_fact_ids"])
        self.assertEqual([], event["issues"])
        self.assertEqual([], event["warnings"])
        self.assertEqual(
            {
                "event_id",
                "attempt_id",
                "query",
                "status",
                "score",
                "selected_count",
                "issue_count",
                "warning_count",
                "selected_fact_ids",
                "missing_relevant_fact_ids",
                "issues",
                "warnings",
                "selected_facts",
            },
            set(event),
        )
        self.assertEqual(
            {
                "id",
                "kind",
                "topic",
                "summary",
                "status",
                "confidence",
                "relevance_score",
            },
            set(event["selected_facts"][0]),
        )

    def test_memory_eval_fails_unaccepted_superseded_and_policy_blocked_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / ".ait").mkdir(exist_ok=True)
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps(
                    {
                        "exclude_paths": ["secret/**"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                        "recall_source_allow": ["attempt-memory:*", "agent-memory:*"],
                        "recall_source_block": [],
                        "recall_lint_block_severities": ["error"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            _upsert_eval_fact(
                repo_root,
                fact_id="fact:new",
                status="accepted",
                confidence="high",
                summary="Replacement release fact",
                body="Replacement release workflow.",
                source_trace_ref=".ait/traces/new.txt",
            )
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:bad",
                fact_status="candidate",
                confidence="high",
                selected_fact_ids=("fact:bad",),
                query="release pytest workflow",
                source_file_path="secret/release.md",
                superseded_by="fact:new",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        event = payload["events"][0]
        self.assertEqual("fail", event["status"])
        self.assertLess(event["score"], 100)
        self.assertTrue(any("not accepted" in issue for issue in event["issues"]))
        self.assertTrue(any("stale or superseded" in issue for issue in event["issues"]))
        self.assertTrue(any("blocked by memory policy" in issue for issue in event["issues"]))

    def test_memory_eval_fails_source_trace_ref_blocked_by_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / ".ait").mkdir(exist_ok=True)
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps(
                    {
                        "exclude_paths": [".env"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                        "recall_source_allow": ["attempt-memory:*", "agent-memory:*"],
                        "recall_source_block": ["blocked:*"],
                        "recall_lint_block_severities": ["error"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:blocked-trace",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:blocked-trace",),
                query="release pytest workflow",
                source_trace_ref="blocked:trace",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("blocked by memory policy" in issue for issue in payload["events"][0]["issues"])
        )

    def test_memory_eval_fails_logical_source_not_allowed_by_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:untrusted",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:untrusted",),
                query="release pytest workflow",
                source_trace_ref="untrusted:trace",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("blocked by memory policy" in issue for issue in payload["events"][0]["issues"])
        )

    def test_memory_eval_expiry_is_judged_against_retrieval_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:expires-later",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:expires-later",),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
                valid_to="2026-04-30T00:03:00Z",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual("pass", payload["events"][0]["status"])

    def test_memory_eval_fails_expired_fact_at_retrieval_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:expired",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=("fact:expired",),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
                valid_to="2026-04-30T00:01:00Z",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(any("stale or superseded" in issue for issue in payload["events"][0]["issues"]))

    def test_memory_eval_fails_rejected_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:rejected",
                fact_status="rejected",
                confidence="high",
                selected_fact_ids=("fact:rejected",),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(any("not accepted" in issue for issue in payload["events"][0]["issues"]))

    def test_memory_eval_warns_for_low_confidence_no_evidence_and_missing_relevant_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:release:pytest",
                fact_status="accepted",
                confidence="medium",
                selected_fact_ids=("fact:release:pytest",),
                query="release pytest workflow",
            )
            _upsert_eval_fact(
                repo_root,
                fact_id="fact:release:build",
                status="accepted",
                confidence="high",
                summary="Run build before release",
                body="Release workflow must run build before publishing.",
                source_trace_ref=".ait/traces/build.txt",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        text = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Status: warn", text)
        self.assertIn("score=", text)
        self.assertIn("selected:", text)
        self.assertIn("fact:release:pytest", text)
        self.assertIn("confidence is not high", text)
        self.assertIn("has no trace, commit, or file evidence", text)
        self.assertIn("missing relevant facts", text)
        self.assertIn("fact:release:build", text)

    def test_memory_eval_warns_when_no_facts_selected_but_relevant_fact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            _seed_memory_eval_state(
                repo_root,
                fact_id="fact:release:pytest",
                fact_status="accepted",
                confidence="high",
                selected_fact_ids=(),
                query="release pytest workflow",
                source_trace_ref=".ait/traces/release.txt",
            )
            stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "eval", "--format", "json"]):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("warn", payload["status"])
        event = payload["events"][0]
        self.assertEqual("warn", event["status"])
        self.assertEqual(0, event["selected_count"])
        self.assertIn("fact:release:pytest", event["missing_relevant_fact_ids"])
        self.assertTrue(any("no facts selected" in warning for warning in event["warnings"]))

    def test_work_graph_json_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            stderr = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "graph", "--limit", "-1"]):
                    with redirect_stderr(stderr):
                        exit_code = cli.main()

        self.assertEqual(2, exit_code)
        self.assertIn("limit must be non-negative", stderr.getvalue())

    def test_work_graph_filters_by_status_agent_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            first_stdout = io.StringIO()
            second_stdout = io.StringIO()
            filtered_stdout = io.StringIO()
            json_stdout = io.StringIO()
            html_stdout = io.StringIO()

            with chdir(repo_root):
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--agent",
                        "claude-code:manual",
                        "--intent",
                        "Claude graph branch",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('claude.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(first_stdout):
                        first_exit = cli.main()
                with patch(
                    "sys.argv",
                    [
                        "ait",
                        "run",
                        "--format",
                        "json",
                        "--agent",
                        "codex:manual",
                        "--intent",
                        "Codex graph branch",
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('codex.txt').write_text('ok\\n')",
                    ],
                ):
                    with redirect_stdout(second_stdout):
                        second_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--agent", "claude-code", "--file", "claude.txt", "--status", "succeeded"]):
                    with redirect_stdout(filtered_stdout):
                        filtered_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--agent", "claude-code", "--format", "json"]):
                    with redirect_stdout(json_stdout):
                        json_exit = cli.main()
                with patch("sys.argv", ["ait", "graph", "--file", "claude.txt", "--html"]):
                    with redirect_stdout(html_stdout):
                        html_exit = cli.main()

            graph_text = filtered_stdout.getvalue()
            graph_json = json.loads(json_stdout.getvalue())
            html = (repo_root / ".ait" / "report" / "graph.html").read_text(encoding="utf-8")

            self.assertEqual(0, first_exit)
            self.assertEqual(0, second_exit)
            self.assertEqual(0, filtered_exit)
            self.assertEqual(0, json_exit)
            self.assertEqual(0, html_exit)
            self.assertIn("Filters: agent=claude-code, file=claude.txt, status=succeeded", graph_text)
            self.assertIn("Claude graph branch", graph_text)
            self.assertIn("claude.txt", graph_text)
            self.assertNotIn("Codex graph branch", graph_text)
            self.assertEqual({"agent": "claude-code"}, graph_json["filters"])
            self.assertEqual(1, graph_json["matched_attempt_count"])
            self.assertIn("Filters:", html)
            self.assertIn("claude.txt", html)
            self.assertNotIn("codex.txt", html)

    def test_memory_policy_cli_initializes_and_shows_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_stdout = io.StringIO()
            show_stdout = io.StringIO()

            with chdir(repo_root):
                with patch("sys.argv", ["ait", "memory", "policy", "init"]):
                    with redirect_stdout(init_stdout):
                        init_exit = cli.main()
                with patch("sys.argv", ["ait", "memory", "policy", "show"]):
                    with redirect_stdout(show_stdout):
                        show_exit = cli.main()

        init_payload = json.loads(init_stdout.getvalue())
        show_payload = json.loads(show_stdout.getvalue())
        self.assertEqual(0, init_exit)
        self.assertEqual(0, show_exit)
        self.assertTrue(init_payload["created"])
        self.assertTrue(init_payload["path"].endswith(".ait/memory-policy.json"))
        self.assertIn(".env", show_payload["exclude_paths"])
        self.assertIn("BEGIN PRIVATE KEY", show_payload["exclude_transcript_patterns"])
        self.assertEqual(
            [
                "manual",
                "manual:*",
                "attempt-memory:*",
                "agent-memory:*",
                "live-memory:*",
                "durable-memory:*",
                "transcript-summary:*",
            ],
            show_payload["recall_source_allow"],
        )
        self.assertEqual([], show_payload["recall_source_block"])
        self.assertEqual(["error"], show_payload["recall_lint_block_severities"])


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True)


def _run_ait_cli_subprocess(
    repo_root: Path,
    args: list[str],
    *,
    stdin_text: str,
    path_prefix: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = Path(__file__).resolve().parents[1] / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_path)
        if not existing_pythonpath
        else str(src_path) + os.pathsep + existing_pythonpath
    )
    if path_prefix is not None:
        env["PATH"] = str(path_prefix) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [sys.executable, "-m", "ait.cli", *args],
        cwd=repo_root,
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _write_mock_codex(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    mock_codex = bin_dir / "codex"
    mock_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print('args=' + repr(sys.argv[1:]))\n"
        "print('stdin=' + repr(data))\n",
        encoding="utf-8",
    )
    mock_codex.chmod(0o755)
    return mock_codex


def _init_ait_and_commit_gitignore(repo_root: Path) -> None:
    init_repo(repo_root)
    gitignore = repo_root / ".gitignore"
    if gitignore.exists() and _git_stdout(repo_root, "status", "--short", "--", ".gitignore"):
        _git(repo_root, "add", ".gitignore")
        _git(repo_root, "commit", "-m", "ignore ait state")


def _snapshot_non_internal_files(repo_root: Path) -> dict[str, tuple[bytes, int]]:
    snapshot: dict[str, tuple[bytes, int]] = {}
    for path in sorted(item for item in repo_root.rglob("*") if item.is_file()):
        relative = path.relative_to(repo_root).as_posix()
        if relative.startswith(".git/") or relative.startswith(".ait/"):
            continue
        stat = path.stat()
        snapshot[relative] = (path.read_bytes(), stat.st_mtime_ns)
    return snapshot


def _git_stdout(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True)


def _seed_memory_eval_state(
    repo_root: Path,
    *,
    fact_id: str,
    fact_status: str,
    confidence: str,
    selected_fact_ids: tuple[str, ...],
    query: str,
    intent_id: str = "intent:release",
    attempt_id: str = "attempt:release",
    event_id: str = "retrieval:release",
    source_trace_ref: str | None = None,
    source_file_path: str | None = None,
    superseded_by: str | None = None,
    valid_to: str | None = None,
    summary: str = "Run pytest before release",
    body: str = "Release workflow must run pytest before publishing.",
    entities: tuple[str, ...] = ("release", "pytest"),
) -> str:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        insert_intent(
            conn,
            NewIntent(
                id=intent_id,
                repo_id="repo",
                title="Release memory eval",
                created_at="2026-04-30T00:00:00Z",
                created_by_actor_type="agent",
                created_by_actor_id="codex:main",
                trigger_source="cli",
            ),
        )
        insert_attempt(
            conn,
            NewAttempt(
                id=attempt_id,
                intent_id=intent_id,
                agent_id="codex:main",
                workspace_ref=str(repo_root / ".ait" / "workspaces" / attempt_id),
                base_ref_oid="abc123",
                started_at="2026-04-30T00:01:00Z",
                ownership_token="token",
                reported_status="finished",
                verified_status="succeeded",
            ),
        )
        _upsert_eval_fact(
            repo_root,
            fact_id=fact_id,
            status=fact_status,
            confidence=confidence,
            summary=summary,
            body=body,
            source_trace_ref=source_trace_ref,
            source_file_path=source_file_path,
            superseded_by=superseded_by,
            valid_to=valid_to,
            entities=entities,
        )
        insert_memory_retrieval_event(
            conn,
            NewMemoryRetrievalEvent(
                id=event_id,
                attempt_id=attempt_id,
                query=query,
                selected_fact_ids=selected_fact_ids,
                ranker_version="hybrid-v1",
                budget_chars=4000,
                created_at="2026-04-30T00:02:00Z",
            ),
        )
    finally:
        conn.close()
    return attempt_id


def _upsert_eval_fact(
    repo_root: Path,
    *,
    fact_id: str,
    status: str,
    confidence: str,
    summary: str,
    body: str,
    source_trace_ref: str | None = None,
    source_file_path: str | None = None,
    superseded_by: str | None = None,
    valid_to: str | None = None,
    entities: tuple[str, ...] = ("release", "pytest"),
) -> None:
    conn = connect_db(repo_root / ".ait" / "state.sqlite3")
    try:
        run_migrations(conn)
        upsert_memory_fact(
            conn,
            NewMemoryFact(
                id=fact_id,
                kind="rule",
                topic="release",
                body=body,
                summary=summary,
                status=status,
                confidence=confidence,
                source_trace_ref=source_trace_ref,
                source_file_path=source_file_path,
                valid_to=valid_to,
                valid_from="2026-04-30T00:00:00Z",
                created_at="2026-04-30T00:00:00Z",
                updated_at="2026-04-30T00:00:00Z",
                superseded_by=superseded_by,
            ),
        )
        replace_memory_fact_entities(
            conn,
            memory_fact_id=fact_id,
            entities=tuple(
                MemoryFactEntityRecord(
                    memory_fact_id=fact_id,
                    entity=entity,
                    entity_type="keyword",
                    weight=1.0,
                )
                for entity in entities
            ),
        )
    finally:
        conn.close()


class CliRunStdinModeTests(unittest.TestCase):
    """Tests for the --stdin flag on `ait run`.

    Default 'auto' preserves interactive inheritance but redirects known
    non-interactive agent commands (e.g. `codex exec`) from /dev/null.
    Explicit 'none' always redirects child stdin from /dev/null.
    """

    def test_parser_defaults_to_auto(self) -> None:
        from ait.cli_parser import build_parser

        args = build_parser().parse_args(
            ["run", "--adapter", "shell", "--", "echo", "hi"]
        )
        self.assertEqual(args.stdin, "auto")

    def test_parser_accepts_none(self) -> None:
        from ait.cli_parser import build_parser

        args = build_parser().parse_args(
            ["run", "--adapter", "shell", "--stdin", "none", "--", "echo", "hi"]
        )
        self.assertEqual(args.stdin, "none")

    def test_parser_rejects_unknown_value(self) -> None:
        from ait.cli_parser import build_parser

        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["run", "--adapter", "shell", "--stdin", "wat", "--", "echo", "hi"]
            )

    def test_run_with_stdin_none_does_not_inherit_parent_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            with chdir(repo_root):
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--adapter",
                            "shell",
                            "--stdin",
                            "none",
                            "--intent",
                            "stdin none integration",
                            "--no-auto-commit",
                            "--format",
                            "json",
                            "--",
                            "sh",
                            "-c",
                            "cat; echo CAT_EXITED",
                        ],
                    ),
                    redirect_stdout(io.StringIO()) as buf_out,
                    redirect_stderr(io.StringIO()),
                ):
                    code = cli.main()
                self.assertEqual(code, 0, f"ait run returned {code}")
                payload = json.loads(buf_out.getvalue())
                self.assertEqual(payload["exit_code"], 0)
                self.assertIn(
                    "CAT_EXITED",
                    payload.get("command_stdout") or "",
                    "cat must have seen EOF and exited cleanly; if this hangs, --stdin none is broken",
                )

    def test_auto_stdin_detects_wrapped_codex_js_exec(self) -> None:
        from ait.runner import _resolve_stdin_mode

        mode = _resolve_stdin_mode(
            adapter_name="codex",
            command=["/opt/codex/bin/codex.js", "exec", "prompt from argv"],
            requested_stdin_mode="auto",
            command_stdin=None,
            stdio_is_tty=False,
        )

        self.assertEqual("none", mode)

    def test_auto_stdin_does_not_treat_unrelated_exec_arg_as_codex_exec(self) -> None:
        from ait.runner import _resolve_stdin_mode

        mode = _resolve_stdin_mode(
            adapter_name="codex",
            command=["echo", "exec"],
            requested_stdin_mode="auto",
            command_stdin=None,
            stdio_is_tty=False,
        )

        self.assertEqual("inherit", mode)

    def test_stdin_none_gives_mock_command_eof_even_when_parent_has_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            completed = _run_ait_cli_subprocess(
                repo_root,
                [
                    "run",
                    "--adapter",
                    "shell",
                    "--stdin",
                    "none",
                    "--intent",
                    "stdin none mock command",
                    "--no-auto-commit",
                    "--format",
                    "json",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; print('stdin=' + repr(sys.stdin.read()))",
                ],
                stdin_text="parent stdin should not reach child",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(0, payload["exit_code"])
        self.assertIn("stdin=''", payload["command_stdout"])

    def test_codex_exec_auto_stdin_none_for_noninteractive_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _init_git_repo(repo_root)
            bin_dir = Path(tmp) / "bin"
            _write_mock_codex(bin_dir)
            completed = _run_ait_cli_subprocess(
                repo_root,
                [
                    "run",
                    "--adapter",
                    "codex",
                    "--intent",
                    "codex exec auto stdin",
                    "--no-auto-commit",
                    "--format",
                    "json",
                    "--",
                    "codex",
                    "exec",
                    "prompt from argv",
                ],
                stdin_text="parent stdin should not reach codex exec",
                path_prefix=bin_dir,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(0, payload["exit_code"])
        self.assertIn("stdin=''", payload["command_stdout"])
        self.assertIn("args=['exec', 'prompt from argv']", payload["command_stdout"])
        self.assertNotIn("may wait for stdin EOF", completed.stderr)

    def test_codex_exec_explicit_inherit_keeps_parent_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            _init_git_repo(repo_root)
            bin_dir = Path(tmp) / "bin"
            _write_mock_codex(bin_dir)
            completed = _run_ait_cli_subprocess(
                repo_root,
                [
                    "run",
                    "--adapter",
                    "codex",
                    "--stdin",
                    "inherit",
                    "--intent",
                    "codex exec inherited stdin",
                    "--no-auto-commit",
                    "--format",
                    "json",
                    "--",
                    "codex",
                    "exec",
                    "prompt from argv",
                ],
                stdin_text="parent stdin reaches explicit inherit",
                path_prefix=bin_dir,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(0, payload["exit_code"])
        self.assertIn("stdin='parent stdin reaches explicit inherit'", payload["command_stdout"])


class CliRunWrapperWarningTests(unittest.TestCase):
    """Tests for the pre-run wrapper-not-installed warning.

    `ait run --adapter <name>` runs against an adapter even when that adapter's
    repo-local wrapper has not been installed via `ait init --adapter <name>`.
    In that case ait cannot capture the wrapped agent's internal tool events,
    the verifier sees zero evidence, and the attempt gets marked failed —
    which is confusing if the user did not realise the wrapper was missing.
    The fix prints a one-line stderr warning before the run starts.
    """

    def test_shell_adapter_does_not_emit_wrapper_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            with chdir(repo_root):
                stderr_buf = io.StringIO()
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--adapter",
                            "shell",
                            "--no-auto-commit",
                            "--stdin",
                            "none",
                            "--intent",
                            "shell no wrapper concept",
                            "--format",
                            "json",
                            "--",
                            "echo",
                            "ok",
                        ],
                    ),
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(stderr_buf),
                ):
                    code = cli.main()
                self.assertEqual(code, 0)
                self.assertNotIn(
                    "wrapper is not active",
                    stderr_buf.getvalue(),
                    "shell adapter has no wrapper concept; warning must stay silent",
                )

    def test_codex_adapter_without_init_emits_wrapper_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            with chdir(repo_root):
                stderr_buf = io.StringIO()
                with (
                    patch(
                        "sys.argv",
                        [
                            "ait",
                            "run",
                            "--adapter",
                            "codex",
                            "--no-auto-commit",
                            "--stdin",
                            "none",
                            "--intent",
                            "codex without ait init",
                            "--format",
                            "json",
                            "--",
                            "echo",
                            "ok",
                        ],
                    ),
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(stderr_buf),
                ):
                    code = cli.main()
                self.assertEqual(code, 0)
                stderr_text = stderr_buf.getvalue()
                self.assertIn("wrapper is not active", stderr_text)
                self.assertIn("ait init --adapter codex", stderr_text)


if __name__ == "__main__":
    unittest.main()
