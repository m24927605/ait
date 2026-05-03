from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.adapters import setup_adapter
from ait.app import show_attempt


def _load_hook_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "claude_code_hook.py"
    spec = importlib.util.spec_from_file_location("claude_code_hook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load claude_code_hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class ClaudeCodeHookTests(unittest.TestCase):
    def test_tool_category_maps_claude_tools_to_ait_categories(self) -> None:
        self.assertEqual("read", hook.tool_category("Read"))
        self.assertEqual("read", hook.tool_category("Grep"))
        self.assertEqual("write", hook.tool_category("Edit"))
        self.assertEqual("write", hook.tool_category("MultiEdit"))
        self.assertEqual("command", hook.tool_category("Bash"))
        self.assertEqual("other", hook.tool_category("TodoWrite"))

    def test_tool_files_extracts_known_path_fields(self) -> None:
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/app.py",
                "path": "src/app.py",
                "notebook_path": "notes.ipynb",
            },
        }

        self.assertEqual(
            [
                {"path": "notes.ipynb", "access": "write"},
                {"path": "src/app.py", "access": "write"},
            ],
            hook.tool_files(payload),
        )

    def test_state_round_trips_with_sanitized_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            state = {"session_id": "abc/123", "attempt_id": "repo:attempt"}

            hook.write_state(repo_root, "abc/123", state)

            self.assertTrue((repo_root / ".ait" / "claude-code-hooks" / "abc_123.json").exists())
            self.assertEqual(state, hook.read_state(repo_root, "abc/123"))

    def test_persist_transcript_copies_existing_file_into_ait_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            upstream = repo_root / "upstream.jsonl"
            upstream.write_text(
                '{"role":"user","text":"hi"}\n{"role":"assistant","text":"hello"}\n',
                encoding="utf-8",
            )

            persisted = hook.persist_transcript(
                repo_root,
                attempt_id="attempt-aaa",
                source_path=str(upstream),
            )

            self.assertEqual(".ait/transcripts/attempt-aaa.jsonl", persisted)
            copied = repo_root / ".ait" / "transcripts" / "attempt-aaa.jsonl"
            self.assertTrue(copied.exists())
            self.assertEqual(upstream.read_bytes(), copied.read_bytes())

    def test_persist_transcript_returns_none_when_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self.assertIsNone(
                hook.persist_transcript(
                    repo_root,
                    attempt_id="attempt-bbb",
                    source_path=str(repo_root / "missing.jsonl"),
                )
            )
            self.assertFalse((repo_root / ".ait" / "transcripts").exists())

    def test_persist_transcript_returns_none_when_source_path_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self.assertIsNone(
                hook.persist_transcript(
                    repo_root,
                    attempt_id="attempt-ccc",
                    source_path=None,
                )
            )

    def test_append_env_file_quotes_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "claude.env"

            hook.append_env_file(
                {"CLAUDE_ENV_FILE": str(env_file)},
                {"AIT_ATTEMPT_ID": "repo:attempt with space"},
            )

            self.assertEqual(
                "export AIT_ATTEMPT_ID='repo:attempt with space'\n",
                env_file.read_text(encoding="utf-8"),
            )

    def test_installed_hook_records_session_tool_and_finish_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            setup_adapter("claude-code", repo_root)
            hook_path = repo_root / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
            env_file = repo_root / "claude.env"
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "CLAUDE_PROJECT_DIR": str(repo_root),
                "CLAUDE_ENV_FILE": str(env_file),
            }

            start = _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": "session-e2e",
                    "cwd": str(repo_root),
                    "source": "startup",
                    "model": "test-model",
                    "agent_type": "default",
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "session-e2e",
                    "cwd": str(repo_root),
                    "tool_name": "Edit",
                    "duration_ms": 7,
                    "tool_input": {"file_path": "README.md"},
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionEnd",
                    "session_id": "session-e2e",
                    "cwd": str(repo_root),
                    "exit_code": 0,
                    "transcript_path": ".claude/transcript.jsonl",
                },
                env,
            )

            state = json.loads(
                (repo_root / ".ait" / "claude-code-hooks" / "session-e2e.json").read_text(
                    encoding="utf-8"
                )
            )
            attempt = show_attempt(repo_root, attempt_id=state["attempt_id"])
            env_text = env_file.read_text(encoding="utf-8")

        payload = json.loads(start.stdout)
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn("AIT_ATTEMPT_ID=", env_text)
        self.assertEqual("finished", attempt.attempt["reported_status"])
        self.assertEqual(0, attempt.attempt["result_exit_code"])
        self.assertEqual(1, attempt.evidence_summary["observed_tool_calls"])
        self.assertEqual(1, attempt.evidence_summary["observed_file_writes"])
        self.assertEqual(("README.md",), attempt.files["touched"])

    def test_session_end_persists_transcript_under_ait_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            setup_adapter("claude-code", repo_root)
            hook_path = repo_root / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
            upstream = repo_root / "upstream-transcript.jsonl"
            upstream.write_text(
                '{"role":"user","text":"do the thing"}\n'
                '{"role":"assistant","text":"done"}\n',
                encoding="utf-8",
            )
            env_file = repo_root / "claude.env"
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "CLAUDE_PROJECT_DIR": str(repo_root),
                "CLAUDE_ENV_FILE": str(env_file),
            }

            _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": "session-persist",
                    "cwd": str(repo_root),
                    "source": "startup",
                    "agent_type": "default",
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionEnd",
                    "session_id": "session-persist",
                    "cwd": str(repo_root),
                    "exit_code": 0,
                    "transcript_path": str(upstream),
                },
                env,
            )

            state = json.loads(
                (
                    repo_root / ".ait" / "claude-code-hooks" / "session-persist.json"
                ).read_text(encoding="utf-8")
            )
            attempt_id = state["attempt_id"]
            persisted = repo_root / ".ait" / "transcripts" / f"{attempt_id}.jsonl"
            self.assertTrue(
                persisted.exists(),
                f"expected transcript at {persisted}",
            )
            self.assertEqual(upstream.read_bytes(), persisted.read_bytes())
            attempt = show_attempt(repo_root, attempt_id=attempt_id)
            self.assertEqual(
                f".ait/transcripts/{attempt_id}.jsonl",
                attempt.attempt["raw_trace_ref"],
            )


def _run_hook(
    hook_path: Path,
    payload: dict[str, object],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload),
        cwd=hook_path.parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


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


if __name__ == "__main__":
    unittest.main()
