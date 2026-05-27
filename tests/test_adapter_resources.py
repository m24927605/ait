from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ait.adapter_resources import (
    _claude_code_settings,
    _codex_hooks_settings,
    _gemini_settings,
)


def _claude_command() -> str:
    settings = _claude_code_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _codex_command() -> str:
    settings = _codex_hooks_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _gemini_command() -> str:
    settings = _gemini_settings()
    hooks = settings["hooks"]
    return hooks["SessionStart"][0]["hooks"][0]["command"]


def _run_hook(command: str, env_overrides: dict[str, str], payload: bytes = b"{}") -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        command,
        shell=True,
        env=env,
        input=payload,
        capture_output=True,
        timeout=10,
    )


class ClaudeCodeHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # No wrapper at $CLAUDE_PROJECT_DIR/.ait/adapters/claude-code/...
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "claude-code" / "claude_code_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)

    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            # bogus does not exist; AIT_WRAPPER_REPO is honoured over CLAUDE_PROJECT_DIR
            result = _run_hook(
                _claude_command(),
                env_overrides={
                    "CLAUDE_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)


class CodexHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "codex" / "codex_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)

    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            result = _run_hook(
                _codex_command(),
                env_overrides={
                    "CODEX_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)


class GeminiHookCommandTests(unittest.TestCase):
    def test_silent_exit_when_wrapper_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_executes_wrapper_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp) / ".ait" / "adapters" / "gemini" / "gemini_hook.py"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "import sys\n"
                "data = sys.stdin.read()\n"
                "sys.stdout.write('ECHO:' + data)\n",
                encoding="utf-8",
            )
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": "",
                },
                payload=b'{"hook_event_name":"SessionStart"}',
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertIn(b'ECHO:{"hook_event_name":"SessionStart"}', result.stdout)

    def test_silent_exit_when_ait_wrapper_repo_points_nowhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bogus = Path(tmp) / "nonexistent-wrapper-repo"
            result = _run_hook(
                _gemini_command(),
                env_overrides={
                    "GEMINI_PROJECT_DIR": tmp,
                    "AIT_WRAPPER_REPO": str(bogus),
                },
            )
        self.assertEqual(0, result.returncode, msg=result.stderr.decode())
        self.assertEqual(b"", result.stdout)
        self.assertEqual(b"", result.stderr)


if __name__ == "__main__":
    unittest.main()
