from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ait import cli


class CliRunTests(unittest.TestCase):
    def test_run_json_format_outputs_parseable_json_with_command_output(self) -> None:
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
                        "Capture output",
                        "--",
                        sys.executable,
                        "-c",
                        "import sys; print('agent out'); print('agent err', file=sys.stderr)",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(0, payload["exit_code"])
        self.assertEqual("agent out\n", payload["command_stdout"])
        self.assertEqual("agent err\n", payload["command_stderr"])

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
        self.assertIn("AIT run", stderr.getvalue())
        self.assertIn("Exit code: 0", stderr.getvalue())

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
                        "--",
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('graph.txt').write_text('ok\\n')",
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
            self.assertIn("Build graph report", graph_text)
            self.assertIn("Attempt 1", graph_text)
            self.assertIn("graph.txt", graph_text)
            self.assertIn(run_payload["attempt_id"].rsplit(":", 1)[-1][:8], graph_text)
            self.assertIn("wrote", html_stdout.getvalue())
            self.assertIn("AIT Work Graph", html)
            self.assertIn("Attempt Status", html)
            self.assertIn("Hot Files", html)
            self.assertIn("<details", html)
            self.assertIn("Build graph report", html)
            self.assertIn("graph.txt", html)

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
        self.assertEqual(["attempt-memory:*", "agent-memory:*"], show_payload["recall_source_allow"])
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


def _git_stdout(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    unittest.main()
