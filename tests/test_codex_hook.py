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
        / "codex"
        / "codex_hook.py"
    )
    spec = importlib.util.spec_from_file_location("codex_hook", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load codex_hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class CodexHookUnitTests(unittest.TestCase):
    def test_tool_category_maps_codex_tools_to_ait_categories(self) -> None:
        self.assertEqual("read", hook.tool_category("Read"))
        self.assertEqual("write", hook.tool_category("Edit"))
        self.assertEqual("command", hook.tool_category("Bash"))
        self.assertEqual("command", hook.tool_category("shell"))
        self.assertEqual("write", hook.tool_category("apply_patch"))
        self.assertEqual("other", hook.tool_category("Unknown"))

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

            self.assertTrue(
                (repo_root / ".ait" / "codex-hooks" / "abc_123.json").exists()
            )
            self.assertEqual(state, hook.read_state(repo_root, "abc/123"))

    def test_persist_transcript_copies_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            upstream = repo_root / "rollout-2026-05-04.jsonl"
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

    def test_repo_root_for_payload_prefers_codex_project_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".git").mkdir()
            resolved = hook.repo_root_for_payload(
                {"cwd": str(repo_root)},
                {"CODEX_PROJECT_DIR": str(repo_root)},
            )
            self.assertEqual(repo_root.resolve(), resolved.resolve())


class CodexHookE2ETests(unittest.TestCase):
    def test_installed_hook_records_session_tool_and_finish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            setup_adapter("codex", repo_root)
            hook_path = (
                repo_root / ".ait" / "adapters" / "codex" / "codex_hook.py"
            )
            self.assertTrue(hook_path.exists())
            self.assertTrue((repo_root / ".codex" / "hooks.json").exists())
            upstream = repo_root / "rollout.jsonl"
            upstream.write_text(
                '{"role":"user","text":"refactor parser"}\n'
                '{"role":"assistant","text":"done"}\n',
                encoding="utf-8",
            )
            env_file = repo_root / "codex.env"
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "CODEX_PROJECT_DIR": str(repo_root),
                "CODEX_ENV_FILE": str(env_file),
            }

            start = _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": "session-codex-1",
                    "cwd": str(repo_root),
                    "source": "startup",
                    "agent_type": "default",
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "session-codex-1",
                    "cwd": str(repo_root),
                    "tool_name": "apply_patch",
                    "duration_ms": 12,
                    "tool_input": {"file_path": "src/parser.py"},
                },
                env,
            )
            _run_hook(
                hook_path,
                {
                    "hook_event_name": "SessionEnd",
                    "session_id": "session-codex-1",
                    "cwd": str(repo_root),
                    "exit_code": 0,
                    "transcript_path": str(upstream),
                },
                env,
            )

            state = json.loads(
                (
                    repo_root / ".ait" / "codex-hooks" / "session-codex-1.json"
                ).read_text(encoding="utf-8")
            )
            attempt_id = state["attempt_id"]
            attempt = show_attempt(repo_root, attempt_id=attempt_id)
            env_text = env_file.read_text(encoding="utf-8")
            persisted = repo_root / ".ait" / "transcripts" / f"{attempt_id}.jsonl"
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
        self.assertEqual("codex:default", attempt.attempt["agent_id"])
        self.assertEqual(1, attempt.evidence_summary["observed_tool_calls"])
        self.assertEqual(1, attempt.evidence_summary["observed_file_writes"])
        self.assertEqual(("src/parser.py",), attempt.files["touched"])
        self.assertTrue(persisted_exists, f"expected transcript at {persisted}")
        self.assertEqual(upstream_bytes, persisted_bytes)
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


if __name__ == "__main__":
    unittest.main()
