from __future__ import annotations

from contextlib import chdir, redirect_stderr, redirect_stdout
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ait import cli
from ait.app import init_repo
from ait.db import connect_db, list_memory_facts


class CliSessionTests(unittest.TestCase):
    def test_session_start_ask_show_export_does_not_mutate_root_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)

            start = _run_cli_json(repo, "session", "start", "Refactor auth", "--agents", "fake:one,fake:two", "--format", "json")
            ask = _run_cli_json(repo, "session", "ask", "latest", "What is safe?", "--format", "json")
            show = _run_cli_json(repo, "session", "show", "latest", "--format", "json")
            export = _run_cli_text(repo, "session", "export", "latest", "--format", "md")

            self.assertEqual(start["state"], "active")
            self.assertEqual(ask["current_turn_id"], "turn_0001")
            self.assertEqual(show["kind"], "session_state")
            self.assertIn("AIT Session: Refactor auth", export)
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_panel_mode_records_separate_fake_agent_responses_and_partial_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Panel", "--agents", "fake:one,fake:fail", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Compare approaches", "--format", "json")

            payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")

            self.assertEqual("awaiting_decision", payload["state"])
            self.assertEqual("panel", payload["mode"])
            self.assertEqual(2, len(payload["responses"]))
            self.assertEqual({"fake:one", "fake:fail"}, {item["agent_id"] for item in payload["responses"]})
            self.assertEqual(["fake:fail"], [item["agent_id"] for item in payload["partial_failures"]])
            self.assertNotEqual(
                payload["responses"][0]["context_manifest_ref"],
                payload["responses"][1]["context_manifest_ref"],
            )

    def test_panel_mode_can_run_explicit_local_command_agent_with_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            command = (
                f"{sys.executable} -c \"import os; "
                "print('ctx=' + str(os.path.exists(os.environ['AIT_CONTEXT_FILE'])))\""
            )
            _run_cli_json(
                repo,
                "session",
                "start",
                "Local",
                "--agents",
                "local",
                "--agent-command",
                f"local={command}",
                "--format",
                "json",
            )
            _run_cli_json(repo, "session", "ask", "latest", "Use local command", "--format", "json")

            payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            stdout = (repo / payload["responses"][0]["provenance_refs"]["stdout_ref"]).read_text(encoding="utf-8")

            self.assertIn("ctx=True", stdout)
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_panel_mode_invokes_real_adapter_cli_when_no_agent_command_is_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            with tempfile.TemporaryDirectory() as bin_tmp:
                bin_dir = Path(bin_tmp)
                fake_codex = bin_dir / "codex"
                fake_codex.write_text(
                    "#!/bin/sh\n"
                    "printf 'argv=%s\\n' \"$*\"\n"
                    "printf 'ctx=%s\\n' \"$AIT_CONTEXT_FILE\"\n"
                    "printf 'stdin=' \n"
                    "cat\n",
                    encoding="utf-8",
                )
                fake_codex.chmod(0o755)
                start = _run_cli_json(
                    repo,
                    "session",
                    "start",
                    "Real invocation",
                    "--agents",
                    "codex",
                    "--codex-sandbox",
                    "workspace-write",
                    "--codex-approval",
                    "on-request",
                    "--format",
                    "json",
                )
                _run_cli_json(repo, "session", "ask", "latest", "Use real agent?", "--format", "json")

                with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                    payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            stdout = (repo / payload["responses"][0]["provenance_refs"]["stdout_ref"]).read_text(encoding="utf-8")
            command = (repo / payload["responses"][0]["command_ref"]).read_text(encoding="utf-8")

            self.assertEqual("workspace-write", start["permission_policy"]["codex_sandbox"])
            self.assertEqual("on-request", start["permission_policy"]["codex_approval"])
            self.assertIn("argv=exec --sandbox workspace-write -", stdout)
            self.assertNotIn("--ask-for-approval", stdout)
            self.assertIn("ctx=", stdout)
            self.assertIn("Use real agent?", stdout)
            self.assertIn("codex", command)
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_session_start_records_claude_permission_consent_for_panel_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            with tempfile.TemporaryDirectory() as bin_tmp:
                bin_dir = Path(bin_tmp)
                fake_claude = bin_dir / "claude"
                fake_claude.write_text(
                    "#!/bin/sh\n"
                    "printf 'argv=%s\\n' \"$*\"\n"
                    "cat\n",
                    encoding="utf-8",
                )
                fake_claude.chmod(0o755)
                start = _run_cli_json(
                    repo,
                    "session",
                    "start",
                    "Claude permissions",
                    "--agents",
                    "claude-code",
                    "--claude-permission-mode",
                    "bypassPermissions",
                    "--format",
                    "json",
                )
                _run_cli_json(repo, "session", "ask", "latest", "Use agreed permission mode", "--format", "json")

                with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                    payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            stdout = (repo / payload["responses"][0]["provenance_refs"]["stdout_ref"]).read_text(encoding="utf-8")

            self.assertEqual("bypassPermissions", start["permission_policy"]["claude_code_permission_mode"])
            self.assertIn("argv=-p --permission-mode bypassPermissions", stdout)
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_session_start_prompts_for_real_agent_permission_policy_in_tty_text_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            fake_stdin = Mock()
            fake_stdin.isatty.return_value = True
            # Python 3.14 added color support to argparse, which calls
            # `os.isatty(file.fileno())` on sys.stdout during formatter
            # construction. A bare Mock returns another Mock from
            # `fileno()`, and `os.isatty(<Mock>)` raises
            # `TypeError: 'Mock' object cannot be interpreted as an integer`.
            # Pin fileno to a real int so the colorize probe completes;
            # the actual color decision is irrelevant to this test.
            fake_stdin.fileno.return_value = 0
            fake_stdout = Mock()
            fake_stdout.isatty.return_value = True
            fake_stdout.fileno.return_value = 1
            answers = iter(["dontAsk", "workspace-write", "on-request"])

            # JSON mode is automation-safe and does not prompt.
            payload = _run_cli_json(repo, "session", "start", "Prompt", "--agents", "claude-code,codex", "--format", "json")
            self.assertEqual("plan", payload["permission_policy"]["claude_code_permission_mode"])

            stderr = io.StringIO()
            with chdir(repo):
                with patch("sys.argv", ["ait", "session", "start", "Prompt text", "--agents", "claude-code,codex"]):
                    with patch("sys.stdin", fake_stdin), patch("sys.stdout", fake_stdout), patch("builtins.input", side_effect=lambda _prompt: next(answers)):
                        with redirect_stderr(stderr):
                            exit_code = cli.main()
            self.assertEqual(0, exit_code, stderr.getvalue())
            sessions = _run_cli_json(repo, "session", "list", "--format", "json")["sessions"]
            prompted_session_id = next(item["session_id"] for item in sessions if item["title"] == "Prompt text")
            show = _run_cli_json(repo, "session", "show", prompted_session_id, "--format", "json")
            self.assertEqual("dontAsk", show["permission_policy"]["claude_code_permission_mode"])
            self.assertEqual("workspace-write", show["permission_policy"]["codex_sandbox"])
            self.assertEqual("on-request", show["permission_policy"]["codex_approval"])

    def test_timeout_and_cancelled_fake_agents_store_partial_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Timeout", "--agents", "fake:sleep:99,fake:cancel", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Run slow agents", "--format", "json")

            payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--timeout", "1", "--format", "json")
            states = {item["agent_id"]: item["state"] for item in payload["responses"]}

            self.assertEqual("timed_out", states["fake:sleep:99"])
            self.assertEqual("cancelled", states["fake:cancel"])
            timed_out = next(item for item in payload["responses"] if item["agent_id"] == "fake:sleep:99")
            raw = (repo / timed_out["provenance_refs"]["raw_trace_ref"]).read_text(encoding="utf-8")
            self.assertIn("started", raw)

    def test_retry_creates_new_response_linked_to_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Retry", "--agents", "fake:fail", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Try once", "--format", "json")
            first = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            original_id = first["responses"][0]["response_id"]

            retried = _run_cli_json(repo, "session", "retry", "latest", "--response", original_id, "--format", "json")
            response_ids = [item["response_id"] for item in retried["responses"]]
            new_id = next(item for item in response_ids if item != original_id)
            new_response = json.loads((repo / ".ait" / "sessions" / retried["session_id"] / "responses" / f"{new_id}.json").read_text(encoding="utf-8"))

            self.assertIn(original_id, response_ids)
            self.assertEqual(original_id, new_response["provenance"]["retry_of_response_id"])

    def test_context_manifest_excludes_policy_blocked_memory_and_marks_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            (repo / "AGENTS.md").write_text("do not leak this memory\n", encoding="utf-8")
            (repo / "CLAUDE.md").write_text("allowed advisory memory\n", encoding="utf-8")
            (repo / ".ait").mkdir(exist_ok=True)
            (repo / ".ait" / "memory-policy.json").write_text(
                json.dumps({"recall_source_block": ["live-memory:codex:AGENTS.md"]}) + "\n",
                encoding="utf-8",
            )
            _run_cli_json(repo, "session", "start", "Memory", "--agents", "fake:one", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Use context", "--format", "json")
            payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")

            manifest_ref = payload["responses"][0]["context_manifest_ref"]
            manifest = json.loads((repo / manifest_ref).read_text(encoding="utf-8"))
            context_text = (repo / manifest["context_ref"]).read_text(encoding="utf-8")
            entries = {item["source_id"]: item for item in manifest["entries"]}

            self.assertEqual("ait.context_manifest", manifest["schema"])
            self.assertIn("advisory_response_refs", manifest)
            self.assertTrue(any(item["source_id"] == "live:codex:AGENTS.md" for item in manifest["policy_exclusions"]))
            self.assertEqual("policy_blocked", entries["live:codex:AGENTS.md"]["trust_level"])
            self.assertFalse(entries["live:codex:AGENTS.md"]["body_included"])
            self.assertEqual("advisory", entries["live:claude:CLAUDE.md"]["trust_level"])
            self.assertTrue(entries["live:claude:CLAUDE.md"]["included_in_context"])
            self.assertFalse(entries["live:claude:CLAUDE.md"]["trusted_baseline"])
            self.assertFalse(any(item == "live:codex:AGENTS.md" for item in manifest["trusted_baseline_refs"]))
            self.assertIn("allowed advisory memory", context_text)
            self.assertNotIn("do not leak this memory", context_text)
            self.assertNotIn("do not leak this memory", json.dumps(manifest))

    def test_redaction_before_transcript_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Secrets", "--agents", "fake:secret", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Find secrets", "--format", "json")
            payload = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")

            redacted_ref = payload["responses"][0]["provenance_refs"]["redacted_response_ref"]
            redacted = (repo / redacted_ref).read_text(encoding="utf-8")
            export = _run_cli_text(repo, "session", "export", "latest", "--format", "md")

            self.assertIn("TOKEN=[REDACTED]", redacted)
            self.assertIn("TOKEN=[REDACTED]", export)
            self.assertNotIn("super-secret-token-value", export)

    def test_decision_promote_memory_requires_explicit_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Decision", "--agents", "fake:one", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Remember this", "--format", "json")
            panel = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            response_id = panel["responses"][0]["response_id"]

            decision = _run_cli_json(repo, "session", "decision", "latest", "--accept", response_id, "--promote-memory", "--format", "json")
            init_result = init_repo(repo)
            conn = connect_db(init_result.db_path)
            try:
                facts = list_memory_facts(conn, status="accepted", kind="decision")
            finally:
                conn.close()

            self.assertEqual("active", decision["state"])
            self.assertTrue(any(str(fact.source_trace_ref or "").startswith(".ait/sessions/") for fact in facts))

    def test_session_attempt_from_advisory_response_creates_isolated_attempt_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Attempt", "--agents", "fake:one", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Create attempt candidate", "--format", "json")
            panel = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            response_id = panel["responses"][0]["response_id"]

            payload = _run_cli_json(repo, "session", "attempt", "latest", "--from", response_id, "--format", "json")

            self.assertTrue(payload["attempt"]["created"])
            self.assertTrue(payload["attempt"]["attempt_id"])
            self.assertFalse((repo / "session-attempts" / "from-response.txt").exists())
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_participant_add_remove_affects_future_turns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Participants", "--agents", "fake:one", "--format", "json")
            _run_cli_json(repo, "session", "participant", "add", "latest", "--agent", "fake:two", "--role", "panelist", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "first", "--format", "json")
            first = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")
            _run_cli_json(repo, "session", "participant", "remove", "latest", "--agent", "fake:two", "--reason", "done", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "second", "--format", "json")
            second = _run_cli_json(repo, "session", "run", "latest", "--mode", "panel", "--format", "json")

            self.assertEqual({"fake:one", "fake:two"}, {item["agent_id"] for item in first["responses"]})
            self.assertEqual({"fake:one"}, {item["agent_id"] for item in second["responses"] if item["response_id"] not in {r["response_id"] for r in first["responses"]}})

    def test_adaptive_allocation_dry_run_is_advisory_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Allocate", "--agents", "fake:one,fake:two", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Split it", "--format", "json")

            plan = _run_cli_json(
                repo,
                "session",
                "allocate",
                "latest",
                "--strategy",
                "adaptive",
                "--agents",
                "fake:one,fake:two",
                "--package",
                "backend=src/backend.py",
                "--package",
                "tests=tests/test_backend.py",
                "--dry-run",
                "--format",
                "json",
            )

            self.assertEqual("draft", plan["state"])
            self.assertTrue(plan["no_invocation"])
            self.assertTrue(plan["no_repo_mutation"])
            self.assertIn("scoring_factors", plan)
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_role_mode_separates_implementer_attempt_and_reviewer_evidence_without_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Role", "--agents", "fake:impl,fake:review", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Implement safely", "--format", "json")

            payload = _run_cli_json(
                repo,
                "session",
                "run",
                "latest",
                "--mode",
                "role",
                "--implementer",
                "fake:impl",
                "--reviewer",
                "fake:review",
                "--package",
                "backend=src/backend.txt",
                "--format",
                "json",
            )

            attempt_response = next(item for item in payload["responses"] if item["trust_class"] == "attempt_result")
            review_response = next(item for item in payload["responses"] if item["trust_class"] == "review_evidence")
            self.assertTrue(attempt_response["attempt_id"])
            self.assertTrue(review_response["review_id"])
            self.assertFalse((repo / "src" / "backend.txt").exists())
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_role_mode_invokes_real_implementer_adapter_in_isolated_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            with tempfile.TemporaryDirectory() as bin_tmp:
                bin_dir = Path(bin_tmp)
                fake_codex = bin_dir / "codex"
                fake_codex.write_text(
                    "#!/bin/sh\n"
                    "printf 'argv=%s\\n' \"$*\"\n"
                    "printf 'ctx=%s\\n' \"$AIT_CONTEXT_FILE\"\n"
                    "printf 'session=%s response=%s mode=%s role=%s package=%s\\n' "
                    "\"$AIT_SESSION_ID\" \"$AIT_RESPONSE_ID\" \"$AIT_SESSION_MODE\" \"$AIT_ROLE\" \"$AIT_PACKAGE_NAME\"\n"
                    "printf 'stdin-start\\n'\n"
                    "cat\n"
                    "mkdir -p src\n"
                    "printf 'real role implementation\\n' > src/backend.txt\n",
                    encoding="utf-8",
                )
                fake_codex.chmod(0o755)
                _run_cli_json(
                    repo,
                    "session",
                    "start",
                    "Role real",
                    "--agents",
                    "codex",
                    "--codex-sandbox",
                    "workspace-write",
                    "--format",
                    "json",
                )
                _run_cli_json(repo, "session", "ask", "latest", "Implement with real codex", "--format", "json")

                with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                    payload = _run_cli_json(
                        repo,
                        "session",
                        "run",
                        "latest",
                        "--mode",
                        "role",
                        "--implementer",
                        "codex",
                        "--package",
                        "backend=src/backend.txt",
                        "--format",
                        "json",
                    )

            response = payload["attempt_responses"][0]
            stdout = (repo / response["stdout_ref"]).read_text(encoding="utf-8")
            command = (repo / response["command_ref"]).read_text(encoding="utf-8")
            manifest = json.loads((repo / response["context_manifest_ref"]).read_text(encoding="utf-8"))
            workspace = Path(response["provenance"]["workspace_ref"])

            self.assertEqual("codex", response["adapter_name"])
            self.assertEqual("real_adapter", response["metadata_json"]["role_command_kind"])
            self.assertIn("argv=exec --sandbox workspace-write -", stdout)
            self.assertIn("mode=role role=implementer package=backend", stdout)
            self.assertIn("This is Role Mode", stdout)
            self.assertIn("Implement with real codex", stdout)
            self.assertIn("codex", command)
            self.assertIn("exec --sandbox workspace-write -", command)
            self.assertEqual({"role": "implementer", "package_name": "backend", "scope_paths": ["src/backend.txt"]}, manifest["role_assignment"])
            self.assertEqual(["src/backend.txt"], response["provenance"]["changed_files"])
            self.assertTrue((workspace / "src" / "backend.txt").exists())
            self.assertFalse((repo / "src" / "backend.txt").exists())
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_role_mode_invokes_real_reviewer_adapter_against_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            with tempfile.TemporaryDirectory() as bin_tmp:
                bin_dir = Path(bin_tmp)
                fake_codex = bin_dir / "codex"
                fake_codex.write_text(
                    f"#!{sys.executable}\n"
                    "import json, os, pathlib, sys\n"
                    "brief = sys.stdin.read()\n"
                    "pathlib.Path('reviewer-side.txt').write_text('reviewed', encoding='utf-8')\n"
                    "print(json.dumps({"
                    "'summary': 'codex role reviewer args=' + ' '.join(sys.argv[1:])"
                    " + ' brief=' + str(bool(brief)).lower()"
                    " + ' cwd=' + os.getcwd(),"
                    "'findings': []"
                    "}))\n",
                    encoding="utf-8",
                )
                fake_codex.chmod(0o755)
                _run_cli_json(
                    repo,
                    "session",
                    "start",
                    "Role review",
                    "--agents",
                    "fake:impl,codex",
                    "--format",
                    "json",
                )
                _run_cli_json(repo, "session", "ask", "latest", "Implement then review", "--format", "json")

                with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                    payload = _run_cli_json(
                        repo,
                        "session",
                        "run",
                        "latest",
                        "--mode",
                        "role",
                        "--implementer",
                        "fake:impl",
                        "--reviewer",
                        "codex",
                        "--package",
                        "backend=src/backend.txt",
                        "--format",
                        "json",
                    )

            review_response = payload["review_responses"][0]
            artifact = json.loads((repo / review_response["provenance"]["artifact_ref"]).read_text(encoding="utf-8"))
            adapter_invocation = artifact["adapter_invocation"]
            reviewer_cwd = Path(adapter_invocation["cwd"])

            self.assertEqual("codex", review_response["adapter_name"])
            self.assertEqual("real_adapter", review_response["metadata_json"]["role_command_kind"])
            self.assertEqual("adversarial", artifact["mode"])
            self.assertEqual("codex", artifact["reviewer_adapter"])
            self.assertEqual(["codex", "exec", "--sandbox", "read-only", "-"], adapter_invocation["command"])
            self.assertIn("codex role reviewer args=exec --sandbox read-only -", adapter_invocation["stdout"])
            self.assertIn("brief=true", adapter_invocation["stdout"])
            self.assertTrue((reviewer_cwd / "reviewer-side.txt").exists())
            self.assertFalse((repo / "reviewer-side.txt").exists())
            self.assertFalse((repo / "src" / "backend.txt").exists())
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_role_mode_failed_reviewer_marks_turn_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Role failed review", "--agents", "fake:impl,fake:malformed", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Implement then fail review", "--format", "json")

            payload = _run_cli_json(
                repo,
                "session",
                "run",
                "latest",
                "--mode",
                "role",
                "--implementer",
                "fake:impl",
                "--reviewer",
                "fake:malformed",
                "--package",
                "backend=src/backend.txt",
                "--format",
                "json",
            )

            review_response = payload["review_responses"][0]
            turn = json.loads(
                (
                    repo
                    / ".ait"
                    / "sessions"
                    / payload["session_id"]
                    / "turns"
                    / f"{payload['current_turn_id']}-turn.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("role", payload["mode"])
            self.assertEqual("partial", turn["state"])
            self.assertEqual("failed", review_response["state"])
            self.assertTrue(any("review failed: fake:malformed" in reason for reason in payload["blocking_reasons"]))
            self.assertTrue(any(item["agent_id"] == "fake:malformed" for item in payload["partial_failures"]))
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_split_implementation_disjoint_and_overlap_behaviors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Split", "--agents", "fake:a,fake:b", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Split work", "--format", "json")
            disjoint = _run_cli_json(
                repo,
                "session",
                "run",
                "latest",
                "--mode",
                "role",
                "--implementer",
                "fake:a",
                "--implementer",
                "fake:b",
                "--package",
                "a=src/a.txt",
                "--package",
                "b=src/b.txt",
                "--format",
                "json",
            )

            _run_cli_json(repo, "session", "ask", "latest", "Overlap work", "--format", "json")
            overlap = _run_cli_json(
                repo,
                "session",
                "run",
                "latest",
                "--mode",
                "role",
                "--implementer",
                "fake:a",
                "--implementer",
                "fake:b",
                "--package",
                "a=src/shared.txt",
                "--package",
                "b=src/shared.txt",
                "--format",
                "json",
            )

            self.assertEqual("ready", disjoint["integration"]["status"])
            self.assertEqual("blocked", overlap["integration"]["status"])
            self.assertIn("src/shared.txt", overlap["integration"]["overlap_files"])

    def test_attach_json_plan_does_not_start_pty_or_mutate_root_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Terminal", "--agents", "fake:one,fake:two", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Attach safely", "--format", "json")

            plan = _run_cli_json(repo, "session", "attach", "latest", "--format", "json")

            self.assertEqual("session_attach_plan", plan["kind"])
            self.assertEqual(2, len(plan["participants"]))
            self.assertTrue(all(not item["will_start_pty"] for item in plan["participants"]))
            self.assertEqual("pending", plan["daemon_ownership"]["state"])
            session_id = plan["session_id"]
            self.assertFalse((repo / ".ait" / "sessions" / session_id / "streams" / "events.jsonl").exists())
            self.assertEqual([], list((repo / ".ait" / "sessions" / session_id / "ptys").glob("*.json")))
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_foreground_attach_fake_ptys_routes_input_and_replays_with_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Terminal", "--agents", "fake:one,fake:two", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Attach safely", "--format", "json")

            _run_cli_text(
                repo,
                "session",
                "attach",
                "latest",
                "--input",
                "/to fake:one hello one",
                "--input",
                "/all status please",
                "--input",
                "/detach",
                "--terminate-on-detach",
            )
            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")
            replay = _run_cli_json(repo, "session", "replay", "latest", "--turn", "latest", "--format", "json")

            self.assertEqual("session_panes", panes["kind"])
            self.assertEqual(2, len(panes["panes"]))
            self.assertEqual(2, len({item["pty_id"] for item in panes["panes"]}))
            self.assertEqual(2, len({item["response_id"] for item in panes["panes"]}))
            self.assertTrue(all(item["context_manifest_ref"] for item in panes["panes"]))
            self.assertTrue(all(item["provenance_refs"]["raw_trace_ref"] for item in panes["panes"]))
            self.assertTrue(all(item["provenance_refs"]["redacted_response_ref"] for item in panes["panes"]))

            input_events = [item for item in replay["events"] if item["kind"] == "pty_input"]
            direct = [item for item in input_events if item["text"] == "hello one\n"]
            broadcast = [item for item in input_events if item["text"] == "status please\n"]
            self.assertEqual(["fake:one"], [item["agent_id"] for item in direct])
            self.assertEqual({"fake:one", "fake:two"}, {item["agent_id"] for item in broadcast})
            self.assertIn("[fake:one]", replay["text"])
            self.assertIn("[fake:two]", replay["text"])
            self.assertEqual("", _git_stdout(repo, "status", "--short"))

    def test_foreground_attach_sets_child_window_size(self) -> None:
        code = (
            "import fcntl, struct, sys, termios; "
            "rows, cols, _, _ = struct.unpack("
            "'HHHH', fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b'\\0' * 8)"
            "); "
            "print(f'WIN={rows}x{cols}', flush=True)"
        )
        command = f"{sys.executable} -c {shlex.quote(code)}"
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(
                repo,
                "session",
                "start",
                "Terminal size",
                "--agents",
                "local",
                "--agent-command",
                f"local={command}",
                "--format",
                "json",
            )
            _run_cli_json(repo, "session", "ask", "latest", "Report terminal size", "--format", "json")

            with patch(
                "ait.session_terminal.current_pty_window_size",
                return_value=SimpleNamespace(rows=32, cols=120),
            ):
                _run_cli_text(repo, "session", "attach", "latest")

            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")
            raw_ref = panes["panes"][0]["provenance_refs"]["raw_trace_ref"]
            raw_text = (repo / raw_ref).read_text(encoding="utf-8")
            self.assertIn("WIN=32x120", raw_text)

    def test_terminal_replay_and_export_redact_secrets_and_strip_escape_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Secrets", "--agents", "fake:secret,fake:ansi", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Capture terminal output", "--format", "json")

            _run_cli_text(repo, "session", "attach", "latest")
            replay = _run_cli_json(repo, "session", "replay", "latest", "--turn", "latest", "--format", "json")
            export = _run_cli_text(repo, "session", "export", "latest", "--format", "md")
            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")

            self.assertNotIn("super-secret-token-value", replay["text"])
            self.assertNotIn("super-secret-token-value", export)
            self.assertNotIn("\x1b", replay["text"])
            self.assertNotIn("\x1b", export)
            redacted_refs = [item["provenance_refs"]["redacted_response_ref"] for item in panes["panes"]]
            redacted_text = "\n".join((repo / ref).read_text(encoding="utf-8") for ref in redacted_refs)
            self.assertIn("TOKEN=[REDACTED]", redacted_text)
            self.assertNotIn("\x1b", redacted_text)

    def test_terminal_kill_and_detach_are_explicit_and_do_not_kill_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Kill", "--agents", "fake:codex,fake:claude", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Route safely", "--format", "json")

            payload_text = _run_cli_text(
                repo,
                "session",
                "attach",
                "latest",
                "--input",
                "/kill fake:codex",
                "--input",
                "/detach",
            )
            self.assertIn("foreground detach refused", payload_text)
            replay = _run_cli_json(repo, "session", "replay", "latest", "--turn", "latest", "--format", "json")
            cancelled = [item for item in replay["events"] if item["kind"] == "pty_cancelled"]

            killed = [item for item in cancelled if item["cancellation_reason"] == "killed by user"]
            cleanup = [item for item in cancelled if item["cancellation_reason"] == "foreground attach cleanup"]
            self.assertEqual(["fake:codex"], [item["agent_id"] for item in killed])
            self.assertEqual(["fake:claude"], [item["agent_id"] for item in cleanup])
            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")
            killed_pane = next(item for item in panes["panes"] if item["agent_id"] == "fake:codex")
            killed_raw = (repo / killed_pane["provenance_refs"]["raw_trace_ref"]).read_text(encoding="utf-8")
            self.assertIn("fake:codex ready", killed_raw)

            send = _run_cli_json(repo, "session", "send", "latest", "--to", "fake:claude", "hello", "--format", "json")
            send_all = _run_cli_json(repo, "session", "send", "latest", "--all", "hello all", "--format", "json")
            kill = _run_cli_json(repo, "session", "kill", "latest", "--agent", "fake:claude", "--format", "json")
            self.assertFalse(send["delivered"])
            self.assertFalse(send_all["delivered"])
            self.assertTrue(send["blocking_reasons"])
            self.assertEqual("pending", send_all["daemon_ownership"]["state"])
            self.assertEqual({"fake:codex", "fake:claude"}, {item["agent_id"] for item in send_all["targets"]})
            self.assertTrue(kill["blocking_reasons"])

    def test_terminal_stale_foreground_pty_is_marked_crashed_without_killing_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            _run_cli_json(repo, "session", "start", "Stale", "--agents", "fake:one,fake:two", "--format", "json")
            _run_cli_json(repo, "session", "ask", "latest", "Detect stale panes", "--format", "json")
            _run_cli_text(repo, "session", "attach", "latest")
            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")
            target = next(item for item in panes["panes"] if item["agent_id"] == "fake:one")
            sibling = next(item for item in panes["panes"] if item["agent_id"] == "fake:two")

            pane_path = repo / ".ait" / "sessions" / panes["session_id"] / "ptys" / f"{target['pty_id']}.json"
            stale = json.loads(pane_path.read_text(encoding="utf-8"))
            stale["state"] = "running"
            stale["pid"] = 2_147_483_647
            pane_path.write_text(json.dumps(stale, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            refreshed = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")
            crashed = next(item for item in refreshed["panes"] if item["pty_id"] == target["pty_id"])
            unchanged_sibling = next(item for item in refreshed["panes"] if item["pty_id"] == sibling["pty_id"])
            response = json.loads((repo / ".ait" / "sessions" / panes["session_id"] / "responses" / f"{target['response_id']}.json").read_text(encoding="utf-8"))
            replay = _run_cli_json(repo, "session", "replay", "latest", "--turn", "latest", "--format", "json")

            self.assertEqual("crashed", crashed["state"])
            self.assertEqual("crashed", response["state"])
            self.assertEqual(sibling["state"], unchanged_sibling["state"])
            self.assertTrue(any(item["kind"] == "pty_exited" and item.get("state") == "crashed" for item in replay["events"]))

    def test_terminal_roles_keep_advisory_reviewer_and_implementer_workspaces_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_repo(repo)
            impl_command = (
                f"{sys.executable} -c \"import os, pathlib; "
                "print('workspace=' + os.environ.get('AIT_WORKSPACE_REF', '')); "
                "pathlib.Path('impl.txt').write_text('implemented', encoding='utf-8')\""
            )
            review_command = (
                f"{sys.executable} -c \"import os, pathlib; "
                "print('review_ctx=' + str(os.path.exists(os.environ['AIT_CONTEXT_FILE']))); "
                "pathlib.Path('review.txt').write_text('reviewed', encoding='utf-8')\""
            )
            _run_cli_json(repo, "session", "start", "Roles", "--format", "json")
            _run_cli_json(
                repo,
                "session",
                "participant",
                "add",
                "latest",
                "--agent",
                "local-impl",
                "--role",
                "implementer",
                "--command",
                impl_command,
                "--format",
                "json",
            )
            _run_cli_json(
                repo,
                "session",
                "participant",
                "add",
                "latest",
                "--agent",
                "local-review",
                "--role",
                "reviewer",
                "--command",
                review_command,
                "--format",
                "json",
            )
            _run_cli_json(repo, "session", "ask", "latest", "Keep work isolated", "--format", "json")

            _run_cli_text(repo, "session", "attach", "latest")
            panes = _run_cli_json(repo, "session", "panes", "latest", "--format", "json")

            impl = next(item for item in panes["panes"] if item["agent_id"] == "local-impl")
            reviewer = next(item for item in panes["panes"] if item["agent_id"] == "local-review")
            self.assertTrue(impl["attempt_id"])
            self.assertTrue(impl["workspace_ref"])
            self.assertTrue((Path(impl["workspace_ref"]) / "impl.txt").exists())
            self.assertIsNone(reviewer["attempt_id"])
            self.assertTrue(str(reviewer["provenance_refs"]["raw_trace_ref"]).startswith(".ait/sessions/"))
            self.assertFalse((repo / "impl.txt").exists())
            self.assertFalse((repo / "review.txt").exists())
            self.assertEqual("", _git_stdout(repo, "status", "--short"))


def _run_cli_json(repo: Path, *argv: str) -> dict[str, object]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with chdir(repo):
        with patch("sys.argv", ["ait", *argv]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(f"cli exited {exit_code}: {stderr.getvalue()}\nstdout={stdout.getvalue()}")
    return json.loads(stdout.getvalue())


def _run_cli_text(repo: Path, *argv: str) -> str:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with chdir(repo):
        with patch("sys.argv", ["ait", *argv]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main()
    if exit_code != 0:
        raise AssertionError(f"cli exited {exit_code}: {stderr.getvalue()}\nstdout={stdout.getvalue()}")
    return stdout.getvalue()


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "ait@example.invalid")
    _git(repo_root, "config", "user.name", "AIT Tests")
    (repo_root / ".gitignore").write_text(".ait/\n", encoding="utf-8")
    _git(repo_root, "add", ".gitignore")
    _git(repo_root, "commit", "-m", "initial")


def _git_stdout(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
