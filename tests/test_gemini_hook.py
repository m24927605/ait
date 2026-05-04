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
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ait"
        / "resources"
        / "gemini"
        / "gemini_hook.py"
    )
    spec = importlib.util.spec_from_file_location("gemini_hook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load gemini_hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class GeminiHookUnitTests(unittest.TestCase):
    def test_tool_category_maps_gemini_tools_to_ait_categories(self) -> None:
        self.assertEqual("read", hook.tool_category("ReadFile"))
        self.assertEqual("read", hook.tool_category("ListDirectory"))
        self.assertEqual("write", hook.tool_category("WriteFile"))
        self.assertEqual("write", hook.tool_category("ApplyPatch"))
        self.assertEqual("command", hook.tool_category("RunShellCommand"))
        self.assertEqual("other", hook.tool_category("Unknown"))

    def test_tool_files_extracts_absolute_path_field(self) -> None:
        payload = {
            "tool_name": "WriteFile",
            "tool_input": {
                "absolute_path": "/repo/src/app.py",
            },
        }

        self.assertEqual(
            [{"path": "/repo/src/app.py", "access": "write"}],
            hook.tool_files(payload),
        )

    def test_state_round_trips_with_sanitized_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            state = {"session_id": "abc/123", "attempt_id": "repo:attempt"}

            hook.write_state(repo_root, "abc/123", state)

            self.assertTrue(
                (repo_root / ".ait" / "gemini-hooks" / "abc_123.json").exists()
            )
            self.assertEqual(state, hook.read_state(repo_root, "abc/123"))

    def test_persist_transcript_copies_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            upstream = repo_root / "session.json"
            upstream.write_text(
                '{"role":"user","text":"hi"}\n',
                encoding="utf-8",
            )

            persisted = hook.persist_transcript(
                repo_root,
                attempt_id="attempt-aaa",
                source_path=str(upstream),
            )

            self.assertEqual(".ait/transcripts/attempt-aaa.json", persisted)
            copied = repo_root / ".ait" / "transcripts" / "attempt-aaa.json"
            self.assertTrue(copied.exists())
            self.assertEqual(upstream.read_bytes(), copied.read_bytes())

    def test_handle_hook_aftertool_aliases_post_tool_use(self) -> None:
        # AfterTool == PostToolUse semantically. handle_hook must accept both.
        self.assertIsNone(
            hook.handle_hook(
                {"hook_event_name": "AfterTool", "session_id": "missing"},
                {},
            )
        )
        self.assertIsNone(
            hook.handle_hook(
                {"hook_event_name": "PostToolUse", "session_id": "missing"},
                {},
            )
        )


class GeminiHookE2ETests(unittest.TestCase):
    def test_installed_hook_records_session_tool_and_finish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            setup_adapter("gemini", repo_root)
            hook_path = (
                repo_root / ".ait" / "adapters" / "gemini" / "gemini_hook.py"
            )
            self.assertTrue(hook_path.exists())
            self.assertTrue((repo_root / ".gemini" / "settings.json").exists())
            upstream = repo_root / "gemini-session.json"
            upstream.write_text(
                '{"role":"user","text":"add validation"}\n'
                '{"role":"assistant","text":"done"}\n',
                encoding="utf-8",
            )
            env_file = repo_root / "gemini.env"
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "GEMINI_PROJECT_DIR": str(repo_root),
                "GEMINI_ENV_FILE": str(env_file),
            }

            start = _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": "session-gem-1",
                    "cwd": str(repo_root),
                    "source": "startup",
                    "agent_type": "default",
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "AfterTool",
                    "session_id": "session-gem-1",
                    "cwd": str(repo_root),
                    "tool_name": "WriteFile",
                    "duration_ms": 9,
                    "tool_input": {"absolute_path": "src/config.py"},
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "Stop",
                    "session_id": "session-gem-1",
                    "cwd": str(repo_root),
                    "exit_code": 0,
                    "transcript_path": str(upstream),
                },
                env,
            )

            state = json.loads(
                (
                    repo_root / ".ait" / "gemini-hooks" / "session-gem-1.json"
                ).read_text(encoding="utf-8")
            )
            attempt_id = state["attempt_id"]
            attempt = show_attempt(repo_root, attempt_id=attempt_id)
            env_text = env_file.read_text(encoding="utf-8")
            persisted = repo_root / ".ait" / "transcripts" / f"{attempt_id}.json"
            persisted_exists = persisted.exists()
            persisted_bytes = persisted.read_bytes() if persisted_exists else b""
            upstream_bytes = upstream.read_bytes()

        start_payload = json.loads(start.stdout)
        self.assertIn("hookSpecificOutput", start_payload)
        self.assertEqual(
            "SessionStart",
            start_payload["hookSpecificOutput"]["hookEventName"],
        )
        self.assertIn("AIT_ATTEMPT_ID=", env_text)
        self.assertEqual("finished", attempt.attempt["reported_status"])
        self.assertEqual(0, attempt.attempt["result_exit_code"])
        self.assertEqual("gemini:default", attempt.attempt["agent_id"])
        self.assertEqual(1, attempt.evidence_summary["observed_tool_calls"])
        self.assertEqual(1, attempt.evidence_summary["observed_file_writes"])
        self.assertEqual(("src/config.py",), attempt.files["touched"])
        self.assertTrue(persisted_exists, f"expected transcript at {persisted}")
        self.assertEqual(upstream_bytes, persisted_bytes)
        self.assertEqual(
            f".ait/transcripts/{attempt_id}.json",
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


if __name__ == "__main__":
    unittest.main()
