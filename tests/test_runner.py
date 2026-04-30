from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from ait.db import connect_db, list_memory_retrieval_events
from ait.memory import list_memory_notes, search_repo_memory
from ait.runner import _run_command_with_pty_transcript, _strip_terminal_control, run_agent_command


class RunnerTests(unittest.TestCase):
    def test_run_agent_command_records_command_and_finishes_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Run command",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                ],
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual("succeeded", result.attempt.outcome["outcome_class"])
            self.assertEqual("shell:local", result.attempt.attempt["agent_id"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_tool_calls"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_commands_run"])
            self.assertTrue((Path(result.workspace_ref) / "agent.txt").exists())
            self.assertEqual(1, len(result.attempt.commits))
            self.assertFalse(_git_stdout(Path(result.workspace_ref), "status", "--short"))
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())

    def test_run_agent_command_self_repairs_memory_policy_and_imports_agent_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Prefer direct wrapped agent CLI use.\n", encoding="utf-8")

            result = run_agent_command(
                repo_root,
                intent_title="Self repair memory",
                command=[sys.executable, "-c", "print('ok')"],
                capture_command_output=True,
            )

            notes = list_memory_notes(repo_root, topic="agent-memory")

            self.assertEqual(0, result.exit_code)
            self.assertTrue((repo_root / ".ait" / "memory-policy.json").exists())
            self.assertEqual(1, len(notes))
            self.assertEqual("agent-memory:claude:CLAUDE.md", notes[0].source)

    def test_run_agent_command_returns_process_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Fail command",
                agent_id="shell:test",
                command=[sys.executable, "-c", "raise SystemExit(7)"],
            )

            self.assertEqual(7, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("failed", result.attempt.attempt["verified_status"])
            self.assertEqual("failed_with_evidence", result.attempt.outcome["outcome_class"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_commands_run"])

    def test_run_agent_command_records_missing_command_as_failed_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Missing command",
                command=["/definitely/missing/ait-agent-binary"],
                capture_command_output=True,
            )

            self.assertEqual(127, result.exit_code)
            self.assertEqual("", result.command_stdout)
            self.assertIn("ait run failed: command not executable", result.command_stderr or "")
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("failed", result.attempt.attempt["verified_status"])
            self.assertEqual("failed_infra", result.attempt.outcome["outcome_class"])
            self.assertEqual(1, result.attempt.evidence_summary["observed_commands_run"])

    def test_run_agent_command_can_capture_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Capture command",
                command=[
                    sys.executable,
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr)",
                ],
                capture_command_output=True,
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("out\n", result.command_stdout)
            self.assertEqual("err\n", result.command_stderr)

    def test_run_agent_command_finalizes_locally_if_finish_is_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            def interrupt_finish(harness, **kwargs):
                del kwargs
                harness._finish_attempted = True
                raise KeyboardInterrupt

            with patch("ait.runner.AitHarness.finish", interrupt_finish):
                result = run_agent_command(
                    repo_root,
                    intent_title="Interrupted finish",
                    command=[sys.executable, "-c", "print('finished before interrupt')"],
                    capture_command_output=True,
                )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual(0, result.attempt.attempt["result_exit_code"])
            self.assertIsNotNone(result.attempt.attempt["raw_trace_ref"])

    def test_run_agent_command_can_write_context_file_for_wrapped_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Context file",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "p=Path(os.environ['AIT_CONTEXT_FILE']);"
                        "Path('context-copy.txt').write_text(p.read_text())"
                    ),
                ],
                with_context=True,
            )

            copied = Path(result.workspace_ref) / "context-copy.txt"
            self.assertEqual(0, result.exit_code)
            self.assertFalse((Path(result.workspace_ref) / ".ait-context.md").exists())
            self.assertTrue((repo_root / ".ait" / "brain" / "graph.json").exists())
            self.assertTrue((repo_root / ".ait" / "brain" / "REPORT.md").exists())
            self.assertIn("Intent: Context file", copied.read_text(encoding="utf-8"))
            self.assertIn("AIT Long-Term Repo Memory", copied.read_text(encoding="utf-8"))
            self.assertIn("AIT Relevant Memory", copied.read_text(encoding="utf-8"))
            self.assertIn("AIT Repo Brain Briefing", copied.read_text(encoding="utf-8"))
            self.assertIn("Briefing Query Sources:", copied.read_text(encoding="utf-8"))
            self.assertIn("command_args:", copied.read_text(encoding="utf-8"))
            self.assertIn("agent:", copied.read_text(encoding="utf-8"))
            self.assertNotIn("Edges:", copied.read_text(encoding="utf-8"))

    def test_run_agent_command_records_memory_retrieval_events_for_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            first = run_agent_command(
                repo_root,
                intent_title="Seed memory",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    "print('以後所有 release 必須先跑 pytest。')",
                ],
                capture_command_output=True,
            )
            second = run_agent_command(
                repo_root,
                intent_title="Use release memory",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "Path('context-copy.txt').write_text(Path(os.environ['AIT_CONTEXT_FILE']).read_text())"
                    ),
                ],
                with_context=True,
            )

            conn = connect_db(repo_root / ".ait" / "state.sqlite3")
            self.addCleanup(conn.close)
            events = list_memory_retrieval_events(conn, attempt_id=second.attempt_id)
            copied = (Path(second.workspace_ref) / "context-copy.txt").read_text(encoding="utf-8")

            self.assertEqual(0, first.exit_code)
            self.assertEqual(0, second.exit_code)
            self.assertEqual(1, len(events))
            self.assertTrue(events[0].selected_fact_ids)
            self.assertIn("release 必須先跑 pytest", copied)

    def test_run_agent_command_auto_imports_agent_memory_before_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / "CLAUDE.md").write_text("Use repair before release.\n", encoding="utf-8")

            result = run_agent_command(
                repo_root,
                intent_title="Auto memory",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "p=Path(os.environ['AIT_CONTEXT_FILE']);"
                        "Path('context-copy.txt').write_text(p.read_text())"
                    ),
                ],
                with_context=True,
            )

            copied = Path(result.workspace_ref) / "context-copy.txt"
            notes = list_memory_notes(repo_root, topic="agent-memory")

            self.assertEqual(0, result.exit_code)
            self.assertEqual(1, len(notes))
            self.assertIn("Use repair before release.", notes[0].body)
            self.assertIn("Use repair before release.", copied.read_text(encoding="utf-8"))

    def test_run_agent_command_adds_attempt_memory_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Remember successful attempt",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                ],
                commit_message="commit generated change",
            )

            notes = list_memory_notes(repo_root, topic="attempt-memory")

            self.assertEqual(0, result.exit_code)
            self.assertEqual(1, len(notes))
            self.assertEqual(f"attempt-memory:{result.attempt_id}", notes[0].source)
            self.assertIn("confidence=high", notes[0].body)
            self.assertIn("intent_title=Remember successful attempt", notes[0].body)
            self.assertIn("verified_status=succeeded", notes[0].body)
            self.assertIn("outcome_class=succeeded", notes[0].body)
            self.assertIn("changed_files=agent.txt", notes[0].body)
            self.assertIn(result.attempt.commits[0]["commit_oid"], notes[0].body)

    def test_next_context_includes_relevant_attempt_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            first = run_agent_command(
                repo_root,
                intent_title="Billing adapter retry path",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('billing_retry.py').write_text('ok\\n')",
                ],
                commit_message="add billing retry path",
            )
            second = run_agent_command(
                repo_root,
                intent_title="Improve billing adapter retry path",
                agent_id="shell:test",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "p=Path(os.environ['AIT_CONTEXT_FILE']);"
                        "Path('context-copy.txt').write_text(p.read_text())"
                    ),
                ],
                with_context=True,
            )

            copied = (Path(second.workspace_ref) / "context-copy.txt").read_text(encoding="utf-8")

            self.assertEqual(0, first.exit_code)
            self.assertEqual(0, second.exit_code)
            self.assertIn("AIT Relevant Memory", copied)
            self.assertIn(f"attempt-memory:{first.attempt_id}", copied)
            self.assertIn("Billing adapter retry path", copied)
            self.assertIn("changed_files=billing_retry.py", copied)

    def test_run_agent_command_adds_failed_attempt_memory_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Remember failed attempt",
                agent_id="shell:test",
                command=[sys.executable, "-c", "raise SystemExit(5)"],
            )

            notes = list_memory_notes(repo_root, topic="attempt-memory")

            self.assertEqual(5, result.exit_code)
            self.assertEqual(1, len(notes))
            self.assertEqual(f"attempt-memory:{result.attempt_id}", notes[0].source)
            self.assertIn("confidence=advisory", notes[0].body)
            self.assertIn("verified_status=failed", notes[0].body)
            self.assertIn("exit_code=5", notes[0].body)

    def test_claude_code_adapter_defaults_to_context_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Claude adapter",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "from pathlib import Path;"
                        "Path('adapter.txt').write_text("
                        "os.environ['AIT_ADAPTER'] + '\\n' + "
                        "Path(os.environ['AIT_CONTEXT_FILE']).read_text())"
                    ),
                ],
            )

            output = (Path(result.workspace_ref) / "adapter.txt").read_text(encoding="utf-8")
            self.assertEqual(0, result.exit_code)
            self.assertEqual("claude-code:manual", result.attempt.attempt["agent_id"])
            self.assertTrue(output.startswith("claude-code\nIntent: Claude adapter"))

    def test_aider_and_codex_adapters_default_to_context_and_env(self) -> None:
        for adapter_name, expected_agent in (("aider", "aider:main"), ("codex", "codex:main")):
            with self.subTest(adapter=adapter_name):
                with tempfile.TemporaryDirectory() as tmp:
                    repo_root = Path(tmp)
                    _init_git_repo(repo_root)

                    result = run_agent_command(
                        repo_root,
                        intent_title=f"{adapter_name} adapter",
                        adapter_name=adapter_name,
                        command=[
                            sys.executable,
                            "-c",
                            (
                                "import os;"
                                "from pathlib import Path;"
                                "Path('adapter.txt').write_text("
                                "os.environ['AIT_ADAPTER'] + '\\n' + "
                                "os.environ['AIT_CONTEXT_HINT'] + '\\n' + "
                                "Path(os.environ['AIT_CONTEXT_FILE']).read_text())"
                            ),
                        ],
                    )

                    output = (Path(result.workspace_ref) / "adapter.txt").read_text(encoding="utf-8")
                    self.assertEqual(0, result.exit_code)
                    self.assertEqual(expected_agent, result.attempt.attempt["agent_id"])
                    self.assertTrue(output.startswith(f"{adapter_name}\nRead AIT_CONTEXT_FILE"))
                    self.assertIn(f"Intent: {adapter_name} adapter", output)

    def test_agent_adapters_capture_transcript_for_memory_search(self) -> None:
        adapters = (
            ("aider", "AIDER_TRANSCRIPT_TOKEN"),
            ("claude-code", "CLAUDE_TRANSCRIPT_TOKEN"),
            ("codex", "CODEX_TRANSCRIPT_TOKEN"),
            ("cursor", "CURSOR_TRANSCRIPT_TOKEN"),
            ("gemini", "GEMINI_TRANSCRIPT_TOKEN"),
        )
        for adapter_name, expected_token in adapters:
            with self.subTest(adapter=adapter_name):
                with tempfile.TemporaryDirectory() as tmp:
                    repo_root = Path(tmp)
                    _init_git_repo(repo_root)

                    result = run_agent_command(
                        repo_root,
                        intent_title=f"{adapter_name} transcript",
                        adapter_name=adapter_name,
                        command=[
                            sys.executable,
                            "-c",
                            f"print('{expected_token} useful transcript evidence')",
                        ],
                        capture_command_output=True,
                    )

                    raw_trace_ref = result.attempt.attempt["raw_trace_ref"]
                    trace_path = repo_root / raw_trace_ref
                    search_results = search_repo_memory(repo_root, expected_token)

                    self.assertEqual(0, result.exit_code)
                    self.assertTrue(raw_trace_ref.startswith(".ait/traces/"))
                    self.assertIn(expected_token, trace_path.read_text(encoding="utf-8"))
                    self.assertEqual("attempt", search_results[0].kind)
                    self.assertEqual(result.attempt_id, search_results[0].id)

    def test_codex_transcript_redacts_secrets_before_memory_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Codex secret transcript",
                adapter_name="codex",
                command=[
                    sys.executable,
                    "-c",
                    "print('api token sk-abcdefghijklmnopqrstuvwxyz123456')",
                ],
                capture_command_output=True,
            )

            raw_trace_ref = result.attempt.attempt["raw_trace_ref"]
            trace_text = (repo_root / raw_trace_ref).read_text(encoding="utf-8")
            search_results = search_repo_memory(repo_root, "redacted")

            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", trace_text)
            self.assertIn("[REDACTED]", trace_text)
            self.assertIn("Redacted: true", trace_text)
            self.assertEqual("attempt", search_results[0].kind)
            self.assertTrue(search_results[0].metadata["redacted"])
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", search_results[0].text)

    def test_codex_transcript_policy_excludes_sensitive_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            (repo_root / ".ait").mkdir(exist_ok=True)
            (repo_root / ".ait" / "memory-policy.json").write_text(
                json.dumps(
                    {
                        "exclude_paths": [".env"],
                        "exclude_transcript_patterns": ["BEGIN PRIVATE KEY"],
                    }
                ),
                encoding="utf-8",
            )

            result = run_agent_command(
                repo_root,
                intent_title="Codex private transcript",
                adapter_name="codex",
                command=[
                    sys.executable,
                    "-c",
                    "print('BEGIN PRIVATE KEY SECRET_TRANSCRIPT_TOKEN')",
                ],
                capture_command_output=True,
            )

            raw_trace_ref = result.attempt.attempt["raw_trace_ref"]
            trace_text = (repo_root / raw_trace_ref).read_text(encoding="utf-8")
            search_results = search_repo_memory(repo_root, "SECRET_TRANSCRIPT_TOKEN")

            self.assertEqual(0, result.exit_code)
            self.assertIn("Excluded-By-Memory-Policy: true", trace_text)
            self.assertIn("[EXCLUDED BY MEMORY POLICY]", trace_text)
            self.assertNotIn("BEGIN PRIVATE KEY", trace_text)
            self.assertNotIn("SECRET_TRANSCRIPT_TOKEN", trace_text)
            self.assertEqual((), search_results)

    def test_run_agent_command_commit_message_stages_commits_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Commit generated change",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                ],
                commit_message="commit generated change",
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual(("agent.txt",), result.attempt.files["changed"])
            self.assertEqual(1, len(result.attempt.commits))
            self.assertFalse((Path(result.workspace_ref) / ".ait-context.md").exists())
            self.assertFalse(_git_stdout(Path(result.workspace_ref), "status", "--short"))

    def test_run_agent_command_suppresses_keyboard_interrupt_during_auto_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            with patch("ait.runner._stage_all_changes", side_effect=KeyboardInterrupt):
                result = run_agent_command(
                    repo_root,
                    intent_title="Interrupted auto commit",
                    adapter_name="claude-code",
                    command=[
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                    ],
                    commit_message="commit generated change",
                )

            self.assertEqual(130, result.exit_code)
            self.assertEqual("finished", result.attempt.attempt["reported_status"])
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual(0, result.attempt.attempt["result_exit_code"])
            self.assertEqual([], result.attempt.commits)

    def test_run_agent_command_commit_message_allows_no_change_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="No generated change",
                adapter_name="claude-code",
                command=[sys.executable, "-c", "print('no changes')"],
                commit_message="commit generated change",
                capture_command_output=True,
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual("no changes\n", result.command_stdout)
            self.assertEqual("succeeded", result.attempt.attempt["verified_status"])
            self.assertEqual("succeeded_noop", result.attempt.outcome["outcome_class"])
            self.assertEqual([], result.attempt.commits)
            self.assertEqual({}, result.attempt.files)
            self.assertFalse((Path(result.workspace_ref) / ".ait-context.md").exists())
            self.assertFalse(_git_stdout(Path(result.workspace_ref), "status", "--short"))

    def test_run_agent_command_noop_does_not_create_durable_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            run_agent_command(
                repo_root,
                intent_title="Chat only",
                command=[sys.executable, "-c", "print('hi')"],
                capture_command_output=True,
            )

            self.assertEqual((), list_memory_notes(repo_root, topic="durable-memory"))

    def test_run_agent_command_promotes_rule_memory_without_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Rule only",
                command=[sys.executable, "-c", "print('以後所有 API route 必須使用 zod 驗證。')"],
                capture_command_output=True,
            )

            durable_notes = list_memory_notes(repo_root, topic="durable-memory")

            self.assertEqual("succeeded", result.attempt.outcome["outcome_class"])
            self.assertEqual(1, len(durable_notes))
            self.assertIn("API route", durable_notes[0].body)

    def test_run_agent_command_marks_refusal_without_changes_as_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Refused generated change",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    "print(\"I don't have permission to write files in this mode\")",
                ],
                commit_message="commit generated change",
                capture_command_output=True,
            )

            self.assertEqual(3, result.exit_code)
            self.assertEqual("failed", result.attempt.attempt["verified_status"])
            self.assertEqual([], result.attempt.commits)

    def test_pty_runner_tees_interactive_output_for_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)

            completed = _run_command_with_pty_transcript(
                [
                    sys.executable,
                    "-c",
                    "print('AIT_PTY_TRANSCRIPT_TOKEN')",
                ],
                cwd=repo_root,
                env={},
            )

            self.assertEqual(0, completed.returncode)
            self.assertIn("AIT_PTY_TRANSCRIPT_TOKEN", completed.stdout)

    def test_run_agent_command_writes_normalized_transcript_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Normalize transcript",
                adapter_name="codex",
                command=[
                    sys.executable,
                    "-c",
                    "print('WorkingWorkingWorking'); print('你是誰?'); print('我是 Codex')",
                ],
                capture_command_output=True,
            )

            raw_trace = repo_root / result.attempt.attempt["raw_trace_ref"]
            normalized_trace = raw_trace.parent / "normalized" / raw_trace.name
            normalized_text = normalized_trace.read_text(encoding="utf-8")

            self.assertTrue(raw_trace.exists())
            self.assertTrue(normalized_trace.exists())
            self.assertIn("WorkingWorkingWorking", raw_trace.read_text(encoding="utf-8"))
            self.assertNotIn("WorkingWorkingWorking", normalized_text.split("STDOUT:", 1)[1])
            self.assertIn("你是誰?", normalized_text)
            self.assertIn("我是 Codex", normalized_text)

    def test_transcript_sanitizer_removes_terminal_control_sequences(self) -> None:
        text = "\x1b[?25hhello\r\n\x1b]0;title\x07world\x1b[0m"

        self.assertEqual("hello\nworld", _strip_terminal_control(text))

    def test_run_agent_command_can_disable_default_auto_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Leave generated change uncommitted",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('agent.txt').write_text('ok\\n')",
                ],
                auto_commit=False,
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual([], result.attempt.commits)
            self.assertIn("agent.txt", _git_stdout(Path(result.workspace_ref), "status", "--short"))

    def test_run_agent_command_does_not_duplicate_agent_created_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)

            result = run_agent_command(
                repo_root,
                intent_title="Agent commits its own change",
                adapter_name="claude-code",
                command=[
                    sys.executable,
                    "-c",
                    (
                        "import subprocess;"
                        "from pathlib import Path;"
                        "Path('agent.txt').write_text('ok\\n');"
                        "subprocess.run(['git','add','agent.txt'], check=True);"
                        "subprocess.run(['git','commit','-m','agent self commit'], check=True)"
                    ),
                ],
            )

            self.assertEqual(0, result.exit_code)
            self.assertEqual(1, len(result.attempt.commits))
            self.assertEqual("agent self commit", _git_stdout(Path(result.workspace_ref), "log", "-1", "--pretty=%s"))
            self.assertFalse(_git_stdout(Path(result.workspace_ref), "status", "--short"))


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


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
